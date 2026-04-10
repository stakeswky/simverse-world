"""Add personality_history table for evolution audit trail.

Revision ID: 006_add_personality_history
Revises: 005_add_home_tile
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "006_add_personality_history"
down_revision = "005_add_home_tile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personality_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "resident_id",
            sa.String(),
            sa.ForeignKey("residents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trigger_type", sa.String(10), nullable=False),
        sa.Column(
            "trigger_memory_id",
            sa.String(),
            sa.ForeignKey("memories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("changes_json", sa.JSON(), nullable=False),
        sa.Column("old_type", sa.String(20), nullable=False),
        sa.Column("new_type", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_personality_history_resident_created",
        "personality_history",
        ["resident_id", "created_at"],
    )
    op.create_index(
        "ix_personality_history_trigger_type",
        "personality_history",
        ["resident_id", "trigger_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_personality_history_trigger_type")
    op.drop_index("ix_personality_history_resident_created")
    op.drop_table("personality_history")
