"""add search_vector and last_daily_reward_at

Revision ID: 002_search_reward
Revises:
Create Date: 2026-04-07

"""
from alembic import op
import sqlalchemy as sa

revision = '002_search_reward'
down_revision = None  # Will be updated to chain from initial migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add last_daily_reward_at to users
    op.add_column("users", sa.Column("last_daily_reward_at", sa.DateTime(timezone=True), nullable=True))

    # Add search_vector to residents (as TEXT for SQLite compat; PostgreSQL uses tsvector index)
    op.add_column("residents", sa.Column("search_vector", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("residents", "search_vector")
    op.drop_column("users", "last_daily_reward_at")
