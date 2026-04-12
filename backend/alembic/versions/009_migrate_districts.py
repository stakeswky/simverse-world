"""Migrate resident district values from old 4-district to 11-location system.

Revision ID: 009_migrate_districts
Revises: 008_home_location
Create Date: 2026-04-12
"""
from alembic import op

revision = "009_migrate_districts"
down_revision = "008_home_location"
branch_labels = None
depends_on = None

# Location bounds: (x1, y1, x2, y2) → district name
# Mirrors backend/app/agent/map_data.py LOCATIONS
LOCATION_BOUNDS = [
    # Public facilities
    ((15, 18, 42, 34), "academy"),
    ((72, 13, 83, 26), "tavern"),
    ((53, 14, 62, 26), "cafe"),
    ((108, 20, 124, 34), "workshop"),
    ((57, 43, 70, 53), "library"),
    ((75, 43, 93, 53), "shop"),
    ((106, 45, 132, 62), "town_hall"),
    # Outdoor areas
    ((15, 35, 135, 42), "north_path"),
    ((55, 54, 95, 58), "central_plaza"),
    ((15, 76, 99, 83), "south_lawn"),
    ((50, 85, 90, 99), "town_entrance"),
]


def upgrade() -> None:
    conn = op.get_bind()
    # Read all residents with their tile coordinates
    rows = conn.execute(
        op.f.sa.text("SELECT id, tile_x, tile_y FROM residents")
    ).fetchall()

    for row in rows:
        resident_id = row[0]
        tx = row[1]
        ty = row[2]

        # Find matching location by bounds
        new_district = None
        for (x1, y1, x2, y2), loc_id in LOCATION_BOUNDS:
            if x1 <= tx <= x2 and y1 <= ty <= y2:
                new_district = loc_id
                break

        if new_district is None:
            new_district = "outdoor"

        conn.execute(
            op.f.sa.text(
                "UPDATE residents SET district = :district WHERE id = :id"
            ),
            {"district": new_district, "id": resident_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    # Reverse: map old district values back
    # academy/engineering → engineering, product → product, free → free
    rows = conn.execute(
        op.f.sa.text("SELECT id, district FROM residents")
    ).fetchall()

    for row in rows:
        resident_id = row[0]
        loc_id = row[1]

        # Map public facilities back to reasonable old districts
        if loc_id in ("academy",):
            old_district = "academy"
        elif loc_id in ("workshop", "town_hall"):
            old_district = "engineering"
        elif loc_id in ("cafe", "tavern", "library", "shop"):
            old_district = "product"
        elif loc_id in ("north_path", "central_plaza", "south_lawn", "town_entrance"):
            old_district = "free"
        else:
            old_district = "free"

        conn.execute(
            op.f.sa.text(
                "UPDATE residents SET district = :district WHERE id = :id"
            ),
            {"district": old_district, "id": resident_id},
        )
