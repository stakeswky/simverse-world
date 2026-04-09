"""Onboarding router: check status, create character, load preset, skip."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.onboarding_service import (
    check_onboarding_needed,
    create_player_resident,
    load_preset_as_player,
    skip_onboarding,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


async def _require_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = await get_current_user(db, auth.removeprefix("Bearer "))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


# --- Request / Response schemas ---

class CreateCharacterRequest(BaseModel):
    name: str
    sprite_key: str
    reply_mode: str = "auto"
    ability_md: str = ""
    persona_md: str = ""
    soul_md: str = ""
    portrait_url: str | None = None


class LoadPresetRequest(BaseModel):
    preset_slug: str


class ResidentResponse(BaseModel):
    id: str
    slug: str
    name: str
    sprite_key: str
    tile_x: int
    tile_y: int

    class Config:
        from_attributes = True


# --- Endpoints ---

@router.get("/check")
async def check(request: Request, db: AsyncSession = Depends(get_db)):
    """Check if the current user needs onboarding."""
    user = await _require_user(request, db)
    return await check_onboarding_needed(db, user.id)


@router.post("/create-character", response_model=ResidentResponse)
async def create_character(
    body: CreateCharacterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a new player resident from scratch."""
    user = await _require_user(request, db)
    try:
        resident = await create_player_resident(
            db=db,
            user_id=user.id,
            name=body.name,
            sprite_key=body.sprite_key,
            reply_mode=body.reply_mode,
            ability_md=body.ability_md,
            persona_md=body.persona_md,
            soul_md=body.soul_md,
            portrait_url=body.portrait_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ResidentResponse.model_validate(resident, from_attributes=True)


@router.post("/load-preset", response_model=ResidentResponse)
async def load_preset(
    body: LoadPresetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Load a preset resident as the player character."""
    user = await _require_user(request, db)
    try:
        resident = await load_preset_as_player(db, user.id, body.preset_slug)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ResidentResponse.model_validate(resident, from_attributes=True)


@router.post("/skip", response_model=ResidentResponse)
async def skip(request: Request, db: AsyncSession = Depends(get_db)):
    """Skip onboarding and create a default player resident."""
    user = await _require_user(request, db)
    try:
        resident = await skip_onboarding(db, user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ResidentResponse.model_validate(resident, from_attributes=True)
