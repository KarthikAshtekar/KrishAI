from __future__ import annotations

import argparse

from sqlalchemy.orm import Session

from database import session_scope
from repositories import (
    create_membership,
    create_tenant,
    get_tenant_by_slug,
    upsert_user_identity,
)

ALLOWED_ROLES = ("ADMIN", "AGRONOMIST", "BUYER", "FARMER", "FPO_MANAGER")


def bootstrap_tenant(
    session: Session,
    *,
    firebase_uid: str,
    email: str,
    display_name: str,
    tenant_slug: str,
    tenant_name: str,
    role: str,
) -> tuple[str, str, str]:
    tenant = get_tenant_by_slug(session, slug=tenant_slug)
    if tenant is None:
        tenant = create_tenant(session, slug=tenant_slug, name=tenant_name)
    user = upsert_user_identity(
        session,
        firebase_uid=firebase_uid,
        email=email,
        display_name=display_name,
    )
    membership = create_membership(session, tenant_id=tenant.id, user_id=user.id, role=role)
    return tenant.id, user.id, membership.id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update the initial Firebase user and tenant membership.")
    parser.add_argument("--firebase-uid", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--tenant-slug", required=True)
    parser.add_argument("--tenant-name", required=True)
    parser.add_argument("--role", choices=ALLOWED_ROLES, default="ADMIN")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with session_scope() as session:
        tenant_id, user_id, membership_id = bootstrap_tenant(
            session,
            firebase_uid=args.firebase_uid,
            email=args.email,
            display_name=args.display_name,
            tenant_slug=args.tenant_slug,
            tenant_name=args.tenant_name,
            role=args.role,
        )
    print(f"Bootstrapped tenant={tenant_id} user={user_id} membership={membership_id}")


if __name__ == "__main__":
    main()
