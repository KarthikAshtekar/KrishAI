import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from auth import create_firebase_session, require_roles, resolve_principal, validate_csrf
from config import AppSettings
from database import Base, make_engine
from repositories import create_membership, create_tenant, upsert_user_identity


def make_request(
    *,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> Request:
    normalized_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    if cookies:
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        normalized_headers.append((b"cookie", cookie_header.encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": normalized_headers})


class AuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "auth.db"
        self.engine = make_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_demo_identity_is_bootstrapped_only_outside_production(self) -> None:
        settings = AppSettings(app_env="test", auth_mode="demo")
        with self.sessions.begin() as session:
            principal = resolve_principal(make_request(), session=session, settings=settings)
        self.assertEqual("demo", principal.authentication_mode)
        self.assertEqual("ADMIN", principal.role)

    def test_invalid_firebase_token_returns_401(self) -> None:
        settings = AppSettings(app_env="test", auth_mode="firebase", firebase_project_id="test-project")
        gateway = Mock()
        gateway.verify_id_token.side_effect = ValueError("bad token details must stay internal")
        request = make_request(headers={"Authorization": "Bearer invalid"})

        with self.sessions.begin() as session, self.assertRaises(HTTPException) as raised:
            resolve_principal(request, session=session, settings=settings, gateway=gateway)

        self.assertEqual(401, raised.exception.status_code)
        self.assertNotIn("bad token", raised.exception.detail)

    def test_verified_user_without_membership_is_denied(self) -> None:
        settings = AppSettings(app_env="test", auth_mode="firebase", firebase_project_id="test-project")
        gateway = Mock()
        gateway.verify_id_token.return_value = {"uid": "firebase-no-membership", "email": "none@example.test"}

        with self.sessions.begin() as session, self.assertRaises(HTTPException) as raised:
            resolve_principal(
                make_request(headers={"Authorization": "Bearer valid"}),
                session=session,
                settings=settings,
                gateway=gateway,
            )

        self.assertEqual(403, raised.exception.status_code)

    def test_tenant_header_is_checked_against_membership(self) -> None:
        settings = AppSettings(app_env="test", auth_mode="firebase", firebase_project_id="test-project")
        gateway = Mock()
        gateway.verify_id_token.return_value = {"uid": "firebase-a", "email": "a@example.test"}
        with self.sessions.begin() as session:
            tenant_a = create_tenant(session, slug="farm-a", name="Farm A")
            tenant_b = create_tenant(session, slug="farm-b", name="Farm B")
            user = upsert_user_identity(
                session,
                firebase_uid="firebase-a",
                email="a@example.test",
                display_name="Farmer A",
            )
            create_membership(session, tenant_id=tenant_a.id, user_id=user.id, role="FARMER")
            tenant_b_id = tenant_b.id

        request = make_request(headers={"Authorization": "Bearer valid", "X-Tenant-ID": tenant_b_id})
        with self.sessions.begin() as session, self.assertRaises(HTTPException) as raised:
            resolve_principal(request, session=session, settings=settings, gateway=gateway)
        self.assertEqual(403, raised.exception.status_code)

    def test_session_exchange_requires_recent_sign_in(self) -> None:
        settings = AppSettings(app_env="test", auth_mode="firebase", firebase_project_id="test-project")
        gateway = Mock()
        gateway.verify_id_token.return_value = {
            "uid": "firebase-a",
            "auth_time": int(datetime.now(UTC).timestamp()) - 600,
        }
        with self.assertRaises(HTTPException) as raised:
            create_firebase_session("old-token", settings=settings, gateway=gateway)
        self.assertEqual(401, raised.exception.status_code)
        gateway.create_session_cookie.assert_not_called()

    def test_session_exchange_returns_cookie_for_recent_sign_in(self) -> None:
        settings = AppSettings(app_env="test", auth_mode="firebase", firebase_project_id="test-project")
        gateway = Mock()
        gateway.verify_id_token.return_value = {
            "uid": "firebase-a",
            "auth_time": int(datetime.now(UTC).timestamp()),
        }
        gateway.create_session_cookie.return_value = "signed-session-cookie"
        cookie, claims = create_firebase_session("valid-token", settings=settings, gateway=gateway)
        self.assertEqual("signed-session-cookie", cookie)
        self.assertEqual("firebase-a", claims["uid"])

    def test_csrf_requires_matching_cookie_and_header(self) -> None:
        settings = AppSettings(app_env="test")
        validate_csrf(
            make_request(headers={"X-CSRF-Token": "matching"}, cookies={settings.csrf_cookie_name: "matching"}),
            settings,
        )
        with self.assertRaises(HTTPException) as raised:
            validate_csrf(
                make_request(headers={"X-CSRF-Token": "wrong"}, cookies={settings.csrf_cookie_name: "matching"}),
                settings,
            )
        self.assertEqual(403, raised.exception.status_code)

    def test_role_dependency_denies_unlisted_role(self) -> None:
        dependency = require_roles("ADMIN")
        principal = type("TestPrincipal", (), {"role": "FARMER"})()
        with self.assertRaises(HTTPException) as raised:
            dependency(principal)
        self.assertEqual(403, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
