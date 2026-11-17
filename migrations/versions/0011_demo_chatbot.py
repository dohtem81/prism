"""Add demo chatbot identity and durable jobs.

Revision ID: 0011_demo_chatbot
Revises: 0010_message_processing_progress
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0011_demo_chatbot"
down_revision: str | None = "0010_message_processing_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demo_bot_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kind", "source_id", name="uq_demo_bot_job_source"),
    )
    op.create_index("ix_demo_bot_jobs_pending", "demo_bot_jobs", ["status", "next_attempt_at", "id"])
    op.execute(
        "INSERT INTO users (id, display_name, preferred_lang, is_demo, created_at) "
        "VALUES ('prism_demo_bot', 'Prism Bot', 'fr', false, CURRENT_TIMESTAMP)"
    )
    op.execute(
        "INSERT INTO room_members (room_id, user_id, role, preferred_lang, created_at) "
        "VALUES ('room_demo_general', 'prism_demo_bot', 'member', 'fr', CURRENT_TIMESTAMP)"
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM messages WHERE author_user_id = 'prism_demo_bot') THEN "
        "RAISE EXCEPTION 'Cannot downgrade while demo bot messages exist'; END IF; END $$"
    )
    op.execute("DELETE FROM room_members WHERE user_id = 'prism_demo_bot'")
    op.execute("DELETE FROM users WHERE id = 'prism_demo_bot'")
    op.drop_index("ix_demo_bot_jobs_pending", table_name="demo_bot_jobs")
    op.drop_table("demo_bot_jobs")
