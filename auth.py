from __future__ import annotations

import hmac
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any, Protocol

import firebase_admin
from fastapi import Depends, HTTPException, Request, status
from firebase_admin import auth as firebase_auth
from sqlalchemy.orm import Session

from config import AppSettings, get_settings
from database import get_db
from repositories import (
    create_membership,
    create_tenant,
    get_active_membership,
    get_tenant_by_slug,
    list_active_memberships,
    upsert_user_identity,
)

SESSION_AUTH_MAX_AGE_SECONDS = 5 * 60


class FirebaseGateway(Protocol):
    def verify_id_token(self, token: str) -> Mapping[str, Any]: ...

    def verify_session_cookie(self, cookie: str) -> Mapping[str, Any]: ...

    def create_session_cookie(self, token: str, *, expires_in: timedelta) -> str: ...


class FirebaseAdminGateway:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id

    def _ensure_app(self) -> firebase_admin.App:
        try:
            return firebase_admin.get_app()
        except ValueError:
            options = {"projectId": self.project_id} if self.project_id else None
            return firebase_admin.initialize_app(options=options)

    def verify_id_token(self, token: str) -> Mapping[str, Any]:
        return firebase_auth.verify_id_token(token, app=self._ensure_app(), check_revoked=True)

    def verify_session_cookie(self, cookie: str) -> Mapping[str, Any]:
        return firebase_auth.verify_session_cookie(cookie, app=self._ensure_app(), check_revoked=True)

    def create_session_cookie(self, token: str, *, expires_in: timedelta) -> str:
        return firebase_auth.create_session_cookie(token, expires_in=expires_in, app=self._ensure_app())


@dataclass(frozen=True, slots=True)
class Principal:
    identity_uid: str
    user_id: str
    tenant_id: str
    role: str
    email: str | None
    authentication_mode: str


@lru_cache(maxsize=4)
def get_firebase_gateway(project_id: str) -> FirebaseGateway:
    return FirebaseAdminGateway(project_id)


def _authentication_error(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _authorization_error(detail: str = "Tenant membership required") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _verify_request_identity(
    request: Request,
    *,
    settings: AppSettings,
    gateway: FirebaseGateway,
) -> Mapping[str, Any]:
    authorization = request.headers.get("authorization", "")
    try:
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
            if not token:
                raise _authentication_error()
            return gateway.verify_id_token(token)

        session_cookie = request.cookies.get(settings.session_cookie_name)
        if session_cookie:
            return gateway.verify_session_cookie(session_cookie)
    except HTTPException:
        raise
    except Exception as exc:
        raise _authentication_error("Invalid or expired authentication") from exc

    raise _authentication_error()


def _resolve_membership(
    request: Request,
    *,
    session: Session,
    user_id: str,
) -> tuple[str, str]:
    requested_tenant_id = request.headers.get("x-tenant-id")
    if requested_tenant_id:
        membership = get_active_membership(session, user_id=user_id, tenant_id=requested_tenant_id)
        if membership is None:
            raise _authorization_error()
        return membership.tenant_id, membership.role

    memberships = list_active_memberships(session, user_id=user_id)
    if not memberships:
        raise _authorization_error()
    membership = memberships[0]
    return membership.tenant_id, membership.role


def _resolve_demo_principal(session: Session, settings: AppSettings) -> Principal:
    if settings.is_deployed:
        raise _authentication_error("Demo authentication is disabled")

    tenant = get_tenant_by_slug(session, slug=settings.demo_tenant_slug)
    if tenant is None:
        tenant = create_tenant(session, slug=settings.demo_tenant_slug, name=settings.demo_tenant_name)
    user = upsert_user_identity(
        session,
        firebase_uid=settings.demo_user_uid,
        email=settings.demo_user_email,
        display_name="Demo Farmer",
    )
    membership = create_membership(session, tenant_id=tenant.id, user_id=user.id, role="ADMIN")
    return Principal(
        identity_uid=user.firebase_uid,
        user_id=user.id,
        tenant_id=tenant.id,
        role=membership.role,
        email=user.email,
        authentication_mode="demo",
    )


def resolve_principal(
    request: Request,
    *,
    session: Session,
    settings: AppSettings,
    gateway: FirebaseGateway | None = None,
) -> Principal:
    if settings.auth_mode == "demo":
        return _resolve_demo_principal(session, settings)

    firebase_gateway = gateway or get_firebase_gateway(settings.firebase_project_id)
    claims = _verify_request_identity(request, settings=settings, gateway=firebase_gateway)
    identity_uid = str(claims.get("uid") or claims.get("sub") or "").strip()
    if not identity_uid:
        raise _authentication_error("Verified identity is missing a user ID")

    user = upsert_user_identity(
        session,
        firebase_uid=identity_uid,
        email=str(claims["email"]) if claims.get("email") else None,
        display_name=str(claims["name"]) if claims.get("name") else None,
    )
    tenant_id, role = _resolve_membership(request, session=session, user_id=user.id)
    return Principal(
        identity_uid=identity_uid,
        user_id=user.id,
        tenant_id=tenant_id,
        role=role,
        email=user.email,
        authentication_mode="firebase",
    )


def get_current_principal(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Principal:
    return resolve_principal(request, session=session, settings=settings)


def require_roles(*allowed_roles: str):
    allowed = frozenset(allowed_roles)

    def dependency(principal: Annotated[Principal, Depends(get_current_principal)]) -> Principal:
        if principal.role not in allowed:
            raise _authorization_error("Insufficient role")
        return principal

    return dependency


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def validate_csrf(request: Request, settings: AppSettings) -> None:
    cookie_token = request.cookies.get(settings.csrf_cookie_name, "")
    header_token = request.headers.get("x-csrf-token", "")
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")


def create_firebase_session(
    id_token: str,
    *,
    settings: AppSettings,
    gateway: FirebaseGateway | None = None,
) -> tuple[str, Mapping[str, Any]]:
    firebase_gateway = gateway or get_firebase_gateway(settings.firebase_project_id)
    try:
        claims = firebase_gateway.verify_id_token(id_token)
        auth_time = int(claims.get("auth_time", 0))
        now = int(datetime.now(UTC).timestamp())
        if auth_time <= 0 or now - auth_time > SESSION_AUTH_MAX_AGE_SECONDS:
            raise _authentication_error("Recent sign-in required")
        expires_in = timedelta(days=settings.session_duration_days)
        cookie = firebase_gateway.create_session_cookie(id_token, expires_in=expires_in)
        return cookie, claims
    except HTTPException:
        raise
    except Exception as exc:
        raise _authentication_error("Invalid or expired authentication") from exc
