"""Track when a translation worker starts or fails a message.

Revision ID: 0010_message_processing_progress
Revises: 0009_add_demo_access
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010_message_processing_progress"
down_revision: str | None = "0009_add_demo_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("translation_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("messages", sa.Column("translation_failed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_outbox_events_aggregate_event", "outbox_events", ["aggregate_type", "aggregate_id", "event_type"])


def downgrade() -> None:
    op.drop_index("ix_outbox_events_aggregate_event", table_name="outbox_events")
    op.drop_column("messages", "translation_failed_at")
    op.drop_column("messages", "translation_started_at")
