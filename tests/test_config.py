import unittest

from config import AppSettings, ConfigurationError


class ConfigurationTests(unittest.TestCase):
    def test_development_allows_explicit_demo_mode_and_sqlite(self) -> None:
        settings = AppSettings(app_env="development", auth_mode="demo")
        self.assertFalse(settings.is_deployed)
        self.assertFalse(settings.cookie_secure)

    def test_production_rejects_demo_authentication(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "AUTH_MODE=firebase"):
            AppSettings(
                app_env="production",
                auth_mode="demo",
                database_url="postgresql+psycopg://example",
                firebase_project_id="example-project",
            )

    def test_production_rejects_sqlite(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "PostgreSQL"):
            AppSettings(
                app_env="production",
                auth_mode="firebase",
                database_url="sqlite+pysqlite:///unsafe.db",
                firebase_project_id="example-project",
            )

    def test_production_requires_firebase_project(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "FIREBASE_PROJECT_ID"):
            AppSettings(
                app_env="production",
                auth_mode="firebase",
                database_url="postgresql+psycopg://example",
                firebase_web_api_key="public-web-configuration",
                firebase_auth_domain="example.firebaseapp.com",
            )

    def test_production_requires_firebase_web_configuration(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "FIREBASE_WEB_API_KEY"):
            AppSettings(
                app_env="production",
                auth_mode="firebase",
                database_url="postgresql+psycopg://example",
                firebase_project_id="example-project",
            )

    def test_unknown_environment_name_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "APP_ENV"):
            AppSettings(app_env="prod", auth_mode="demo")

    def test_valid_production_configuration_enables_secure_cookies(self) -> None:
        settings = AppSettings(
            app_env="production",
            auth_mode="firebase",
            database_url="postgresql+psycopg://example",
            firebase_project_id="example-project",
            firebase_web_api_key="public-web-configuration",
            firebase_auth_domain="example.firebaseapp.com",
        )
        self.assertTrue(settings.cookie_secure)

    def test_production_rejects_non_postgresql_database_url(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "PostgreSQL"):
            AppSettings(
                app_env="production",
                auth_mode="firebase",
                database_url="mysql://example",
                firebase_project_id="example-project",
                firebase_web_api_key="public-web-configuration",
                firebase_auth_domain="example.firebaseapp.com",
            )


if __name__ == "__main__":
    unittest.main()
