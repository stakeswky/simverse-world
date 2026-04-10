"""Add home_tile_x/y to residents for agent pathfinding.

Revision ID: 005
Revises: 004_add_memories
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "005_add_home_tile"
down_revision = "004_add_memories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("residents", sa.Column("home_tile_x", sa.Integer(), nullable=True))
    op.add_column("residents", sa.Column("home_tile_y", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("residents", "home_tile_y")
    op.drop_column("residents", "home_tile_x")
