"""index outbox rows for pending-event sweeps

Revision ID: 0007_index_pending_outbox_events
Revises: 0006_add_admin_password_rotation
Create Date: 2026-10-16

"""

from collections.abc import Sequence

from alembic import op


revision: str = "0007_index_pending_outbox_events"
down_revision: str | None = "0006_add_admin_password_rotation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_outbox_events_status_id",
        "outbox_events",
        ["status", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_status_id", table_name="outbox_events")