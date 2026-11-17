"""Add demo identities and the shared General room.

Revision ID: 0009_add_demo_access
Revises: 0008_add_email_verification
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0009_add_demo_access"
down_revision: str | None = "0008_add_email_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(
        "INSERT INTO rooms (id, name, default_translation_mode, created_at) "
        "VALUES ('room_demo_general', 'General', 'balanced', CURRENT_TIMESTAMP) ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    # Do not silently remove the restrictions from existing guest sessions.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM users WHERE is_demo) THEN "
        "RAISE EXCEPTION 'Cannot downgrade while demo users exist'; END IF; END $$"
    )
    op.drop_column("users", "is_demo")
