import tempfile
import unittest
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from database import Base, make_engine
from db_models import Tenant, TenantMembership, User
from scripts.bootstrap_tenant import bootstrap_tenant


class BootstrapTenantTests(unittest.TestCase):
    def test_bootstrap_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "bootstrap.db"
            engine = make_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
            Base.metadata.create_all(engine)
            sessions = sessionmaker(bind=engine, expire_on_commit=False)

            for display_name in ("Initial Admin", "Updated Admin"):
                with sessions.begin() as session:
                    bootstrap_tenant(
                        session,
                        firebase_uid="firebase-admin",
                        email="admin@example.test",
                        display_name=display_name,
                        tenant_slug="first-fpo",
                        tenant_name="First FPO",
                        role="ADMIN",
                    )

            with sessions() as session:
                self.assertEqual(1, session.scalar(select(func.count()).select_from(Tenant)))
                self.assertEqual(1, session.scalar(select(func.count()).select_from(User)))
                self.assertEqual(1, session.scalar(select(func.count()).select_from(TenantMembership)))
                self.assertEqual("Updated Admin", session.scalar(select(User.display_name)))
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
