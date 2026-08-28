"""Concurrency contract for one UTC Living Loop day per user."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.main import app

from tests.test_living_loop_support import auth_headers, create_user

pytestmark = pytest.mark.anyio


async def test_concurrent_today_gets_share_one_persisted_decision(
    tmp_path, monkeypatch,
) -> None:
    from app.models.living_loop_day import LivingLoopDay

    monkeypatch.setattr(settings, "living_loop_p0_enabled", True)
    monkeypatch.setattr(settings, "living_loop_p0_delay_seconds", 3600)
    database = tmp_path / "living-loop-concurrency.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as seed:
        user, _ = await create_user(seed, "concurrent")

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://living-loop.test",
        ) as client:
            responses = await asyncio.gather(*[
                client.get("/living-loop/today", headers=auth_headers(user))
                for _ in range(8)
            ])
        assert {response.status_code for response in responses} == {200}
        ids = {response.json()["decision"]["id"] for response in responses}
        assert len(ids) == 1
        async with factory() as verify:
            count = int((await verify.execute(
                select(func.count()).select_from(LivingLoopDay)
            )).scalar() or 0)
        assert count == 1
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
