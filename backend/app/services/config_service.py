import json
from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_config import SystemConfig


class ConfigService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get(self, key: str, *, default=None):
        """Get a config value. Returns typed value (int/float/str/bool/dict/list).

        Priority: DB > default.
        """
        result = await self._db.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        )
        config = result.scalar_one_or_none()
        if config is None:
            return default
        return json.loads(config.value)

    async def set(self, key: str, value, *, group: str, updated_by: str):
        """Set a config value. Creates or updates."""
        result = await self._db.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        )
        config = result.scalar_one_or_none()
        serialized = json.dumps(value)

        if config is None:
            config = SystemConfig(
                key=key,
                value=serialized,
                group=group,
                updated_by=updated_by,
            )
            self._db.add(config)
        else:
            config.value = serialized
            config.updated_by = updated_by
            config.updated_at = datetime.now(UTC)

        await self._db.commit()

    async def get_group(self, group: str) -> dict:
        """Get all config entries for a group as {key: typed_value}."""
        result = await self._db.execute(
            select(SystemConfig).where(SystemConfig.group == group)
        )
        configs = result.scalars().all()
        return {c.key: json.loads(c.value) for c in configs}
