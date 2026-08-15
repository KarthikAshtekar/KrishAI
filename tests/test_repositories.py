import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from database import Base, make_engine
from db_models import AuditEvent, Tenant, TenantMembership, User
from repositories import (
    create_audit_event,
    create_decision_record,
    create_tenant,
    get_active_membership,
    get_decision_record,
    get_latest_decision_record,
    list_active_memberships,
    upsert_user_identity,
)


class TenantRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "repositories.db"
        self.engine = make_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _seed_two_tenants(self, session: Session) -> tuple[Tenant, Tenant, User, User]:
        tenant_a = create_tenant(session, slug="farm-a", name="Farm A")
        tenant_b = create_tenant(session, slug="farm-b", name="Farm B")
        user_a = upsert_user_identity(
            session,
            firebase_uid="firebase-a",
            email="a@example.test",
            display_name="Farmer A",
        )
        user_b = upsert_user_identity(
            session,
            firebase_uid="firebase-b",
            email="b@example.test",
            display_name="Farmer B",
        )
        session.add_all(
            [
                TenantMembership(tenant_id=tenant_a.id, user_id=user_a.id, role="FARMER"),
                TenantMembership(tenant_id=tenant_b.id, user_id=user_b.id, role="ADMIN"),
            ]
        )
        session.flush()
        return tenant_a, tenant_b, user_a, user_b

    def test_decision_lookup_cannot_cross_tenant_boundary(self) -> None:
        with self.sessions.begin() as session:
            tenant_a, tenant_b, user_a, _ = self._seed_two_tenants(session)
            record = create_decision_record(
                session,
                tenant_id=tenant_a.id,
                created_by_user_id=user_a.id,
                request_id="request-a",
                input_mode="test",
                input_payload={"crop": "maize"},
                result_payload={"recommended_crop": "maize"},
                model_versions={"crop": "legacy-artifact"},
            )
            record_id = record.id

        with self.sessions() as session:
            self.assertIsNotNone(get_decision_record(session, tenant_id=tenant_a.id, record_id=record_id))
            self.assertIsNone(get_decision_record(session, tenant_id=tenant_b.id, record_id=record_id))
            self.assertIsNone(get_latest_decision_record(session, tenant_id=tenant_b.id))

    def test_membership_selector_requires_matching_active_tenant(self) -> None:
        with self.sessions.begin() as session:
            tenant_a, tenant_b, user_a, _ = self._seed_two_tenants(session)

        with self.sessions() as session:
            membership = get_active_membership(session, user_id=user_a.id, tenant_id=tenant_a.id)
            self.assertIsNotNone(membership)
            self.assertIsNone(get_active_membership(session, user_id=user_a.id, tenant_id=tenant_b.id))
            memberships = list_active_memberships(session, user_id=user_a.id)
            self.assertEqual([tenant_a.id], [item.tenant_id for item in memberships])

    def test_identity_upsert_updates_profile_without_duplicate_user(self) -> None:
        with self.sessions.begin() as session:
            first = upsert_user_identity(
                session,
                firebase_uid="firebase-user",
                email="old@example.test",
                display_name="Old name",
            )
            first_id = first.id
            second = upsert_user_identity(
                session,
                firebase_uid="firebase-user",
                email="new@example.test",
                display_name="New name",
            )
            self.assertEqual(first_id, second.id)

        with self.sessions() as session:
            users = list(session.scalars(select(User)))
            self.assertEqual(1, len(users))
            self.assertEqual("new@example.test", users[0].email)

    def test_audit_events_are_written_with_tenant_and_request_context(self) -> None:
        with self.sessions.begin() as session:
            tenant_a, _, user_a, _ = self._seed_two_tenants(session)
            event = create_audit_event(
                session,
                tenant_id=tenant_a.id,
                user_id=user_a.id,
                request_id="request-42",
                event_type="decision.created",
                resource_type="decision_card",
                resource_id="card-42",
                metadata={"source": "api"},
            )
            event_id = event.id

        with self.sessions() as session:
            event = session.get(AuditEvent, event_id)
            self.assertIsNotNone(event)
            self.assertEqual(tenant_a.id, event.tenant_id)
            self.assertEqual("request-42", event.request_id)


if __name__ == "__main__":
    unittest.main()
