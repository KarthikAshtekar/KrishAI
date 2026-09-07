from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from db_models import (
    AuditEvent,
    DecisionCardRecord,
    Tenant,
    TenantMembership,
    User,
)


def create_tenant(session: Session, *, slug: str, name: str) -> Tenant:
    tenant = Tenant(slug=slug, name=name)
    session.add(tenant)
    session.flush()
    return tenant


def get_tenant_by_slug(session: Session, *, slug: str) -> Tenant | None:
    return session.scalar(select(Tenant).where(Tenant.slug == slug))


def upsert_user_identity(
    session: Session,
    *,
    firebase_uid: str,
    email: str | None,
    display_name: str | None,
) -> User:
    user = session.scalar(select(User).where(User.firebase_uid == firebase_uid))
    if user is None:
        user = User(firebase_uid=firebase_uid, email=email, display_name=display_name)
        session.add(user)
    else:
        user.email = email
        user.display_name = display_name
    user.last_login_at = datetime.now(UTC)
    session.flush()
    return user


def list_active_memberships(session: Session, *, user_id: str) -> Sequence[TenantMembership]:
    statement = (
        select(TenantMembership)
        .join(Tenant, Tenant.id == TenantMembership.tenant_id)
        .where(
            TenantMembership.user_id == user_id,
            TenantMembership.is_active.is_(True),
            Tenant.status == "ACTIVE",
        )
        .order_by(TenantMembership.created_at, TenantMembership.tenant_id)
    )
    return tuple(session.scalars(statement))


def get_active_membership(
    session: Session,
    *,
    user_id: str,
    tenant_id: str,
) -> TenantMembership | None:
    statement = (
        select(TenantMembership)
        .join(Tenant, Tenant.id == TenantMembership.tenant_id)
        .where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.is_active.is_(True),
            Tenant.status == "ACTIVE",
        )
    )
    return session.scalar(statement)


def create_membership(
    session: Session,
    *,
    tenant_id: str,
    user_id: str,
    role: str,
) -> TenantMembership:
    existing = session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
        )
    )
    if existing is not None:
        existing.role = role
        existing.is_active = True
        session.flush()
        return existing

    membership = TenantMembership(tenant_id=tenant_id, user_id=user_id, role=role)
    session.add(membership)
    session.flush()
    return membership


def _tenant_decision_statement(tenant_id: str) -> Select[tuple[DecisionCardRecord]]:
    return select(DecisionCardRecord).where(DecisionCardRecord.tenant_id == tenant_id)


def create_decision_record(
    session: Session,
    *,
    tenant_id: str,
    created_by_user_id: str | None,
    request_id: str | None,
    input_mode: str,
    input_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
    model_versions: Mapping[str, Any] | None = None,
) -> DecisionCardRecord:
    record = DecisionCardRecord(
        tenant_id=tenant_id,
        created_by_user_id=created_by_user_id,
        request_id=request_id,
        input_mode=input_mode,
        input_payload=dict(input_payload),
        result_payload=dict(result_payload),
        model_versions=dict(model_versions) if model_versions is not None else None,
    )
    session.add(record)
    session.flush()
    return record


def get_decision_record(
    session: Session,
    *,
    tenant_id: str,
    record_id: str,
) -> DecisionCardRecord | None:
    statement = _tenant_decision_statement(tenant_id).where(DecisionCardRecord.id == record_id)
    return session.scalar(statement)


def get_latest_decision_record(session: Session, *, tenant_id: str) -> DecisionCardRecord | None:
    statement = _tenant_decision_statement(tenant_id).order_by(
        DecisionCardRecord.created_at.desc(),
        DecisionCardRecord.id.desc(),
    )
    return session.scalar(statement.limit(1))


def create_audit_event(
    session: Session,
    *,
    tenant_id: str | None,
    user_id: str | None,
    request_id: str | None,
    event_type: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        request_id=request_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        event_metadata=dict(metadata) if metadata is not None else None,
    )
    session.add(event)
    session.flush()
    return event
