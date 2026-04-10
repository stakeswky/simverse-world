"""Admin Resident Management — list, detail, edit, presets, batch operations."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.resident import Resident
from app.routers.admin.middleware import require_admin
from app.services.scoring_service import compute_star_rating
from app.services.sbti_service import compute_sbti, update_meta_with_sbti
from app.schemas.admin import (
    AdminResidentListItem,
    ResidentPersonaEditRequest,
    PresetResidentRequest,
    BatchDistrictRequest,
    BatchStatusResetRequest,
)

router = APIRouter(prefix="/residents", tags=["admin-residents"])


def _resident_to_dict(r: Resident) -> dict:
    """Serialize a resident with all fields the admin panel needs."""
    return {
        "id": r.id,
        "slug": r.slug,
        "name": r.name,
        "district": r.district,
        "status": r.status,
        "heat": r.heat,
        "star_rating": r.star_rating,
        "sprite_key": getattr(r, "sprite_key", None),
        # frontend uses 'type' and shows 'NPC' or 'Player'
        "type": "NPC" if getattr(r, "resident_type", "player") in ("preset", "npc") else "Player",
        "creator": getattr(r, "creator_id", None),
        "ability_md": r.ability_md,
        "persona_md": r.persona_md,
        "soul_md": r.soul_md,
        "meta_json": getattr(r, "meta_json", None),
    }


async def _list_residents(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 20,
    search: str | None = None,
    district: str | None = None,
    status: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[Resident], int]:
    """List residents with pagination, search, filters."""
    query = select(Resident)
    count_query = select(func.count(Resident.id))

    if search:
        pattern = f"%{search}%"
        condition = or_(Resident.name.ilike(pattern), Resident.slug.ilike(pattern))
        query = query.where(condition)
        count_query = count_query.where(condition)

    if district:
        query = query.where(Resident.district == district)
        count_query = count_query.where(Resident.district == district)

    if status:
        query = query.where(Resident.status == status)
        count_query = count_query.where(Resident.status == status)

    sort_col = getattr(Resident, sort_by, Resident.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    residents = list(result.scalars().all())

    return residents, total


async def _edit_resident(
    db: AsyncSession,
    resident_id: str,
    ability_md: str | None = None,
    persona_md: str | None = None,
    soul_md: str | None = None,
    district: str | None = None,
    status: str | None = None,
    resident_type: str | None = None,
    reply_mode: str | None = None,
) -> Resident:
    """Admin-level edit of any resident's fields."""
    result = await db.execute(select(Resident).where(Resident.id == resident_id))
    resident = result.scalar_one_or_none()
    if not resident:
        raise ValueError("Resident not found")

    if ability_md is not None:
        resident.ability_md = ability_md
    if persona_md is not None:
        resident.persona_md = persona_md
    if soul_md is not None:
        resident.soul_md = soul_md
    if district is not None:
        resident.district = district
    if status is not None:
        resident.status = status
    if resident_type is not None:
        resident.resident_type = resident_type
    if reply_mode is not None:
        resident.reply_mode = reply_mode

    # Recalculate star rating if persona changed
    if any(x is not None for x in [ability_md, persona_md, soul_md]):
        resident.star_rating = compute_star_rating(resident)

    await db.commit()
    await db.refresh(resident)
    return resident


async def _create_preset(
    db: AsyncSession,
    slug: str,
    name: str,
    district: str,
    ability_md: str,
    persona_md: str,
    soul_md: str,
    sprite_key: str,
    tile_x: int,
    tile_y: int,
    resident_type: str,
    reply_mode: str,
    meta_json: dict | None,
    creator_id: str,
) -> Resident:
    """Create a preset resident (admin-managed NPC)."""
    preset_meta = meta_json or {"origin": "preset"}
    sbti = await compute_sbti(name, ability_md, persona_md, soul_md)
    if sbti:
        preset_meta = update_meta_with_sbti(preset_meta, sbti)

    resident = Resident(
        slug=slug,
        name=name,
        district=district,
        ability_md=ability_md,
        persona_md=persona_md,
        soul_md=soul_md,
        sprite_key=sprite_key,
        tile_x=tile_x,
        tile_y=tile_y,
        resident_type=resident_type,
        reply_mode=reply_mode,
        meta_json=preset_meta,
        creator_id=creator_id,
    )
    resident.star_rating = compute_star_rating(resident)
    db.add(resident)
    await db.commit()
    await db.refresh(resident)
    return resident


async def _batch_update_district(
    db: AsyncSession, resident_ids: list[str], district: str
) -> int:
    """Batch update district for multiple residents."""
    result = await db.execute(
        select(Resident).where(Resident.id.in_(resident_ids))
    )
    residents = result.scalars().all()
    for r in residents:
        r.district = district
    await db.commit()
    return len(residents)


async def _batch_reset_status(
    db: AsyncSession, resident_ids: list[str], status: str = "idle"
) -> int:
    """Batch reset status for multiple residents."""
    result = await db.execute(
        select(Resident).where(Resident.id.in_(resident_ids))
    )
    residents = result.scalars().all()
    for r in residents:
        r.status = status
    await db.commit()
    return len(residents)


# ── Routes ─────────────────────────────────────────────────

@router.get("")
async def list_residents(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = None,
    district: str | None = None,
    status: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all residents with filters and pagination."""
    offset = (page - 1) * per_page
    residents, total = await _list_residents(
        db, offset=offset, limit=per_page, search=search,
        district=district, status=status, sort_by=sort_by, sort_order=sort_order,
    )
    return {
        "items": [_resident_to_dict(r) for r in residents],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/{resident_id}")
async def get_resident_detail(
    resident_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get full resident detail (all fields including persona layers)."""
    result = await db.execute(select(Resident).where(Resident.id == resident_id))
    resident = result.scalar_one_or_none()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")
    # Return all columns as dict
    data = {c.key: getattr(resident, c.key) for c in Resident.__table__.columns}
    return data


@router.put("/{resident_id}")
async def edit_resident(
    resident_id: str,
    req: ResidentPersonaEditRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Edit any resident's persona layers, district, status, type, reply mode."""
    try:
        resident = await _edit_resident(
            db, resident_id,
            ability_md=req.ability_md, persona_md=req.persona_md, soul_md=req.soul_md,
            district=req.district, status=req.status,
            resident_type=req.resident_type, reply_mode=req.reply_mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _resident_to_dict(resident)


@router.post("/presets")
async def create_preset(
    req: PresetResidentRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new preset (admin-managed) resident."""
    try:
        resident = await _create_preset(
            db,
            slug=req.slug, name=req.name, district=req.district,
            ability_md=req.ability_md, persona_md=req.persona_md, soul_md=req.soul_md,
            sprite_key=req.sprite_key, tile_x=req.tile_x, tile_y=req.tile_y,
            resident_type=req.resident_type, reply_mode=req.reply_mode,
            meta_json=req.meta_json, creator_id="system",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _resident_to_dict(resident)


@router.delete("/presets/{resident_id}")
async def delete_preset(
    resident_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a preset resident. Only allows deletion of resident_type='preset'."""
    result = await db.execute(select(Resident).where(Resident.id == resident_id))
    resident = result.scalar_one_or_none()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")
    if resident.resident_type != "preset":
        raise HTTPException(status_code=400, detail="Can only delete preset residents via this endpoint")
    await db.delete(resident)
    await db.commit()
    return {"deleted": True, "id": resident_id}


@router.post("/batch/district")
async def batch_district(
    req: BatchDistrictRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Batch change district for multiple residents."""
    count = await _batch_update_district(db, req.resident_ids, req.district)
    return {"updated": count}


@router.post("/batch/status-reset")
async def batch_status_reset(
    req: BatchStatusResetRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Batch reset status for multiple residents."""
    count = await _batch_reset_status(db, req.resident_ids, req.status)
    return {"updated": count}
