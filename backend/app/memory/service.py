import logging
from datetime import datetime, UTC
from sqlalchemy import select, func, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.memory import Memory

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_memory(
        self,
        resident_id: str,
        type: str,
        content: str,
        importance: float,
        source: str,
        *,
        related_resident_id: str | None = None,
        related_user_id: str | None = None,
        media_url: str | None = None,
        media_summary: str | None = None,
        embedding: list[float] | None = None,
        metadata_json: dict | None = None,
    ) -> Memory:
        """Create and persist a new memory record."""
        mem = Memory(
            resident_id=resident_id,
            type=type,
            content=content,
            importance=importance,
            source=source,
            related_resident_id=related_resident_id,
            related_user_id=related_user_id,
            media_url=media_url,
            media_summary=media_summary,
            embedding=embedding,
            metadata_json=metadata_json,
        )
        self.db.add(mem)
        await self.db.commit()
        await self.db.refresh(mem)
        return mem

    async def get_memories(
        self,
        resident_id: str,
        *,
        type: str | None = None,
        limit: int = 50,
    ) -> list[Memory]:
        """Get memories for a resident, optionally filtered by type."""
        stmt = select(Memory).where(Memory.resident_id == resident_id)
        if type:
            stmt = stmt.where(Memory.type == type)
        stmt = stmt.order_by(Memory.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_relationship(
        self,
        resident_id: str,
        *,
        user_id: str | None = None,
        resident_id_target: str | None = None,
    ) -> Memory | None:
        """Get the relationship memory for a specific person."""
        stmt = select(Memory).where(
            Memory.resident_id == resident_id,
            Memory.type == "relationship",
        )
        if user_id:
            stmt = stmt.where(Memory.related_user_id == user_id)
        elif resident_id_target:
            stmt = stmt.where(Memory.related_resident_id == resident_id_target)
        else:
            return None
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_relationship(
        self,
        resident_id: str,
        *,
        user_id: str | None = None,
        resident_id_target: str | None = None,
        content: str,
        importance: float,
        metadata_json: dict | None = None,
    ) -> Memory:
        """Update an existing relationship memory, or create if not found."""
        existing = await self.get_relationship(
            resident_id, user_id=user_id, resident_id_target=resident_id_target,
        )
        if existing:
            existing.content = content
            existing.importance = importance
            if metadata_json is not None:
                existing.metadata_json = metadata_json
            existing.last_accessed_at = datetime.now(UTC)
            await self.db.commit()
            return existing
        else:
            return await self.add_memory(
                resident_id, "relationship", content, importance,
                "chat_player" if user_id else "chat_resident",
                related_user_id=user_id,
                related_resident_id=resident_id_target,
                metadata_json=metadata_json,
            )

    async def get_recent_reflections(
        self,
        resident_id: str,
        limit: int = 5,
    ) -> list[Memory]:
        """Get most important recent reflections."""
        stmt = (
            select(Memory)
            .where(Memory.resident_id == resident_id, Memory.type == "reflection")
            .order_by(Memory.importance.desc(), Memory.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_events_since_last_reflection(self, resident_id: str) -> int:
        """Count event memories created after the most recent reflection."""
        last_ref_stmt = (
            select(Memory.created_at)
            .where(Memory.resident_id == resident_id, Memory.type == "reflection")
            .order_by(Memory.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(last_ref_stmt)
        last_ref_time = result.scalar_one_or_none()

        count_stmt = select(func.count()).select_from(Memory).where(
            Memory.resident_id == resident_id,
            Memory.type == "event",
        )
        if last_ref_time:
            count_stmt = count_stmt.where(Memory.created_at > last_ref_time)

        result = await self.db.execute(count_stmt)
        return result.scalar_one()

    async def evict_memories(self, resident_id: str, max_events: int = 500) -> int:
        """Evict oldest, least important event memories beyond the cap."""
        count_result = await self.db.execute(
            select(func.count()).select_from(Memory).where(
                Memory.resident_id == resident_id, Memory.type == "event",
            )
        )
        total = count_result.scalar_one()
        if total <= max_events:
            return 0

        to_evict = total - max_events
        stmt = (
            select(Memory.id)
            .where(Memory.resident_id == resident_id, Memory.type == "event")
            .order_by(Memory.importance.asc(), Memory.last_accessed_at.asc())
            .limit(to_evict)
        )
        result = await self.db.execute(stmt)
        ids_to_delete = [row[0] for row in result.all()]

        if ids_to_delete:
            await self.db.execute(
                delete(Memory).where(Memory.id.in_(ids_to_delete))
            )
            await self.db.commit()

        return len(ids_to_delete)
