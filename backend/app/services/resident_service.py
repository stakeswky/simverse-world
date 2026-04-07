from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.resident import Resident


async def list_residents(db: AsyncSession) -> list[Resident]:
    result = await db.execute(select(Resident).order_by(Resident.heat.desc()))
    return list(result.scalars().all())


async def get_resident_by_slug(db: AsyncSession, slug: str) -> Resident | None:
    result = await db.execute(select(Resident).where(Resident.slug == slug))
    return result.scalar_one_or_none()
