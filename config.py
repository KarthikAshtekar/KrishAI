from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from database import DEFAULT_DATABASE_URL

PRODUCTION_ENVIRONMENTS = {"production", "staging"}
SUPPORTED_AUTH_MODES = {"demo", "firebase"}


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AppSettings:
    app_env: str = "development"
    auth_mode: str = "demo"
    database_url: str = DEFAULT_DATABASE_URL
    firebase_project_id: str = ""
    firebase_web_api_key: str = ""
    firebase_auth_domain: str = ""
    session_cookie_name: str = "krishi_session"
    csrf_cookie_name: str = "krishi_csrf"
    session_duration_days: int = 5
    demo_tenant_slug: str = "demo-farm"
    demo_tenant_name: str = "Krishi Connect Demo Farm"
    demo_user_uid: str = "demo-user"
    demo_user_email: str = "demo@krishi-connect.local"

    def __post_init__(self) -> None:
        normalized_env = self.app_env.strip().lower()
        normalized_auth = self.auth_mode.strip().lower()
        object.__setattr__(self, "app_env", normalized_env)
        object.__setattr__(self, "auth_mode", normalized_auth)

        if normalized_auth not in SUPPORTED_AUTH_MODES:
            raise ConfigurationError(f"AUTH_MODE must be one of: {', '.join(sorted(SUPPORTED_AUTH_MODES))}")
        if not 1 <= self.session_duration_days <= 14:
            raise ConfigurationError("SESSION_DURATION_DAYS must be between 1 and 14")

        if self.is_deployed:
            if normalized_auth != "firebase":
                raise ConfigurationError("AUTH_MODE=firebase is required in staging and production")
            if self.database_url.startswith("sqlite"):
                raise ConfigurationError("PostgreSQL DATABASE_URL is required in staging and production")
            if not self.firebase_project_id:
                raise ConfigurationError("FIREBASE_PROJECT_ID is required in staging and production")
            if not self.firebase_web_api_key or not self.firebase_auth_domain:
                raise ConfigurationError(
                    "FIREBASE_WEB_API_KEY and FIREBASE_AUTH_DOMAIN are required in staging and production"
                )

    @property
    def is_deployed(self) -> bool:
        return self.app_env in PRODUCTION_ENVIRONMENTS

    @property
    def cookie_secure(self) -> bool:
        return self.is_deployed

    @classmethod
    def from_env(cls) -> AppSettings:
        try:
            session_duration_days = int(os.getenv("SESSION_DURATION_DAYS", "5"))
        except ValueError as exc:
            raise ConfigurationError("SESSION_DURATION_DAYS must be an integer") from exc

        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            auth_mode=os.getenv("AUTH_MODE", "demo"),
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            firebase_project_id=os.getenv("FIREBASE_PROJECT_ID", ""),
            firebase_web_api_key=os.getenv("FIREBASE_WEB_API_KEY", ""),
            firebase_auth_domain=os.getenv("FIREBASE_AUTH_DOMAIN", ""),
            session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "krishi_session"),
            csrf_cookie_name=os.getenv("CSRF_COOKIE_NAME", "krishi_csrf"),
            session_duration_days=session_duration_days,
            demo_tenant_slug=os.getenv("DEMO_TENANT_SLUG", "demo-farm"),
            demo_tenant_name=os.getenv("DEMO_TENANT_NAME", "Krishi Connect Demo Farm"),
            demo_user_uid=os.getenv("DEMO_USER_UID", "demo-user"),
            demo_user_email=os.getenv("DEMO_USER_EMAIL", "demo@krishi-connect.local"),
        )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings.from_env()
