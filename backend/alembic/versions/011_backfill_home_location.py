"""Backfill home_location_id for existing NPC residents.

Revision ID: 011_backfill_home
Revises: 010_add_movement_fields
Create Date: 2026-04-13
"""
from alembic import op
from sqlalchemy import text

revision = "011_backfill_home"
down_revision = "010_add_movement_fields"
branch_labels = None
depends_on = None

_HOUSING_ORDER = [
    ("house_a", 1), ("house_b", 1), ("house_c", 1),
    ("house_d", 1), ("house_e", 1), ("house_f", 1),
    ("apt_star", 5), ("apt_moon", 5), ("apt_dawn", 5),
]


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        text(
            "SELECT id FROM residents "
            "WHERE home_location_id IS NULL "
            "AND resident_type != 'player' "
            "ORDER BY created_at"
        )
    ).fetchall()

    if not rows:
        return

    occ_rows = conn.execute(
        text(
            "SELECT home_location_id, COUNT(*) FROM residents "
            "WHERE home_location_id IS NOT NULL "
            "GROUP BY home_location_id"
        )
    ).fetchall()
    occupied = {r[0]: r[1] for r in occ_rows}

    for (resident_id,) in rows:
        assigned = None
        for loc_id, capacity in _HOUSING_ORDER:
            current = occupied.get(loc_id, 0)
            if current < capacity:
                assigned = loc_id
                occupied[loc_id] = current + 1
                break
        if assigned:
            conn.execute(
                text("UPDATE residents SET home_location_id = :loc WHERE id = :id"),
                {"loc": assigned, "id": resident_id},
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            "UPDATE residents SET home_location_id = NULL "
            "WHERE home_location_id IS NOT NULL "
            "AND resident_type != 'player'"
        )
    )
