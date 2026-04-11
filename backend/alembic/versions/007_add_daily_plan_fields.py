"""Add daily_goal_json and daily_plans_json to residents for hierarchical planning.

Revision ID: 007_daily_plans
Revises: 006_add_personality_history
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa

revision = "007_daily_plans"
down_revision = "006_add_personality_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("residents", sa.Column("daily_goal_json", sa.JSON(), nullable=True))
    op.add_column("residents", sa.Column("daily_plans_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("residents", "daily_plans_json")
    op.drop_column("residents", "daily_goal_json")
