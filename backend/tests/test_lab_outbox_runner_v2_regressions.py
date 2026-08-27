"""Approved-v10 P4 topic ownership and Runner lifecycle regressions."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.lab import outbox_dispatcher as dispatcher
from app.models.lab_event import OutboxEvent


@pytest.fixture
def factory(db_engine):
    return async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)


async def _add(factory, *, event_id: str, topic: str, run_id: str | None = "run-1") -> int:
    async with factory() as db:
        row = OutboxEvent(
            event_id=event_id,
            tenant_id="tenant-1",
            run_id=run_id,
            topic=topic,
            payload_json={"value": event_id},
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id


def test_topic_registry_has_exactly_one_trust_plane_owner():
    assert dispatcher.TOPIC_OWNERS == {
        "lab.run.enqueue": "lab_runner",
        "lab_control": "lab_runner",
        "lab_run_event": "realtime_relay",
        "lab.task.terminalized": "lab_terminalizer",
        "world_changed": "world_relay",
        "artifact.cleanup.requested": "lab_runner",
        "artifact.cleanup.completed": "lab_runner",
    }
    assert set(dispatcher.TOPIC_OWNERS) == set(dispatcher.KNOWN_TOPICS)
    assert dispatcher.owned_topics("lab_runner") == frozenset(
        {
            "lab.run.enqueue",
            "lab_control",
            "artifact.cleanup.requested",
            "artifact.cleanup.completed",
        }
    )


@pytest.mark.anyio
async def test_runner_claims_only_owned_topics_and_publisher_receives_full_envelope(factory):
    ids = {
        topic: await _add(factory, event_id=f"event-{index}", topic=topic)
        for index, topic in enumerate(dispatcher.KNOWN_TOPICS)
    }
    seen: list[dict] = []

    async def publish(envelope: dict) -> None:
        seen.append(envelope)

    publishers = {topic: publish for topic in dispatcher.KNOWN_TOPICS}
    async with factory() as db:
        stats = await dispatcher.dispatch_once(
            db,
            publishers=publishers,
            owned_topics=dispatcher.owned_topics("lab_runner"),
        )

    runner_topics = dispatcher.owned_topics("lab_runner")
    assert stats["published"] == 4
    assert {item["topic"] for item in seen} == runner_topics
    assert {
        (
            item["outbox_id"],
            item["event_id"],
            item["tenant_id"],
            item["run_id"],
            item["payload"]["value"],
        )
        for item in seen
    } == {
        (ids[topic], f"event-{index}", "tenant-1", "run-1", f"event-{index}")
        for index, topic in enumerate(dispatcher.KNOWN_TOPICS)
        if topic in runner_topics
    }

    async with factory() as db:
        rows = (await db.execute(select(OutboxEvent))).scalars().all()
    published = {row.topic for row in rows if row.published_at is not None}
    pending = {row.topic for row in rows if row.dispatch_status == "pending"}
    assert published == runner_topics
    assert pending == {
        "lab_run_event",
        "lab.task.terminalized",
        "world_changed",
    }


@pytest.mark.anyio
async def test_known_but_unregistered_stays_pending_while_truly_unknown_quarantines(factory):
    known_id = await _add(factory, event_id="known", topic="world_changed", run_id=None)
    unknown_id = await _add(factory, event_id="unknown", topic="operator_typo")

    async with factory() as db:
        stats = await dispatcher.dispatch_once(
            db,
            publishers=dispatcher.default_publishers(owner="lab_runner"),
            owned_topics=dispatcher.owned_topics("lab_runner"),
        )

    async with factory() as db:
        known = await db.get(OutboxEvent, known_id)
        unknown = await db.get(OutboxEvent, unknown_id)

    assert known.dispatch_status == "pending"
    assert known.published_at is None
    assert known.attempts == 0
    assert known.locked_until is None
    assert unknown.dispatch_status == "dead"
    assert unknown.published_at is None
    assert unknown.last_error == "unknown_topic"
    assert stats["quarantined"] == 1
    assert stats["published"] == 0


@pytest.mark.anyio
async def test_runner_service_starts_only_runner_owned_dispatch_topics():
    from app.lab.main import RunnerService

    stop = asyncio.Event()
    dispatcher_started = asyncio.Event()
    captured: dict = {}

    async def standby():
        await stop.wait()

    async def dispatch_loop(session_factory, *, publishers, owned_topics, stop_event):
        captured["publishers"] = set(publishers)
        captured["owned_topics"] = frozenset(owned_topics)
        dispatcher_started.set()
        await stop_event.wait()

    service = RunnerService(
        session_factory=object(),
        runner_loop=standby,
        world_reload_loop=standby,
        dispatcher_loop=dispatch_loop,
    )
    running = asyncio.create_task(service.run(stop_event=stop))
    await asyncio.wait_for(dispatcher_started.wait(), timeout=1)
    await service.wait_ready(timeout=1)

    assert service.ready is True
    assert captured == {
        "publishers": {
            "lab.run.enqueue",
            "lab_control",
            "artifact.cleanup.requested",
            "artifact.cleanup.completed",
        },
        "owned_topics": frozenset({
            "lab.run.enqueue",
            "lab_control",
            "artifact.cleanup.requested",
            "artifact.cleanup.completed",
        }),
    }
    stop.set()
    await asyncio.wait_for(running, timeout=1)
    assert service.ready is False


@pytest.mark.anyio
async def test_critical_dispatcher_failure_fails_readiness_and_cancels_siblings():
    from app.lab.main import RunnerService

    stop = asyncio.Event()
    crash = asyncio.Event()
    cancelled: set[str] = set()

    async def sibling(name: str):
        try:
            await stop.wait()
        except asyncio.CancelledError:
            cancelled.add(name)
            raise

    async def dispatch_loop(session_factory, *, publishers, owned_topics, stop_event):
        await crash.wait()
        raise RuntimeError("injected critical dispatcher crash")

    service = RunnerService(
        session_factory=object(),
        runner_loop=lambda: sibling("runner"),
        world_reload_loop=lambda: sibling("world_reload"),
        dispatcher_loop=dispatch_loop,
    )
    running = asyncio.create_task(service.run(stop_event=stop))
    await service.wait_ready(timeout=1)
    assert service.ready is True

    crash.set()
    with pytest.raises(RuntimeError, match="critical dispatcher"):
        await asyncio.wait_for(running, timeout=1)

    assert service.ready is False
    assert service.failure == "outbox_dispatcher: injected critical dispatcher crash"
    assert cancelled == {"runner", "world_reload"}


@pytest.mark.anyio
async def test_runner_service_owns_durable_control_loop_and_exact_controllers():
    from app.lab.main import RunnerService

    stop = asyncio.Event()
    started = asyncio.Event()
    captured: dict = {}

    async def standby():
        await stop.wait()

    async def controller(command):
        return command

    async def control_loop(
        session_factory, *, owner_id, controllers, stop_event
    ):
        captured.update(
            session_factory=session_factory,
            owner_id=owner_id,
            controllers=set(controllers),
        )
        started.set()
        await stop_event.wait()

    service = RunnerService(
        session_factory="factory",
        runner_loop=standby,
        world_reload_loop=standby,
        control_loop=control_loop,
        control_controllers={"runtime": controller, "executor": controller},
        control_owner_id="runner-control-owner",
    )
    running = asyncio.create_task(service.run(stop_event=stop))
    await asyncio.wait_for(started.wait(), timeout=1)
    await service.wait_ready(timeout=1)

    assert captured == {
        "session_factory": "factory",
        "owner_id": "runner-control-owner",
        "controllers": {"runtime", "executor"},
    }
    stop.set()
    await asyncio.wait_for(running, timeout=1)


@pytest.mark.anyio
async def test_runner_service_rejects_partial_control_before_starting_tasks():
    from app.lab.main import RunnerService

    started = False

    async def sibling():
        nonlocal started
        started = True

    async def control_loop(*args, **kwargs):
        return None

    service = RunnerService(
        session_factory=object(),
        runner_loop=sibling,
        world_reload_loop=sibling,
        control_loop=control_loop,
        control_controllers={"runtime": control_loop},
    )
    with pytest.raises(RuntimeError, match="runtime and executor"):
        await service.run(stop_event=asyncio.Event())
    assert started is False
