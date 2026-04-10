"""
Heat Service — recalculates resident heat and manages status transitions.

Heat = number of conversations in the last 7 days.
Status transitions:
  - heat >= 50 → popular
  - heat == 0 AND no conversation in 7 days → sleeping
  - otherwise → idle
  - chatting status is never changed by the cron
"""
from datetime import datetime, timedelta, UTC
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resident import Resident
from app.models.conversation import Conversation

POPULAR_THRESHOLD = 50
SLEEPING_DAYS = 7


async def recalculate_heat(db: AsyncSession) -> list[dict]:
    """
    Recalculate heat for all residents and apply status transitions.
    Returns list of status change dicts for WebSocket broadcast.
    """
    seven_days_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=SLEEPING_DAYS)

    # Count recent conversations per resident
    conv_counts_stmt = (
        select(Conversation.resident_id, func.count(Conversation.id).label("cnt"))
        .where(Conversation.started_at >= seven_days_ago)
        .group_by(Conversation.resident_id)
    )
    conv_result = await db.execute(conv_counts_stmt)
    heat_map: dict[str, int] = {row.resident_id: row.cnt for row in conv_result}

    all_residents = (await db.execute(select(Resident))).scalars().all()
    status_changes: list[dict] = []

    for resident in all_residents:
        new_heat = heat_map.get(resident.id, 0)
        old_status = resident.status
        # Don't overwrite manually set heat with a lower value
        resident.heat = max(new_heat, resident.heat) if new_heat > 0 else resident.heat

        # Never change status of residents currently chatting
        if resident.status == "chatting":
            continue

        # Determine new status based on conversation-derived heat
        if new_heat >= POPULAR_THRESHOLD:
            new_status = "popular"
        elif new_heat == 0:
            last = resident.last_conversation_at
            # Only put to sleep if they had conversations before but none recently
            # Never sleep residents that have never been talked to (new/preset NPCs)
            if last is not None and last < seven_days_ago:
                new_status = "sleeping"
            else:
                new_status = "idle"
        else:
            new_status = "idle"

        if new_status != old_status:
            resident.status = new_status
            status_changes.append({
                "resident_id": resident.id,
                "slug": resident.slug,
                "old_status": old_status,
                "new_status": new_status,
                "heat": new_heat,
            })

    await db.commit()
    return status_changes
