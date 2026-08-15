import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import app
from auth import Principal, get_current_principal
from database import Base, get_db, make_engine
from db_models import AuditEvent, DecisionCardRecord, Tenant, TenantMembership, User


class DecisionPersistenceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "decision-api.db"
        self.engine = make_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

        with self.sessions.begin() as session:
            tenant_a = Tenant(slug="tenant-a", name="Tenant A")
            tenant_b = Tenant(slug="tenant-b", name="Tenant B")
            user_a = User(firebase_uid="firebase-a", email="a@example.test")
            user_b = User(firebase_uid="firebase-b", email="b@example.test")
            session.add_all([tenant_a, tenant_b, user_a, user_b])
            session.flush()
            session.add_all(
                [
                    TenantMembership(tenant_id=tenant_a.id, user_id=user_a.id, role="FARMER"),
                    TenantMembership(tenant_id=tenant_b.id, user_id=user_b.id, role="FARMER"),
                ]
            )
            self.principal_a = Principal(
                identity_uid=user_a.firebase_uid,
                user_id=user_a.id,
                tenant_id=tenant_a.id,
                role="FARMER",
                email=user_a.email,
                authentication_mode="firebase",
            )
            self.principal_b = Principal(
                identity_uid=user_b.firebase_uid,
                user_id=user_b.id,
                tenant_id=tenant_b.id,
                role="FARMER",
                email=user_b.email,
                authentication_mode="firebase",
            )

        def override_db():
            with self.sessions() as session:
                try:
                    yield session
                    session.commit()
                except Exception:
                    session.rollback()
                    raise

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_principal] = lambda: self.principal_a

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_decision_survives_separate_requests_and_is_tenant_scoped(self) -> None:
        with TestClient(app) as client, patch("app.safe_sensor_feeds", return_value=[]):
            created = client.post(
                "/api/decision-card",
                json={"farmer_profile": {"profile_mode": "tenant A supplied inputs"}},
            )
            retrieved = client.get("/api/decision-card")
            app.dependency_overrides[get_current_principal] = lambda: self.principal_b
            other_tenant = client.get("/api/decision-card")

        self.assertEqual(200, created.status_code)
        self.assertEqual(created.json()["decision_id"], retrieved.json()["decision_id"])
        self.assertNotEqual(created.json()["decision_id"], other_tenant.json()["decision_id"])

        with self.sessions() as session:
            decision_count = session.scalar(select(func.count()).select_from(DecisionCardRecord))
            audit_count = session.scalar(select(func.count()).select_from(AuditEvent))
        self.assertEqual(2, decision_count)
        self.assertEqual(2, audit_count)

    def test_application_has_no_process_global_decision_cache(self) -> None:
        source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("LAST_DECISION_CARD", source)


if __name__ == "__main__":
    unittest.main()
