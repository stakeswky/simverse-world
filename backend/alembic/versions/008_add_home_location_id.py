"""Add home_location_id to residents for map-aware housing.

Revision ID: 008_home_location
Revises: 007_daily_plans
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa

revision = "008_home_location"
down_revision = "007_daily_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("residents", sa.Column("home_location_id", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("residents", "home_location_id")
