import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from config import AppSettings, get_settings


class AuthenticationApiTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_demo_login_page_labels_authentication_bypass(self) -> None:
        app.dependency_overrides[get_settings] = lambda: AppSettings(app_env="test", auth_mode="demo")
        with TestClient(app) as client:
            response = client.get("/login")
        self.assertEqual(200, response.status_code)
        self.assertIn("Demo identity is active", response.text)

    def test_session_endpoint_sets_http_only_cookie_after_csrf_check(self) -> None:
        settings = AppSettings(app_env="test", auth_mode="firebase", firebase_project_id="test-project")
        app.dependency_overrides[get_settings] = lambda: settings
        claims = {"uid": "firebase-a", "auth_time": int(datetime.now(UTC).timestamp())}

        user = SimpleNamespace(id="user-a")
        membership = SimpleNamespace(tenant_id="tenant-a")
        with (
            TestClient(app) as client,
            patch("app.create_firebase_session", return_value=("signed-session-cookie", claims)),
            patch("app.upsert_user_identity", return_value=user),
            patch("app.list_active_memberships", return_value=[membership]),
            patch("app.create_audit_event"),
        ):
            csrf_response = client.get("/api/auth/csrf")
            csrf_token = csrf_response.json()["csrf_token"]
            response = client.post(
                "/api/auth/session",
                headers={"X-CSRF-Token": csrf_token},
                json={"id_token": "valid-id-token"},
            )

        self.assertEqual(200, response.status_code)
        set_cookie = response.headers["set-cookie"]
        self.assertIn(f"{settings.session_cookie_name}=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=lax", set_cookie)

    def test_session_endpoint_denies_verified_identity_without_membership(self) -> None:
        settings = AppSettings(app_env="test", auth_mode="firebase", firebase_project_id="test-project")
        app.dependency_overrides[get_settings] = lambda: settings
        claims = {"uid": "firebase-a", "auth_time": int(datetime.now(UTC).timestamp())}
        with (
            TestClient(app) as client,
            patch("app.create_firebase_session", return_value=("unused-cookie", claims)),
            patch("app.upsert_user_identity", return_value=SimpleNamespace(id="user-a")),
            patch("app.list_active_memberships", return_value=[]),
        ):
            csrf_response = client.get("/api/auth/csrf")
            response = client.post(
                "/api/auth/session",
                headers={"X-CSRF-Token": csrf_response.json()["csrf_token"]},
                json={"id_token": "valid-id-token"},
            )
        self.assertEqual(403, response.status_code)

    def test_session_endpoint_rejects_missing_csrf_token(self) -> None:
        settings = AppSettings(app_env="test", auth_mode="firebase", firebase_project_id="test-project")
        app.dependency_overrides[get_settings] = lambda: settings
        with TestClient(app) as client:
            response = client.post("/api/auth/session", json={"id_token": "valid-id-token"})
        self.assertEqual(403, response.status_code)

    def test_demo_mode_rejects_firebase_session_exchange(self) -> None:
        app.dependency_overrides[get_settings] = lambda: AppSettings(app_env="test", auth_mode="demo")
        with TestClient(app) as client:
            csrf_response = client.get("/api/auth/csrf")
            csrf_token = csrf_response.json()["csrf_token"]
            response = client.post(
                "/api/auth/session",
                headers={"X-CSRF-Token": csrf_token},
                json={"id_token": "unused"},
            )
        self.assertEqual(409, response.status_code)

    def test_logout_requires_csrf_and_expires_session_cookie(self) -> None:
        settings = AppSettings(app_env="test", auth_mode="demo")
        app.dependency_overrides[get_settings] = lambda: settings
        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, "session-to-expire")
            csrf_response = client.get("/api/auth/csrf")
            response = client.post(
                "/api/auth/logout",
                headers={"X-CSRF-Token": csrf_response.json()["csrf_token"]},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("signed_out", response.json()["status"])
        self.assertIn(f"{settings.session_cookie_name}=", response.headers["set-cookie"])


if __name__ == "__main__":
    unittest.main()
