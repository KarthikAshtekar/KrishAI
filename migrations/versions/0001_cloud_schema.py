"""Create the initial tenant-aware application schema.

Revision ID: 0001_cloud_schema
Revises:
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_cloud_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id_column() -> sa.Column:
    return sa.Column("id", sa.String(length=36), nullable=False)


def _created_at_column() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def _updated_at_column() -> sa.Column:
    return sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "tenants",
        _id_column(),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.CheckConstraint("status IN ('ACTIVE', 'SUSPENDED')", name="ck_tenants_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    op.create_table(
        "users",
        _id_column(),
        sa.Column("firebase_uid", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=160), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_firebase_uid", "users", ["firebase_uid"], unique=True)

    op.create_table(
        "tenant_memberships",
        _id_column(),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        _created_at_column(),
        sa.CheckConstraint(
            "role IN ('FARMER', 'BUYER', 'FPO_MANAGER', 'AGRONOMIST', 'ADMIN')",
            name="ck_membership_role",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),
    )
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])

    op.create_table(
        "farms",
        _id_column(),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("district", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=80), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_farms_owner_user_id", "farms", ["owner_user_id"])
    op.create_index("ix_farms_tenant_id", "farms", ["tenant_id"])
    op.create_index("ix_farms_tenant_owner", "farms", ["tenant_id", "owner_user_id"])

    op.create_table(
        "plots",
        _id_column(),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("farm_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("area_hectares", sa.Float(), nullable=True),
        sa.Column("current_crop", sa.String(length=100), nullable=True),
        sa.Column("soil_type", sa.String(length=100), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(["farm_id"], ["farms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plots_farm_id", "plots", ["farm_id"])
    op.create_index("ix_plots_tenant_id", "plots", ["tenant_id"])

    op.create_table(
        "sensor_devices",
        _id_column(),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("plot_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("external_id", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("device_metadata", sa.JSON(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(["plot_id"], ["plots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "provider", "external_id", name="uq_sensor_external_identity"),
    )
    op.create_index("ix_sensor_devices_plot_id", "sensor_devices", ["plot_id"])
    op.create_index("ix_sensor_devices_tenant_id", "sensor_devices", ["tenant_id"])

    op.create_table(
        "sensor_readings",
        _id_column(),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("humidity", sa.Float(), nullable=True),
        sa.Column("soil_moisture", sa.Float(), nullable=True),
        sa.Column("light_intensity", sa.Float(), nullable=True),
        sa.Column("rain_status", sa.String(length=20), nullable=True),
        sa.Column("pump_status", sa.String(length=20), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["device_id"], ["sensor_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sensor_readings_device_id", "sensor_readings", ["device_id"])
    op.create_index("ix_sensor_readings_observed_at", "sensor_readings", ["observed_at"])
    op.create_index("ix_sensor_readings_tenant_id", "sensor_readings", ["tenant_id"])
    op.create_index("ix_sensor_readings_tenant_time", "sensor_readings", ["tenant_id", "observed_at"])

    op.create_table(
        "decision_cards",
        _id_column(),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("input_mode", sa.String(length=80), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("model_versions", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decision_cards_created_at", "decision_cards", ["created_at"])
    op.create_index("ix_decision_cards_created_by_user_id", "decision_cards", ["created_by_user_id"])
    op.create_index("ix_decision_cards_request_id", "decision_cards", ["request_id"])
    op.create_index("ix_decision_cards_tenant_created", "decision_cards", ["tenant_id", "created_at"])
    op.create_index("ix_decision_cards_tenant_id", "decision_cards", ["tenant_id"])

    op.create_table(
        "marketplace_listings",
        _id_column(),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("crop", sa.String(length=100), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=30), nullable=False),
        sa.Column("target_price", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_marketplace_listings_created_by_user_id", "marketplace_listings", ["created_by_user_id"])
    op.create_index("ix_marketplace_listings_crop", "marketplace_listings", ["crop"])
    op.create_index("ix_marketplace_listings_tenant_id", "marketplace_listings", ["tenant_id"])

    op.create_table(
        "model_versions",
        _id_column(),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("artifact_uri", sa.String(length=500), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_name", "version", name="uq_model_name_version"),
    )

    op.create_table(
        "audit_events",
        _id_column(),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=80), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])


def downgrade() -> None:
    for table_name in (
        "audit_events",
        "model_versions",
        "marketplace_listings",
        "decision_cards",
        "sensor_readings",
        "sensor_devices",
        "plots",
        "farms",
        "tenant_memberships",
        "users",
        "tenants",
    ):
        op.drop_table(table_name)
