"""add auth schema accounts table

Revision ID: 0003_add_auth_schema_accounts
Revises: 0002_add_user_preferred_lang
Create Date: 2026-08-31

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_add_auth_schema_accounts"
down_revision: str | None = "0002_add_user_preferred_lang"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")

    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_auth_accounts_email"),
        sa.UniqueConstraint("username", name="uq_auth_accounts_username"),
        schema="auth",
    )


def downgrade() -> None:
    op.drop_table("accounts", schema="auth")
    op.execute("DROP SCHEMA IF EXISTS auth")
