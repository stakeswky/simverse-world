"""Add cached movement fields to residents.

Revision ID: 010_add_movement_fields
Revises: 009_migrate_districts
Create Date: 2026-04-12
"""

from alembic import op
import sqlalchemy as sa

revision = "010_add_movement_fields"
down_revision = "009_migrate_districts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("residents", sa.Column("movement_path_json", sa.JSON(), nullable=True))
    op.add_column("residents", sa.Column("movement_target_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("residents", "movement_target_json")
    op.drop_column("residents", "movement_path_json")
