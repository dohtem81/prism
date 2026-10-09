"""add language_flags table

Revision ID: 0005_add_language_flags
Revises: 0004_add_message_receipts
Create Date: 2026-10-09

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_add_language_flags"
down_revision: str | None = "0004_add_message_receipts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "language_flags",
        sa.Column("lang", sa.String(length=16), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("image", sa.LargeBinary(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("lang"),
    )


def downgrade() -> None:
    op.drop_table("language_flags")
