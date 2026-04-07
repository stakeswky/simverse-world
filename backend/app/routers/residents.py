from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.resident import ResidentListItem, ResidentDetail, ResidentEditRequest, VersionSnapshot
from app.services.resident_service import list_residents, get_resident_by_slug
from app.services.version_service import create_version_snapshot, get_versions
from app.services.auth_service import get_current_user
from app.services.scoring_service import compute_star_rating

router = APIRouter(prefix="/residents", tags=["residents"])


async def _require_user_auth(request: Request, db: AsyncSession = Depends(get_db)):
    """Extract and verify auth — returns user object."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = await get_current_user(db, auth.removeprefix("Bearer "))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


@router.get("", response_model=list[ResidentListItem])
async def list_all(db: AsyncSession = Depends(get_db)):
    residents = await list_residents(db)
    return [ResidentListItem.model_validate(r, from_attributes=True) for r in residents]


@router.get("/{slug}", response_model=ResidentDetail)
async def get_one(slug: str, db: AsyncSession = Depends(get_db)):
    r = await get_resident_by_slug(db, slug)
    if not r:
        raise HTTPException(status_code=404, detail="Resident not found")
    return ResidentDetail.model_validate(r, from_attributes=True)


@router.put("/{slug}", response_model=ResidentDetail)
async def edit_resident(
    slug: str,
    req: ResidentEditRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Edit a resident's three layers. Creator only. Auto-versions before each edit."""
    user = await _require_user_auth(request, db)

    r = await get_resident_by_slug(db, slug)
    if not r:
        raise HTTPException(status_code=404, detail="Resident not found")
    if r.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Only the creator can edit this resident")

    # Snapshot current state before editing
    await create_version_snapshot(db, r)

    # Re-fetch (version service commits, so r may be stale)
    r = await get_resident_by_slug(db, slug)

    # Apply updates (only non-None fields)
    if req.ability_md is not None:
        r.ability_md = req.ability_md
    if req.persona_md is not None:
        r.persona_md = req.persona_md
    if req.soul_md is not None:
        r.soul_md = req.soul_md

    # Recalculate star rating
    r.star_rating = compute_star_rating(r)

    await db.commit()
    await db.refresh(r)
    return ResidentDetail.model_validate(r, from_attributes=True)


@router.get("/{slug}/versions", response_model=list[VersionSnapshot])
async def get_resident_versions(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get version history for a resident."""
    user = await _require_user_auth(request, db)
    r = await get_resident_by_slug(db, slug)
    if not r:
        raise HTTPException(status_code=404, detail="Resident not found")
    if r.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Only the creator can view versions")
    return await get_versions(db, r.id)
