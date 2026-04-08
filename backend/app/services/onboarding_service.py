"""Onboarding service: create player resident, bind to user, assign spawn point."""
import random
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.resident import Resident

# Central Plaza spawn point (tile coordinates)
CENTRAL_PLAZA_X = 76
CENTRAL_PLAZA_Y = 50
SPAWN_RADIUS = 5
TILE_SIZE = 32


async def check_onboarding_needed(db: AsyncSession, user_id: str) -> dict:
    """Check if user needs onboarding (no player_resident_id yet)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(f"User {user_id} not found")

    return {
        "needs_onboarding": user.player_resident_id is None,
        "player_resident_id": user.player_resident_id,
    }


async def create_player_resident(
    db: AsyncSession,
    user_id: str,
    name: str,
    sprite_key: str,
    reply_mode: str = "auto",
    ability_md: str = "",
    persona_md: str = "",
    soul_md: str = "",
    portrait_url: str | None = None,
) -> Resident:
    """Create a Resident(type='player') and bind it to the User."""
    # Check user exists and doesn't already have a player resident
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(f"User {user_id} not found")
    if user.player_resident_id:
        raise ValueError(f"User {user_id} already has a player resident")

    # Generate spawn position near Central Plaza (tile coords)
    spawn_x = CENTRAL_PLAZA_X + random.randint(-SPAWN_RADIUS, SPAWN_RADIUS)
    spawn_y = CENTRAL_PLAZA_Y + random.randint(-SPAWN_RADIUS, SPAWN_RADIUS)

    # Generate unique slug
    slug = _generate_player_slug(name)
    existing = await db.execute(select(Resident).where(Resident.slug == slug))
    if existing.scalar_one_or_none():
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    resident = Resident(
        slug=slug,
        name=name,
        district="free",
        status="idle",
        resident_type="player",
        reply_mode=reply_mode,
        sprite_key=sprite_key,
        tile_x=spawn_x,
        tile_y=spawn_y,
        creator_id=user_id,
        ability_md=ability_md,
        persona_md=persona_md,
        soul_md=soul_md,
        portrait_url=portrait_url,
        meta_json={"origin": "onboarding"},
    )
    db.add(resident)
    await db.flush()  # ensure resident.id is persisted before FK reference

    # Bind to user and set initial position (tile coords)
    user.player_resident_id = resident.id
    user.last_x = spawn_x
    user.last_y = spawn_y

    await db.commit()
    await db.refresh(resident)
    await db.refresh(user)
    return resident


async def load_preset_as_player(
    db: AsyncSession,
    user_id: str,
    preset_slug: str,
) -> Resident:
    """Copy a preset Resident's data to create a new player Resident and bind to User."""
    # Find the preset resident
    result = await db.execute(select(Resident).where(Resident.slug == preset_slug))
    preset = result.scalar_one_or_none()
    if not preset:
        raise ValueError(f"Preset resident '{preset_slug}' not found")

    return await create_player_resident(
        db=db,
        user_id=user_id,
        name=preset.name,
        sprite_key=preset.sprite_key,
        reply_mode="auto",
        ability_md=preset.ability_md,
        persona_md=preset.persona_md,
        soul_md=preset.soul_md,
    )


async def skip_onboarding(db: AsyncSession, user_id: str) -> Resident:
    """Create a minimal default player Resident and bind to User."""
    return await create_player_resident(
        db=db,
        user_id=user_id,
        name="新居民",
        sprite_key="埃迪",
        reply_mode="auto",
    )


def _generate_player_slug(name: str) -> str:
    """Generate a URL-friendly slug from player name."""
    slug = name.lower().strip()
    slug = re.sub(r'[^\w\u4e00-\u9fff-]', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    if not slug:
        slug = f"player-{uuid.uuid4().hex[:8]}"
    return f"p-{slug}"  # prefix with p- to distinguish from NPC residents
