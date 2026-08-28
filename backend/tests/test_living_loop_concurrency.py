"""Concurrency contract for one UTC Living Loop day per user."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.main import app

from tests.test_living_loop_support import auth_headers, create_user, event_payload

pytestmark = pytest.mark.anyio


@asynccontextmanager
async def _concurrency_app(tmp_path, monkeypatch, name: str, user_names: list[str]):
    monkeypatch.setattr(settings, "living_loop_p0_enabled", True)
    monkeypatch.setattr(settings, "living_loop_p0_delay_seconds", 3600)
    database = tmp_path / f"{name}.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as seed:
        users = [
            (await create_user(seed, user_name))[0]
            for user_name in user_names
        ]

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://living-loop.test",
        ) as client:
            yield client, factory, users
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


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


async def test_same_choice_key_cannot_bind_two_decisions_concurrently(
    tmp_path, monkeypatch,
) -> None:
    from app.models.living_loop_day import LivingLoopDay
    from app.models.product_event import ProductEvent

    async with _concurrency_app(
        tmp_path,
        monkeypatch,
        "cross-decision-key",
        ["key-owner-a", "key-owner-b"],
    ) as (client, factory, users):
        decisions = []
        for user in users:
            response = await client.get(
                "/living-loop/today", headers=auth_headers(user)
            )
            decisions.append(response.json()["decision"]["id"])
        key = str(uuid4())

        responses = await asyncio.gather(*[
            client.post(
                f"/living-loop/decisions/{decision_id}/choose",
                headers=auth_headers(user),
                json={"choice_key": "public_support", "idempotency_key": key},
            )
            for user, decision_id in zip(users, decisions, strict=True)
        ])

        assert sorted(response.status_code for response in responses) == [200, 409]
        async with factory() as verify:
            bound_days = int((await verify.execute(
                select(func.count()).select_from(LivingLoopDay).where(
                    LivingLoopDay.choice_idempotency_key == key
                )
            )).scalar() or 0)
            events = int((await verify.execute(
                select(func.count()).select_from(ProductEvent).where(
                    ProductEvent.event_id == key
                )
            )).scalar() or 0)
        assert bound_days == events == 1


async def test_choose_and_client_event_collision_commit_one_consistent_winner(
    tmp_path, monkeypatch,
) -> None:
    from app.models.living_loop_day import LivingLoopDay
    from app.models.product_event import ProductEvent

    async with _concurrency_app(
        tmp_path,
        monkeypatch,
        "choose-event-key",
        ["choose-event-owner"],
    ) as (client, factory, users):
        user = users[0]
        today = await client.get(
            "/living-loop/today", headers=auth_headers(user)
        )
        decision_id = today.json()["decision"]["id"]
        key = str(uuid4())

        choose_response, event_response = await asyncio.gather(
            client.post(
                f"/living-loop/decisions/{decision_id}/choose",
                headers=auth_headers(user),
                json={"choice_key": "public_support", "idempotency_key": key},
            ),
            client.post(
                "/product-events/batch",
                headers=auth_headers(user),
                json=event_payload(key),
            ),
        )

        assert sorted([choose_response.status_code, event_response.status_code]) == [
            200,
            409,
        ]
        async with factory() as verify:
            day = await verify.get(LivingLoopDay, decision_id)
            event = (await verify.execute(
                select(ProductEvent).where(ProductEvent.event_id == key)
            )).scalar_one()
        if choose_response.status_code == 200:
            assert day.choice_idempotency_key == key
            assert day.state == "chosen"
            assert event.event_name == "living_loop_choice_confirmed"
        else:
            assert day.choice_idempotency_key is None
            assert day.state == "pending"
            assert event.event_name == "living_loop_today_viewed"


async def test_concurrent_exact_choice_retries_share_one_event(
    tmp_path, monkeypatch,
) -> None:
    from app.models.product_event import ProductEvent

    async with _concurrency_app(
        tmp_path,
        monkeypatch,
        "same-binding-key",
        ["same-binding-owner"],
    ) as (client, factory, users):
        user = users[0]
        today = await client.get(
            "/living-loop/today", headers=auth_headers(user)
        )
        decision_id = today.json()["decision"]["id"]
        key = str(uuid4())
        request = {
            "choice_key": "private_mediation",
            "idempotency_key": key,
        }

        responses = await asyncio.gather(*[
            client.post(
                f"/living-loop/decisions/{decision_id}/choose",
                headers=auth_headers(user),
                json=request,
            )
            for _ in range(2)
        ])

        assert [response.status_code for response in responses] == [200, 200]
        assert responses[0].json() == responses[1].json()
        async with factory() as verify:
            events = int((await verify.execute(
                select(func.count()).select_from(ProductEvent).where(
                    ProductEvent.event_id == key
                )
            )).scalar() or 0)
        assert events == 1
