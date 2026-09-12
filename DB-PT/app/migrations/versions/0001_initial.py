"""Initial schema: users, groups, custom fields and personnel.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _json():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "app_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_users")),
        sa.UniqueConstraint("username", name=op.f("uq_app_users_username")),
    )

    op.create_table(
        "personnel_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("colour", sa.String(length=7), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_personnel_groups")),
        sa.UniqueConstraint("name", name=op.f("uq_personnel_groups_name")),
    )

    op.create_table(
        "custom_fields",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("field_type", sa.String(length=20), nullable=False),
        sa.Column("options", _json(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("show_in_table", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["group_id"], ["personnel_groups.id"],
            name=op.f("fk_custom_fields_group_id_personnel_groups"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_custom_fields")),
        sa.UniqueConstraint("key", name=op.f("uq_custom_fields_key")),
    )
    op.create_index(op.f("ix_custom_fields_group_id"), "custom_fields", ["group_id"])

    op.create_table(
        "personnel",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("identifier", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("preferred_name", sa.String(length=100), nullable=True),
        sa.Column("job_title", sa.String(length=150), nullable=True),
        sa.Column("role", sa.String(length=150), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("extra", _json(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["group_id"], ["personnel_groups.id"],
            name=op.f("fk_personnel_group_id_personnel_groups"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_personnel")),
        sa.UniqueConstraint("identifier", name=op.f("uq_personnel_identifier")),
    )
    op.create_index("ix_personnel_name", "personnel", ["last_name", "first_name"])
    op.create_index(op.f("ix_personnel_group_id"), "personnel", ["group_id"])
    op.create_index(op.f("ix_personnel_status"), "personnel", ["status"])


def downgrade() -> None:
    # Dropping a table drops its indexes too. MariaDB refuses to drop an index a
    # foreign key still needs, so tables go first, children before parents.
    op.drop_table("personnel")
    op.drop_table("custom_fields")
    op.drop_table("personnel_groups")
    op.drop_table("app_users")
