"""add preferred language to users

Revision ID: 0002_add_user_preferred_lang
Revises: 0001_initial_baseline
Create Date: 2026-08-09

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_add_user_preferred_lang"
down_revision: str | None = "0001_initial_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("preferred_lang", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "preferred_lang")
