from datetime import datetime, UTC
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.resident import Resident

MAX_VERSIONS = 10


async def create_version_snapshot(db: AsyncSession, resident: Resident) -> dict:
    """Save current resident state as a version snapshot (max 10 kept)."""
    result = await db.execute(select(Resident).where(Resident.id == resident.id))
    r = result.scalar_one()

    versions: list[dict] = list(r.versions_json or [])
    next_version = (versions[-1]["version_number"] + 1) if versions else 1

    snapshot = {
        "version_number": next_version,
        "ability_md": r.ability_md,
        "persona_md": r.persona_md,
        "soul_md": r.soul_md,
        "created_at": datetime.now(UTC).isoformat(),
    }
    versions.append(snapshot)

    # Keep only last MAX_VERSIONS
    if len(versions) > MAX_VERSIONS:
        versions = versions[-MAX_VERSIONS:]

    r.versions_json = versions
    await db.commit()
    return snapshot


async def get_versions(db: AsyncSession, resident_id: str) -> list[dict]:
    """Return version history for a resident, newest first."""
    result = await db.execute(select(Resident).where(Resident.id == resident_id))
    r = result.scalar_one_or_none()
    if not r:
        return []
    return list(reversed(r.versions_json or []))
