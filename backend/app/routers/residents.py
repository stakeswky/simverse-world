import io
import json
import re
import random
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.resident import Resident
from app.models.user import User
from app.schemas.resident import ResidentListItem, ResidentDetail, ResidentEditRequest, VersionSnapshot, ResidentImportResponse, PlayerPositionUpdate
from app.services.resident_service import list_residents, get_resident_by_slug
from app.services.version_service import create_version_snapshot, get_versions
from app.services.auth_service import get_current_user
from app.services.scoring_service import compute_star_rating
from app.services.sbti_service import compute_sbti, update_meta_with_sbti
from app.services.forge_service import allocate_resident_location, _generate_slug, SPRITE_KEYS

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


def _parse_skill_md(content: str) -> dict:
    """Parse combined SKILL.md into separate layers."""
    sections = {"ability_md": "", "persona_md": "", "soul_md": ""}
    current_key = None

    for line in content.split("\n"):
        stripped = line.strip().lower()
        if re.match(r'^#\s*(ability|能力)', stripped):
            current_key = "ability_md"
            sections[current_key] = line + "\n"
        elif re.match(r'^#\s*(persona|人格)', stripped):
            current_key = "persona_md"
            sections[current_key] = line + "\n"
        elif re.match(r'^#\s*(soul|灵魂)', stripped):
            current_key = "soul_md"
            sections[current_key] = line + "\n"
        elif current_key:
            sections[current_key] += line + "\n"

    return sections


@router.get("", response_model=list[ResidentListItem])
async def list_all(db: AsyncSession = Depends(get_db)):
    residents = await list_residents(db)
    return [ResidentListItem.model_validate(r, from_attributes=True) for r in residents]


@router.post("/import", response_model=ResidentImportResponse)
async def import_resident(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(...),
    slug: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Import a resident from SKILL.md or zip file."""
    user = await _require_user_auth(request, db)

    # Check slug uniqueness
    existing = await get_resident_by_slug(db, slug)
    if existing:
        raise HTTPException(status_code=409, detail="Slug already exists")

    content = await file.read()
    filename = file.filename or ""

    # Parse based on file type
    ability_md, persona_md, soul_md = "", "", ""
    meta_json: dict = {}

    if filename.endswith(".md") or filename.endswith(".txt"):
        # Single SKILL.md
        text = content.decode("utf-8", errors="replace")
        layers = _parse_skill_md(text)
        ability_md = layers["ability_md"]
        persona_md = layers["persona_md"]
        soul_md = layers["soul_md"]

    elif filename.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = zf.namelist()

                # Try ability.md (or work.md for colleague-skill format)
                if "ability.md" in names:
                    ability_md = zf.read("ability.md").decode("utf-8", errors="replace")
                elif "work.md" in names:
                    # colleague-skill format
                    ability_md = zf.read("work.md").decode("utf-8", errors="replace")

                if "persona.md" in names:
                    persona_md = zf.read("persona.md").decode("utf-8", errors="replace")

                # soul.md optional — empty string if not present (colleague-skill)
                if "soul.md" in names:
                    soul_md = zf.read("soul.md").decode("utf-8", errors="replace")

                if "meta.json" in names:
                    try:
                        meta_json = json.loads(zf.read("meta.json").decode("utf-8"))
                    except Exception:
                        meta_json = {}
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid zip file")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Use .md or .zip")

    # Create a mock-like object for scoring
    class _ResidentForScoring:
        pass
    r_score = _ResidentForScoring()
    r_score.ability_md = ability_md
    r_score.persona_md = persona_md
    r_score.soul_md = soul_md
    r_score.total_conversations = 0
    r_score.avg_rating = 0.0

    star_rating = compute_star_rating(r_score)

    district, tile_x, tile_y, home_loc_id = await allocate_resident_location(
        db,
        ability_text=ability_md,
        persona_text=persona_md,
        soul_text=soul_md,
    )

    # Compute SBTI personality (non-blocking: skip if fails)
    final_meta = {**meta_json, "origin": "import"}
    sbti = await compute_sbti(name, ability_md, persona_md, soul_md)
    if sbti:
        final_meta = update_meta_with_sbti(final_meta, sbti)

    resident = Resident(
        slug=slug,
        name=name,
        district=district,
        status="idle",
        heat=0,
        model_tier="standard",
        token_cost_per_turn=1,
        creator_id=user.id,
        ability_md=ability_md,
        persona_md=persona_md,
        soul_md=soul_md,
        meta_json=final_meta,
        sprite_key=random.choice(SPRITE_KEYS),
        tile_x=tile_x,
        tile_y=tile_y,
        star_rating=star_rating,
        home_location_id=home_loc_id,
    )
    db.add(resident)
    await db.commit()
    await db.refresh(resident)

    return ResidentImportResponse(
        id=resident.id,
        slug=resident.slug,
        name=resident.name,
        district=resident.district,
        star_rating=resident.star_rating,
        ability_md=resident.ability_md,
        persona_md=resident.persona_md,
        soul_md=resident.soul_md,
        meta_json=resident.meta_json,
    )


@router.put("/player/position")
async def update_player_position(
    request: Request,
    req: PlayerPositionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Persist the player's tile coordinates (from teleport) to the user record."""
    user = await _require_user_auth(request, db)
    if not user.player_resident_id:
        raise HTTPException(status_code=404, detail="No player resident")

    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    TILE_SIZE = 32
    db_user.last_x = req.tile_x * TILE_SIZE + TILE_SIZE // 2
    db_user.last_y = req.tile_y * TILE_SIZE + TILE_SIZE
    await db.commit()
    return {"tile_x": req.tile_x, "tile_y": req.tile_y}


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

    # Recalculate SBTI when personality layers change
    if req.ability_md is not None or req.persona_md is not None or req.soul_md is not None:
        sbti = await compute_sbti(r.name, r.ability_md, r.persona_md, r.soul_md)
        if sbti:
            r.meta_json = update_meta_with_sbti(r.meta_json, sbti)

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
