"""Add app_settings, used to hold the generated session key.

Revision ID: 0002_app_settings
Revises: 0001_initial
Create Date: 2026-09-12
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_app_settings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_settings")),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
