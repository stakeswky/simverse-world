"""Admin endpoint: batch re-embed event memories using the active provider.

Used after switching embedding provider to align vector space.
"""
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.memory.providers.base import EmbeddingProvider
from app.memory.providers.factory import get_active_provider
from app.models.memory import Memory
from app.models.user import User
from app.routers.admin.middleware import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/embeddings", tags=["admin-embeddings"])


async def _reembed_event_memories(provider: EmbeddingProvider) -> None:
    """Background task: re-embed all event memories using the provided provider.

    Strategy:
    - Load ids in batches of 100 (IDs only to keep memory footprint small)
    - For each batch: load content, call embed_batch, write back
    - Commits per batch so progress is durable on crash
    - Zero vectors (returned by provider on transient failure) are skipped,
      not written, to prevent silent embedding corruption.

    Note: Uses offset-based pagination. If event memories are INSERTED during
    the re-embed (e.g., from live chat), some newly-inserted rows may skip
    their first embedding. Run during low-traffic windows for best coverage.
    """
    batch_size = 100
    offset = 0
    total = 0
    async with async_session() as session:
        while True:
            rows = await session.execute(
                select(Memory.id, Memory.content)
                .where(Memory.type == "event")
                .order_by(Memory.id)
                .offset(offset)
                .limit(batch_size)
            )
            batch = rows.all()
            if not batch:
                break
            ids = [r[0] for r in batch]
            contents = [r[1] for r in batch]
            vectors = await provider.embed_batch(contents)
            zero = [0.0] * provider.dimensions
            skipped = 0
            for mid, vec in zip(ids, vectors):
                if vec == zero:
                    skipped += 1
                    continue
                await session.execute(
                    Memory.__table__.update().where(Memory.id == mid).values(embedding=vec)
                )
            if skipped:
                logger.warning(
                    "Re-embed skipped %d memories in this batch (provider returned zero vectors)",
                    skipped,
                )
            await session.commit()
            total += len(batch)
            if (total // batch_size) % 10 == 0:
                logger.info("Re-embed progress: %d memories updated", total)
            offset += batch_size
            await asyncio.sleep(0)  # yield control
    logger.info("Re-embed completed. Updated %d memories.", total)


@router.post("/reembed-all")
async def reembed_all(
    background: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Queue a background task that re-embeds all event memories."""
    count_result = await db.execute(
        select(func.count()).select_from(Memory).where(Memory.type == "event")
    )
    candidate_count = count_result.scalar_one()

    provider = await get_active_provider()
    background.add_task(_reembed_event_memories, provider)

    return {
        "status": "queued",
        "candidate_count": candidate_count,
        "provider": provider.name,
    }
