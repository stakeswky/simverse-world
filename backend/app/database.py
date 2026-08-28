import logging
import time

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

logger = logging.getLogger("app.slow_query")

# Explicit pool sizing (P0-2): asyncpg defaults (pool_size=5, max_overflow=10)
# are exhausted by ~15 concurrent chat sessions. SQLite doesn't use QueuePool,
# so only apply these to real server databases.
_pool_kwargs = {}
if not settings.database_url.startswith("sqlite"):
    _pool_kwargs = dict(
        pool_size=20,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

engine = create_async_engine(
    settings.database_url,
    echo=False,
    hide_parameters=True,
    **_pool_kwargs,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _install_slow_query_logging(threshold_ms: int) -> None:
    """P1-3: log any statement slower than ``threshold_ms``. Registered on the
    sync engine behind the async engine; a no-op unless slow_query_ms > 0."""
    if threshold_ms <= 0:
        return
    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        context._sv_query_start = time.perf_counter()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        start = getattr(context, "_sv_query_start", None)
        if start is None:
            return
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if elapsed_ms >= threshold_ms:
            logger.warning("slow query %.0fms: %s", elapsed_ms, " ".join(statement.split())[:300])


_install_slow_query_logging(settings.slow_query_ms)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session
