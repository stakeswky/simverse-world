from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.resident import Resident
from app.schemas.resident import ResidentListItem

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=list[ResidentListItem])
async def search_residents(
    q: str = Query("", max_length=200),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search residents by name, district, role. Uses ILIKE (SQLite-compatible fallback)."""
    if not q.strip():
        return []

    q_stripped = q.strip()

    # ILIKE fallback (works on both SQLite and PostgreSQL)
    # In production with PostgreSQL, the tsvector index provides performance
    stmt = (
        select(Resident)
        .where(
            Resident.name.ilike(f"%{q_stripped}%")
            | Resident.district.ilike(f"%{q_stripped}%")
        )
        .order_by(Resident.heat.desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    residents = result.scalars().all()

    # Also search in meta_json role field via Python filter (SQLite JSON support is limited)
    if not residents or len(residents) < limit:
        # Try meta_json role search via a broader query and filter in Python
        all_stmt = select(Resident).order_by(Resident.heat.desc()).limit(100)
        all_result = await db.execute(all_stmt)
        all_residents = all_result.scalars().all()

        extra = [
            r for r in all_residents
            if r not in residents
            and r.meta_json
            and q_stripped.lower() in str(r.meta_json.get("role", "")).lower()
        ]
        residents = list(residents) + extra[:limit - len(residents)]

    return [ResidentListItem.model_validate(r, from_attributes=True) for r in residents[:limit]]
