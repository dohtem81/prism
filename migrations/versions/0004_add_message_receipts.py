"""add message_receipts table

Revision ID: 0004_add_message_receipts
Revises: 0003_add_auth_schema_accounts
Create Date: 2026-10-09

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_add_message_receipts"
down_revision: str | None = "0003_add_auth_schema_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_receipts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_receipts_msg_user"),
    )
    op.create_index("ix_message_receipts_user_id", "message_receipts", ["user_id"], unique=False)

    # Existing history counts as seen so nobody gets a flood of unread dots on deploy.
    op.execute(
        """
        INSERT INTO message_receipts (message_id, user_id, seen_at)
        SELECT m.id, rm.user_id, now()
        FROM messages m
        JOIN room_members rm ON rm.room_id = m.room_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_message_receipts_user_id", table_name="message_receipts")
    op.drop_table("message_receipts")
