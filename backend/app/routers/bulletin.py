from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.schemas.resident import ResidentListItem

router = APIRouter(prefix="/bulletin", tags=["bulletin"])


@router.get("")
async def get_bulletin(db: AsyncSession = Depends(get_db)):
    """Central plaza bulletin: top 10 hot residents, 5 newest, 24h conversation count."""
    hot_stmt = select(Resident).order_by(Resident.heat.desc()).limit(10)
    hot_result = await db.execute(hot_stmt)
    hot_residents = [ResidentListItem.model_validate(r, from_attributes=True) for r in hot_result.scalars().all()]

    new_stmt = select(Resident).order_by(Resident.created_at.desc()).limit(5)
    new_result = await db.execute(new_stmt)
    new_residents = [ResidentListItem.model_validate(r, from_attributes=True) for r in new_result.scalars().all()]

    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    count_result = await db.execute(
        select(func.count(Conversation.id)).where(Conversation.started_at >= twenty_four_hours_ago)
    )
    recent_conv_count = count_result.scalar() or 0

    return {
        "hot_residents": [r.model_dump() for r in hot_residents],
        "new_residents": [r.model_dump() for r in new_residents],
        "recent_conversations_24h": recent_conv_count,
    }
