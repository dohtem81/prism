"""require password rotation for newly provisioned admin account

Revision ID: 0006_add_admin_password_rotation
Revises: 0005_add_language_flags
Create Date: 2026-10-15

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006_add_admin_password_rotation"
down_revision: str | None = "0005_add_language_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False),
        schema="auth",
    )


def downgrade() -> None:
    op.drop_column("accounts", "must_change_password", schema="auth")