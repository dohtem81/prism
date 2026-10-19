"""add email verification

Revision ID: 0008_add_email_verification
Revises: 0007_index_pending_outbox_events
Create Date: 2026-10-19

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0008_add_email_verification"
down_revision: str | None = "0007_index_pending_outbox_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        schema="auth",
    )
    # Accounts that exist before verification was introduced must keep working.
    op.execute("UPDATE auth.accounts SET email_verified_at = created_at")

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["auth.accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_auth_email_verification_tokens_hash"),
        schema="auth",
    )
    op.create_index(
        "ix_auth_email_verification_tokens_account_id",
        "email_verification_tokens",
        ["account_id"],
        schema="auth",
    )


def downgrade() -> None:
    op.drop_index("ix_auth_email_verification_tokens_account_id", table_name="email_verification_tokens", schema="auth")
    op.drop_table("email_verification_tokens", schema="auth")
    op.drop_column("accounts", "email_verified_at", schema="auth")
