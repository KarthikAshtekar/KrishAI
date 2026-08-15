import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import make_engine
from db_models import Tenant, TenantMembership, User

EXPECTED_TABLES = {
    "audit_events",
    "decision_cards",
    "farms",
    "marketplace_listings",
    "model_versions",
    "plots",
    "sensor_devices",
    "sensor_readings",
    "tenant_memberships",
    "tenants",
    "users",
}


class DatabaseSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "schema-test.db"
        self.database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
        self.alembic_config = Config("alembic.ini")
        self.alembic_config.set_main_option("sqlalchemy.url", self.database_url)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initial_migration_creates_expected_tables(self):
        command.upgrade(self.alembic_config, "head")

        engine = make_engine(self.database_url)
        table_names = set(inspect(engine).get_table_names())
        engine.dispose()

        self.assertTrue(EXPECTED_TABLES.issubset(table_names))

    def test_membership_is_unique_per_tenant_and_user(self):
        command.upgrade(self.alembic_config, "head")
        engine = make_engine(self.database_url)

        with Session(engine) as session:
            tenant = Tenant(slug="demo-fpo", name="Demo FPO")
            user = User(firebase_uid="firebase-user-1", email="farmer@example.test")
            session.add_all([tenant, user])
            session.flush()
            session.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role="FARMER"))
            session.commit()

            session.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role="FARMER"))
            with self.assertRaises(IntegrityError):
                session.commit()

        engine.dispose()

    def test_downgrade_removes_application_tables(self):
        command.upgrade(self.alembic_config, "head")
        command.downgrade(self.alembic_config, "base")

        engine = make_engine(self.database_url)
        table_names = set(inspect(engine).get_table_names())
        engine.dispose()

        self.assertFalse(EXPECTED_TABLES.intersection(table_names))

    def test_migration_matches_sqlalchemy_metadata(self):
        command.upgrade(self.alembic_config, "head")

        command.check(self.alembic_config)


if __name__ == "__main__":
    unittest.main()
