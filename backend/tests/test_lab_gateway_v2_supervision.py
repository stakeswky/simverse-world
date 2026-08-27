"""Gateway-side protocol-v2 supervision and result-delivery regressions."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import json
import uuid

import httpx
import pytest
from sqlalchemy import func, select

from app.config import settings
from app.lab import (
    broker,
    grants,
    orchestrator as lab_orchestrator,
    protocol,
    queue,
    runner,
    supervision,
)
from app.lab.protocol import RuntimeEvent, ToolResultCommand
from app.lab.runtime_ref.server import create_app
from app.lab.runtime_ref.service_auth import ServiceTokenIssuer
from app.lab.sandbox.base import (
    ArtifactSpec,
    HttpAgentAdapter,
    RunSpec,
    RuntimeEventBatch,
    RuntimeV2NonRetryableError,
    RuntimeV2RetryableError,
)
from app.models.lab_action import LabApproval, LabToolAction
from app.models.lab_artifact import LabArtifact
from app.models.lab_budget import LabRunBudget
from app.models.lab_event import LabRunEvent
from app.models.lab_lease import LabRunLease
from app.models.lab_run import LabRun
from app.models.lab_runtime import (
    LabRuntimeIntent,
    LabRuntimeResult,
    LabRuntimeSession,
    LabRuntimeTurn,
)
from app.models.lab_task import LabTask


OWNER = "gateway-v2-owner"
EPOCH = 7


@pytest.fixture(autouse=True)
def configured_test_egress(monkeypatch):
    monkeypatch.setenv("LAB_EGRESS_ENABLED", "true")
    monkeypatch.setenv("LAB_EGRESS_SEARCH_ENDPOINT", "http://search.test")
    monkeypatch.setenv("LAB_EGRESS_BASE_URL", "http://egress.test")
    monkeypatch.setenv(
        "LAB_EGRESS_API_KEY", "test-egress-key-at-least-32-bytes-long"
    )


def test_v2_owner_identity_is_replica_unique_and_column_bounded():
    first_process = uuid.uuid4()
    second_process = uuid.uuid4()
    first = lab_orchestrator._v2_owner_id(
        "shared-run", process_namespace=first_process
    )

    assert first == lab_orchestrator._v2_owner_id(
        "shared-run", process_namespace=first_process
    )
    assert first != lab_orchestrator._v2_owner_id(
        "shared-run", process_namespace=second_process
    )
    assert len(first) == 36


async def _seed_runtime(db, *, run_id: str = "gateway-v2-run") -> LabRuntimeSession:
    task = LabTask(
        id=f"task-{run_id}",
        issuer_user_id="tenant",
        researcher_slug="sage",
        title="protocol-v2 supervision task",
        brief_md="exercise gateway supervision",
        scopes_json=["web_search"],
        status="running",
        accepted_run_id=run_id,
        deliverable_kind="report",
    )
    run = LabRun(
        id=run_id,
        task_id=f"task-{run_id}",
        researcher_slug="sage",
        adapter="simverse_ref",
        status="running",
        protocol_version=2,
        scopes_json=["web_search"],
    )
    lease = LabRunLease(
        run_id=run_id,
        owner_id=OWNER,
        fencing_epoch=EPOCH,
        heartbeat_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    session = LabRuntimeSession(
        id=f"session-{run_id}",
        run_id=run_id,
        client_run_id=f"client-{run_id}",
        fencing_epoch=EPOCH,
        protocol_version=2,
        provider_name="simverse_ref",
        provider_session_id=f"provider-{run_id}",
        locator_json={"session_id": f"provider-{run_id}"},
        durability_class="session_affine",
        status="ready",
    )
    db.add_all([task, run, lease, session])
    await db.commit()
    return session


async def _seed_v2_task_run(
    db, *, run_id: str, status: str = "queued"
) -> tuple[LabRun, LabTask]:
    task = LabTask(
        id=f"task-{run_id}",
        issuer_user_id="tenant",
        researcher_slug="sage",
        title="protocol-v2 task",
        brief_md="produce a result",
        scopes_json=["web_search"],
        status="assigned",
        accepted_run_id=run_id,
        deliverable_kind="report",
    )
    run = LabRun(
        id=run_id,
        task_id=task.id,
        researcher_slug="sage",
        adapter="simverse_ref",
        protocol_version=2,
        status=status,
        scopes_json=["web_search"],
        budget_usd_cents=50,
    )
    db.add_all([task, run])
    await db.commit()
    return run, task


def _event(
    session: LabRuntimeSession,
    cursor: int,
    *,
    kind: str = "think",
    turn_id: str | None = None,
    intent_id: str | None = None,
    payload: dict | None = None,
    outcome: str | None = None,
    tool_args: dict | None = None,
) -> RuntimeEvent:
    values = {
        "schema_version": 2,
        "event_id": f"event-{session.run_id}-{cursor}",
        "run_id": session.run_id,
        "session_id": session.provider_session_id,
        "cursor": cursor,
        "epoch": EPOCH,
        "event_kind": kind,
        "turn_id": turn_id,
        "intent_id": intent_id,
        "outcome": outcome,
        "payload": payload or {"summary": f"event-{cursor}"},
        "occurred_at": datetime.now(UTC),
    }
    if kind == "tool_intent":
        args = tool_args or {"query": "approved-v10 sentinel"}
        values.update(
            tool_name="web.search",
            tool_args=args,
            tool_args_digest=protocol.args_digest(args),
        )
    return RuntimeEvent.model_validate(values)


class _TwoTurnCompleter:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, messages):
        self.calls += 1
        if self.calls == 1:
            return json.dumps({
                "plan": "query the broker",
                "tool": "web.search",
                "query": "approved-v10 sentinel",
                "conclusion": "",
            }), 7
        return json.dumps({
            "plan": "use the broker result",
            "tool": None,
            "query": "",
            "conclusion": json.dumps(messages, ensure_ascii=False),
        }), 9


@pytest.mark.anyio
async def test_runtime_event_commit_precedes_ack_and_exact_replay_converges(db_session):
    session = await _seed_runtime(db_session)
    event = _event(
        session,
        1,
        kind="tool_intent",
        turn_id="turn-1",
        intent_id="intent-1",
    )

    committed = await supervision.commit_runtime_event(
        db_session, event=event, owner_id=OWNER
    )
    assert committed.duplicate is False
    assert committed.committed_through == 1
    session_id = session.id
    run_id = session.run_id
    db_session.expire_all()
    stored_session = await db_session.get(LabRuntimeSession, session_id)
    assert stored_session.provider_cursor_committed == 1
    assert stored_session.provider_cursor_acked == 0
    assert await db_session.scalar(
        select(func.count()).select_from(LabRunEvent)
    ) == 1
    canonical = await db_session.get(LabRunEvent, committed.event_id)
    assert canonical.tenant_id == "tenant"
    assert canonical.task_id == f"task-{run_id}"
    assert await db_session.scalar(
        select(func.count()).select_from(LabRuntimeTurn)
    ) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(LabRuntimeIntent)
    ) == 1

    replay = await supervision.commit_runtime_event(
        db_session, event=event, owner_id=OWNER
    )
    assert replay.duplicate is True
    assert replay.committed_through == 1
    assert await db_session.scalar(
        select(func.count()).select_from(LabRunEvent)
    ) == 1

    await supervision.record_provider_ack(
        db_session,
        run_id=run_id,
        session_id=stored_session.provider_session_id,
        epoch=EPOCH,
        owner_id=OWNER,
        acked_through=1,
    )
    db_session.expire_all()
    stored_session = await db_session.get(LabRuntimeSession, session_id)
    assert stored_session.provider_cursor_acked == 1
    assert await supervision.record_provider_ack(
        db_session,
        run_id=run_id,
        session_id=stored_session.provider_session_id,
        epoch=EPOCH,
        owner_id=OWNER,
        acked_through=1,
    ) == 1
    with pytest.raises(
        supervision.RuntimeProtocolConflict, match="ACK cursor regressed"
    ):
        await supervision.record_provider_ack(
            db_session,
            run_id=run_id,
            session_id=stored_session.provider_session_id,
            epoch=EPOCH,
            owner_id=OWNER,
            acked_through=0,
        )


@pytest.mark.anyio
async def test_runtime_event_wrong_binding_and_changed_cursor_replay_fail_closed(db_session):
    session = await _seed_runtime(db_session, run_id="binding-run")
    original = _event(session, 1, payload={"summary": "first"})
    await supervision.commit_runtime_event(db_session, event=original, owner_id=OWNER)

    changed = _event(session, 1, payload={"summary": "different"})
    with pytest.raises(supervision.RuntimeProtocolConflict):
        await supervision.commit_runtime_event(db_session, event=changed, owner_id=OWNER)

    wrong_epoch = original.model_copy(update={"cursor": 2, "epoch": EPOCH + 1})
    with pytest.raises(supervision.RuntimeProtocolConflict):
        await supervision.commit_runtime_event(db_session, event=wrong_epoch, owner_id=OWNER)


@pytest.mark.anyio
async def test_runtime_event_requires_authoritative_task_tenant(db_session):
    session = await _seed_runtime(db_session, run_id="missing-task-tenant-run")
    event = _event(session, 1)
    task = await db_session.get(LabTask, f"task-{session.run_id}")
    await db_session.delete(task)
    await db_session.commit()

    with pytest.raises(
        supervision.RuntimeProtocolConflict,
        match="authoritative task tenant binding",
    ):
        await supervision.commit_runtime_event(
            db_session, event=event, owner_id=OWNER
        )
    assert await db_session.scalar(
        select(func.count())
        .select_from(LabRunEvent)
        .where(LabRunEvent.run_id == event.run_id)
    ) == 0


@pytest.mark.anyio
async def test_runtime_tool_args_are_redacted_before_gateway_persistence(db_session):
    session = await _seed_runtime(db_session, run_id="redacted-intent-run")
    args = {
        "query": "approved-v10 sentinel",
        "api_token": "super-secret-runtime-token",
        "nested": {"password": "never-persist-this"},
    }
    event = _event(
        session,
        1,
        kind="tool_intent",
        turn_id="redacted-turn",
        intent_id="redacted-intent",
        tool_args=args,
    )
    committed = await supervision.commit_runtime_event(
        db_session, event=event, owner_id=OWNER
    )
    intent = await db_session.get(LabRuntimeIntent, committed.intent_row_id)
    assert intent.args_digest == protocol.args_digest(args)
    assert intent.args_redacted_json == {
        "query": "approved-v10 sentinel",
        "api_token": "[REDACTED]",
        "nested": {"password": "[REDACTED]"},
    }
    stored = await db_session.get(LabRunEvent, committed.event_id)
    persisted = json.dumps(
        {"intent": intent.args_redacted_json, "ledger": stored.payload_json}
    )
    assert "super-secret-runtime-token" not in persisted
    assert "never-persist-this" not in persisted


@pytest.mark.anyio
async def test_out_of_order_events_only_ack_highest_contiguous_cursor(db_session):
    session = await _seed_runtime(db_session, run_id="cursor-gap-run")
    second = await supervision.commit_runtime_event(
        db_session, event=_event(session, 2), owner_id=OWNER
    )
    assert second.committed_through == 0

    first = await supervision.commit_runtime_event(
        db_session, event=_event(session, 1), owner_id=OWNER
    )
    assert first.committed_through == 2
    with pytest.raises(supervision.RuntimeProtocolConflict):
        await supervision.record_provider_ack(
            db_session,
            run_id=session.run_id,
            session_id=session.provider_session_id,
            epoch=EPOCH,
            owner_id=OWNER,
            acked_through=3,
        )


@pytest.mark.anyio
async def test_pending_intent_still_allows_earlier_gap_to_close(db_session):
    session = await _seed_runtime(db_session, run_id="pending-intent-gap-run")
    intent = await supervision.commit_runtime_event(
        db_session,
        event=_event(
            session,
            2,
            kind="tool_intent",
            turn_id="gap-turn",
            intent_id="gap-intent",
        ),
        owner_id=OWNER,
    )
    assert intent.committed_through == 0

    gap = await supervision.commit_runtime_event(
        db_session, event=_event(session, 1), owner_id=OWNER
    )
    assert gap.committed_through == 2


@pytest.mark.anyio
async def test_runtime_turn_sequence_rejects_overlap_and_unbound_final(db_session):
    session = await _seed_runtime(db_session, run_id="turn-sequence-run")
    overlapping = _event(session, 2, turn_id="turn-b")
    unbound_final = _event(
        session,
        2,
        kind="final",
        turn_id="never-observed-turn",
    )
    first = await supervision.commit_runtime_event(
        db_session,
        event=_event(session, 1, turn_id="turn-a"),
        owner_id=OWNER,
    )
    with pytest.raises(
        supervision.RuntimeProtocolConflict, match="another is active"
    ):
        await supervision.commit_runtime_event(
            db_session,
            event=overlapping,
            owner_id=OWNER,
        )
    with pytest.raises(
        supervision.RuntimeProtocolConflict, match="must bind the active turn"
    ):
        await supervision.commit_runtime_event(
            db_session,
            event=unbound_final,
            owner_id=OWNER,
        )

    first_turn = await db_session.get(LabRuntimeTurn, first.turn_row_id)
    first_turn.status = "completed"
    first_turn.completed_at = datetime.now(UTC)
    await db_session.commit()
    second = await supervision.commit_runtime_event(
        db_session,
        event=overlapping,
        owner_id=OWNER,
    )
    second_turn = await db_session.get(LabRuntimeTurn, second.turn_row_id)
    assert second_turn.sequence == 2
    assert second_turn.status == "ready"


@pytest.mark.anyio
async def test_gap_window_reserves_one_event_slot(db_session, monkeypatch):
    session = await _seed_runtime(db_session, run_id="gap-event-reserve-run")
    events = {cursor: _event(session, cursor) for cursor in range(1, 6)}
    monkeypatch.setattr(protocol, "MAX_UNACKED_EVENTS", 4)
    monkeypatch.setattr(protocol, "MAX_UNACKED_BYTES", 10_000_000)

    for cursor in (2, 3, 4):
        committed = await supervision.commit_runtime_event(
            db_session, event=events[cursor], owner_id=OWNER
        )
        assert committed.committed_through == 0
    with pytest.raises(supervision.Backpressure):
        await supervision.commit_runtime_event(
            db_session, event=events[5], owner_id=OWNER
        )

    closed = await supervision.commit_runtime_event(
        db_session, event=events[1], owner_id=OWNER
    )
    assert closed.committed_through == 4


@pytest.mark.anyio
async def test_gap_window_reserves_max_event_bytes(db_session, monkeypatch):
    session = await _seed_runtime(db_session, run_id="gap-byte-reserve-run")
    second = _event(session, 2, payload={"summary": "second"})
    third = _event(session, 3, payload={"summary": "third"})
    first = _event(session, 1, payload={"summary": "first"})
    second_size = len(
        protocol.canonical_json(second.model_dump(mode="json")).encode("utf-8")
    )
    monkeypatch.setattr(protocol, "MAX_UNACKED_EVENTS", 128)
    monkeypatch.setattr(
        protocol,
        "MAX_UNACKED_BYTES",
        second_size + protocol.MAX_EVENT_BYTES,
    )

    await supervision.commit_runtime_event(
        db_session, event=second, owner_id=OWNER
    )
    with pytest.raises(supervision.Backpressure):
        await supervision.commit_runtime_event(
            db_session, event=third, owner_id=OWNER
        )
    closed = await supervision.commit_runtime_event(
        db_session, event=first, owner_id=OWNER
    )
    assert closed.committed_through == 2


@pytest.mark.anyio
async def test_restart_watermark_never_jumps_a_committed_gap(db_session):
    session = await _seed_runtime(db_session, run_id="restart-gap-run")
    await supervision.commit_runtime_event(
        db_session, event=_event(session, 3), owner_id=OWNER
    )
    await supervision.commit_runtime_event(
        db_session, event=_event(session, 1), owner_id=OWNER
    )

    assert await supervision.rederive_acked_watermark(
        db_session, run_id=session.run_id
    ) == 1


@pytest.mark.anyio
async def test_512_event_windowed_replay_and_reconnect_has_no_loss_or_duplicate(
    db_session, monkeypatch
):
    session = await _seed_runtime(db_session, run_id="replay-512-run")
    session_id = session.id
    run_id = session.run_id
    provider_session_id = session.provider_session_id
    monkeypatch.setattr(protocol, "MAX_UNACKED_EVENTS", 128)
    monkeypatch.setattr(protocol, "MAX_UNACKED_BYTES", 10_000_000)

    for start in range(1, 513, 128):
        end = start + 127
        batch: list[RuntimeEvent] = []
        for cursor in range(start, end + 1):
            event = _event(session, cursor)
            batch.append(event)
            committed = await supervision.commit_runtime_event(
                db_session, event=event, owner_id=OWNER
            )
            assert committed.duplicate is False
            assert committed.committed_through == cursor

        for index in (0, 31, 63, 95, 127):
            replay = await supervision.commit_runtime_event(
                db_session, event=batch[index], owner_id=OWNER
            )
            assert replay.duplicate is True
            assert replay.committed_through == end

        assert await supervision.record_provider_ack(
            db_session,
            run_id=session.run_id,
            session_id=provider_session_id,
            epoch=EPOCH,
            owner_id=OWNER,
            acked_through=end,
        ) == end

        db_session.expire_all()
        reconnected = await db_session.get(LabRuntimeSession, session_id)
        session = reconnected
        after, remaining_events, remaining_bytes = (
            await supervision.runtime_read_window(
                db_session, session_id=reconnected.id
            )
        )
        assert after == end
        assert remaining_events == 128
        assert remaining_bytes == 10_000_000
        assert await supervision.rederive_acked_watermark(
            db_session, run_id=run_id
        ) == end

    cursors = (
        await db_session.execute(
            select(LabRunEvent.provider_event_id).where(
                LabRunEvent.run_id == run_id,
                LabRunEvent.provider_event_id.isnot(None),
            )
        )
    ).scalars().all()
    assert sorted(int(cursor) for cursor in cursors) == list(range(1, 513))
    assert len(cursors) == len(set(cursors)) == 512
    db_session.expire_all()
    stored_session = await db_session.get(LabRuntimeSession, session_id)
    assert stored_session.provider_cursor_committed == 512
    assert stored_session.provider_cursor_acked == 512


@pytest.mark.anyio
async def test_durable_backpressure_rejects_129th_unacked_event(db_session, monkeypatch):
    session = await _seed_runtime(db_session, run_id="backpressure-run")
    run_id = session.run_id
    monkeypatch.setattr(protocol, "MAX_UNACKED_EVENTS", 128)
    monkeypatch.setattr(protocol, "MAX_UNACKED_BYTES", 10_000_000)
    for cursor in range(1, 129):
        await supervision.commit_runtime_event(
            db_session, event=_event(session, cursor), owner_id=OWNER
        )

    with pytest.raises(supervision.Backpressure):
        await supervision.commit_runtime_event(
            db_session, event=_event(session, 129), owner_id=OWNER
        )
    assert await db_session.scalar(
        select(func.count())
        .select_from(LabRunEvent)
        .where(LabRunEvent.run_id == run_id)
    ) == 128


@pytest.mark.anyio
async def test_durable_byte_window_rebuilds_exact_event_sizes(db_session, monkeypatch):
    session = await _seed_runtime(db_session, run_id="byte-window-run")
    session_id = session.id
    run_id = session.run_id
    first = _event(session, 1, payload={"summary": "a" * 400})
    second = _event(session, 2, payload={"summary": "b" * 600})
    first_size = len(
        protocol.canonical_json(first.model_dump(mode="json")).encode("utf-8")
    )
    second_size = len(
        protocol.canonical_json(second.model_dump(mode="json")).encode("utf-8")
    )
    monkeypatch.setattr(protocol, "MAX_UNACKED_EVENTS", 128)
    monkeypatch.setattr(
        protocol, "MAX_UNACKED_BYTES", first_size + second_size - 1
    )

    await supervision.commit_runtime_event(
        db_session, event=first, owner_id=OWNER
    )
    db_session.expire_all()
    after, remaining_events, remaining_bytes = await supervision.runtime_read_window(
        db_session, session_id=session_id
    )
    assert after == 0
    assert remaining_events == 127
    assert remaining_bytes == second_size - 1
    stored = await db_session.scalar(
        select(LabRunEvent).where(
            LabRunEvent.run_id == run_id,
            LabRunEvent.provider_event_id == "1",
        )
    )
    assert stored.payload_json["runtime_event_bytes"] == first_size

    with pytest.raises(supervision.Backpressure):
        await supervision.commit_runtime_event(
            db_session, event=second, owner_id=OWNER
        )
    assert await db_session.scalar(
        select(func.count())
        .select_from(LabRunEvent)
        .where(LabRunEvent.run_id == run_id)
    ) == 1


@pytest.mark.anyio
async def test_event_loop_closes_reserved_gap_and_acks_full_window(
    db_session, monkeypatch
):
    session = await _seed_runtime(db_session, run_id="event-loop-gap-run")
    session_id = session.id
    run_id = session.run_id
    monkeypatch.setattr(protocol, "MAX_UNACKED_EVENTS", 4)
    monkeypatch.setattr(protocol, "MAX_UNACKED_BYTES", 10_000_000)

    class _GapAdapter:
        def __init__(self):
            self.reads = 0
            self.acks: list[int] = []

        async def read_runtime_events(self, **kwargs):
            self.reads += 1
            if self.reads == 1:
                return RuntimeEventBatch(
                    events=[_event(session, cursor) for cursor in (2, 3, 4)],
                    done=False,
                )
            if self.reads == 2:
                return RuntimeEventBatch(
                    events=[
                        _event(
                            session,
                            1,
                            kind="failed",
                            payload={"reason": "gap closed terminal"},
                        )
                    ],
                    done=False,
                )
            return RuntimeEventBatch(events=[], done=True)

        async def ack_runtime_events(self, *, provider_session_id, cursor):
            self.acks.append(cursor)

        async def send_runtime_result(self, command):
            raise AssertionError("gap-only stream has no result command")

    adapter = _GapAdapter()
    driver = object.__new__(lab_orchestrator._V2Orchestrator)
    driver.db = db_session
    driver.run = await db_session.get(LabRun, run_id)
    driver.run_id = run_id
    driver.runtime_session_id = session_id
    driver.provider_session_id = session.provider_session_id
    driver.owner_id = OWNER
    driver.epoch = EPOCH
    driver.runtime_epoch = EPOCH
    driver.adapter = adapter
    driver.fenced = False
    driver._wall_start_ms = lab_orchestrator._now_ms()
    driver._wall_spent_ms = 0

    with pytest.raises(lab_orchestrator._RunFailed, match="gap closed terminal"):
        await driver._event_loop_v2()

    db_session.expire_all()
    stored = await db_session.get(LabRuntimeSession, session_id)
    assert stored.provider_cursor_committed == 4
    assert stored.provider_cursor_acked == 4
    assert stored.status == "failed"
    assert adapter.acks == [4]
    cursors = (
        await db_session.execute(
            select(LabRunEvent.provider_event_id).where(
                LabRunEvent.run_id == run_id,
                LabRunEvent.provider_event_id.isnot(None),
            )
        )
    ).scalars().all()
    assert sorted(int(cursor) for cursor in cursors) == [1, 2, 3, 4]


@pytest.mark.anyio
async def test_active_takeover_replays_ack_with_runtime_epoch(db_session):
    session = await _seed_runtime(db_session, run_id="active-takeover-ack-run")
    session_id = session.id
    new_owner = "gateway-v2-takeover-owner"
    session.authority_epoch = EPOCH + 1
    lease = await db_session.get(LabRunLease, session.run_id)
    lease.owner_id = new_owner
    lease.fencing_epoch = EPOCH + 1
    lease.heartbeat_at = datetime.now(UTC)
    lease.expires_at = datetime.now(UTC) + timedelta(minutes=5)
    await db_session.commit()
    event = _event(session, 1)

    class _StopProbe(Exception):
        pass

    class _TakeoverAdapter:
        def __init__(self):
            self.acks: list[int] = []
            self.ack_failures = 1

        async def read_runtime_events(self, **kwargs):
            if kwargs["after"] == 0:
                return RuntimeEventBatch(events=[event], done=False)
            raise _StopProbe

        async def ack_runtime_events(self, *, provider_session_id, cursor):
            self.acks.append(cursor)
            if self.ack_failures:
                self.ack_failures -= 1
                raise RuntimeV2RetryableError("events.ack", status_code=503)

        async def send_runtime_result(self, command):
            raise AssertionError("thought replay has no result command")

    adapter = _TakeoverAdapter()
    driver = object.__new__(lab_orchestrator._V2Orchestrator)
    driver.db = db_session
    driver.run = await db_session.get(LabRun, session.run_id)
    driver.run_id = session.run_id
    driver.runtime_session_id = session_id
    driver.provider_session_id = session.provider_session_id
    driver.owner_id = new_owner
    driver.epoch = EPOCH + 1
    driver.runtime_epoch = EPOCH
    driver.adapter = adapter
    driver.fenced = False
    driver._wall_start_ms = lab_orchestrator._now_ms()
    driver._wall_spent_ms = 0

    with pytest.raises(RuntimeV2RetryableError, match="events.ack"):
        await driver._event_loop_v2()
    db_session.expire_all()
    stored = await db_session.get(LabRuntimeSession, session_id)
    assert stored.provider_cursor_committed == 1
    assert stored.provider_cursor_acked == 0

    with pytest.raises(_StopProbe):
        await driver._event_loop_v2()
    db_session.expire_all()
    stored = await db_session.get(LabRuntimeSession, session_id)
    assert stored.fencing_epoch == EPOCH
    assert stored.authority_epoch == EPOCH + 1
    assert stored.provider_cursor_acked == 1
    assert adapter.acks == [1, 1]


@pytest.mark.anyio
async def test_model_token_debit_is_atomic_and_exact_replay_is_free(db_session):
    session = await _seed_runtime(db_session, run_id="model-token-run")
    db_session.add(
        LabRunBudget(
            run_id=session.run_id,
            tenant_id="tenant",
            limit_model_tokens=100,
        )
    )
    await db_session.commit()
    event = _event(
        session,
        1,
        payload={"summary": "metered thought", "model_tokens": 17},
    )

    first = await supervision.commit_runtime_event(
        db_session, event=event, owner_id=OWNER
    )
    replay = await supervision.commit_runtime_event(
        db_session, event=event, owner_id=OWNER
    )

    assert first.model_tokens_charged == 17
    assert replay.duplicate is True
    assert replay.model_tokens_charged == 0
    budget = await db_session.get(LabRunBudget, session.run_id)
    assert budget.used_model_tokens == 17
    ledger_event = await db_session.get(LabRunEvent, first.event_id)
    assert ledger_event.payload_json["runtime_model_usage_charged"] == 17


@pytest.mark.anyio
async def test_broker_result_is_durable_before_delivery_and_receipt_cas(db_session):
    session = await _seed_runtime(db_session, run_id="result-run")
    event = _event(
        session,
        1,
        kind="tool_intent",
        turn_id="turn-result",
        intent_id="intent-result",
    )
    committed = await supervision.commit_runtime_event(
        db_session, event=event, owner_id=OWNER
    )
    action = LabToolAction(
        id="action-result",
        tenant_id="tenant",
        run_id=session.run_id,
        task_id="task-result-run",
        tool_name="web.search",
        args_hash=event.tool_args_digest,
        args_redacted_json=event.tool_args,
        risk_class="R1",
        status="succeeded",
        fencing_epoch=EPOCH,
        policy_version="lab-policy-v2",
        idempotency_key="intent-result",
        result_json={"sentinel": "BROKER-SENTINEL-9F41"},
    )
    db_session.add(action)
    await db_session.commit()

    command = await broker.persist_runtime_result(
        db_session,
        session_id=session.id,
        intent_row_id=committed.intent_row_id,
        action=action,
        owner_id=OWNER,
    )
    row = await db_session.scalar(
        select(LabRuntimeResult).where(
            LabRuntimeResult.command_id == command.command_id
        )
    )
    assert row is not None
    assert row.receipt_id is None
    assert row.runtime_acked_at is None

    receipt = {
        "receipt_id": "runtime-receipt-1",
        "request_digest": protocol.content_digest(command.model_dump(mode="json")),
        "session_id": session.provider_session_id,
        "turn_id": command.turn_id,
        "intent_id": command.intent_id,
        "action_id": command.action_id,
        "state": "runtime_acked",
    }
    await supervision.record_runtime_result_receipt(
        db_session, command=command, receipt=receipt, owner_id=OWNER
    )
    db_session.expire_all()
    row = await db_session.scalar(
        select(LabRuntimeResult).where(
            LabRuntimeResult.command_id == command.command_id
        )
    )
    intent = await db_session.get(LabRuntimeIntent, committed.intent_row_id)
    turn = await db_session.get(LabRuntimeTurn, committed.turn_row_id)
    assert row.receipt_id == "runtime-receipt-1"
    assert row.runtime_acked_at is not None
    assert intent.status == "runtime_acked"
    assert turn.status == "runtime_acked"

    different = dict(receipt, receipt_id="different-receipt")
    with pytest.raises(supervision.RuntimeProtocolConflict):
        await supervision.record_runtime_result_receipt(
            db_session, command=command, receipt=different, owner_id=OWNER
        )


@pytest.mark.anyio
async def test_takeover_reuses_terminal_action_and_exact_runtime_receipt(
    db_session, monkeypatch
):
    session = await _seed_runtime(db_session, run_id="takeover-result-bridge-run")
    session_id = session.id
    run_id = session.run_id
    event = _event(
        session,
        1,
        kind="tool_intent",
        turn_id="takeover-result-turn",
        intent_id="takeover-result-intent",
    )
    committed = await supervision.commit_runtime_event(
        db_session, event=event, owner_id=OWNER
    )
    idempotency_key = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"simverse:v2-intent:{session_id}:{event.intent_id}",
        )
    )
    action = LabToolAction(
        id="takeover-result-action",
        tenant_id="tenant",
        run_id=run_id,
        task_id=f"task-{run_id}",
        tool_name=event.tool_name,
        args_hash=event.tool_args_digest,
        args_redacted_json=event.tool_args,
        risk_class="R1",
        status="succeeded",
        attempts=1,
        fencing_epoch=EPOCH,
        policy_version="lab-policy-v2",
        idempotency_key=idempotency_key,
        result_json={"sentinel": "TAKEOVER-RESULT-SENTINEL"},
    )
    action_id = action.id
    db_session.add(action)
    session.authority_epoch = EPOCH + 1
    new_owner = "gateway-v2-result-takeover"
    lease = await db_session.get(LabRunLease, run_id)
    lease.owner_id = new_owner
    lease.fencing_epoch = EPOCH + 1
    lease.heartbeat_at = datetime.now(UTC)
    lease.expires_at = datetime.now(UTC) + timedelta(minutes=5)
    await db_session.commit()
    monkeypatch.setattr(settings, "lab_grant_secret", "takeover-result-secret")
    token, claims = await grants.issue_run_grant(
        db_session,
        tenant_id="tenant",
        task_id=f"task-{run_id}",
        run_id=run_id,
        agent_id="sage",
        capabilities=["web_search"],
        fencing_epoch=EPOCH + 1,
    )

    driver = object.__new__(lab_orchestrator._V2Orchestrator)
    driver.db = db_session
    driver.run_id = run_id
    driver.runtime_session_id = session_id
    driver.provider_session_id = session.provider_session_id
    driver.owner_id = new_owner
    driver.epoch = EPOCH + 1
    driver.runtime_epoch = EPOCH
    driver.claims = claims
    driver.token = token

    async def forbidden_effect(*args, **kwargs):
        raise AssertionError("a terminal old-epoch effect must never run again")

    driver._select_executor = lambda tool_name: forbidden_effect
    await driver._handle_v2_intent(event, committed)
    await driver._handle_v2_intent(event, committed)

    sent_commands: list[dict] = []

    class _ReceiptAdapter:
        async def send_runtime_result(self, command):
            payload = command.model_dump(mode="json")
            sent_commands.append(payload)
            return {
                "receipt_id": "takeover-stable-receipt",
                "request_digest": protocol.content_digest(payload),
                "session_id": command.session_id,
                "turn_id": command.turn_id,
                "intent_id": command.intent_id,
                "action_id": command.action_id,
                "state": "runtime_acked",
            }

    driver.adapter = _ReceiptAdapter()
    original_record = supervision.record_runtime_result_receipt
    receipt_failures = 1

    async def fail_after_runtime_accepts(*args, **kwargs):
        nonlocal receipt_failures
        if receipt_failures:
            receipt_failures -= 1
            raise RuntimeError("injected Gateway receipt commit failure")
        return await original_record(*args, **kwargs)

    monkeypatch.setattr(
        supervision, "record_runtime_result_receipt", fail_after_runtime_accepts
    )
    with pytest.raises(RuntimeError, match="receipt commit failure"):
        await driver._deliver_pending_results()
    await driver._deliver_pending_results()

    db_session.expire_all()
    stored_action = await db_session.get(LabToolAction, action_id)
    results = (
        await db_session.execute(
            select(LabRuntimeResult).where(
                LabRuntimeResult.session_id == session_id
            )
        )
    ).scalars().all()
    assert stored_action.fencing_epoch == EPOCH
    assert stored_action.attempts == 1
    assert len(results) == 1
    assert results[0].fencing_epoch == EPOCH
    assert results[0].receipt_id == "takeover-stable-receipt"
    assert results[0].runtime_acked_at is not None
    assert len(sent_commands) == 2
    assert sent_commands[0] == sent_commands[1]


@pytest.mark.anyio
async def test_v2_approval_timeout_delivers_canonical_denied_result(
    db_session, monkeypatch
):
    session = await _seed_runtime(db_session, run_id="approval-timeout-run")
    event = _event(
        session,
        1,
        kind="tool_intent",
        turn_id="approval-timeout-turn",
        intent_id="approval-timeout-intent",
    )
    committed = await supervision.commit_runtime_event(
        db_session, event=event, owner_id=OWNER
    )
    action = LabToolAction(
        id="approval-timeout-action",
        tenant_id="tenant",
        run_id=session.run_id,
        task_id="task-approval-timeout-run",
        tool_name=event.tool_name,
        args_hash=event.tool_args_digest,
        args_redacted_json=event.tool_args,
        risk_class="R2",
        status="waiting_approval",
        fencing_epoch=EPOCH,
        policy_version="lab-policy-v2",
        idempotency_key="approval-timeout-intent",
        approval_id="approval-timeout-approval",
    )
    approval = LabApproval(
        id=action.approval_id,
        tenant_id="tenant",
        run_id=session.run_id,
        task_id="task-approval-timeout-run",
        action_id=action.id,
        preview_json={},
        args_digest=event.tool_args_digest,
        decision="pending",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        fencing_epoch=EPOCH,
    )
    budget = LabRunBudget(
        run_id=session.run_id,
        tenant_id="tenant",
        reserved_tool_calls=1,
        reserved_egress_requests=1,
    )
    db_session.add_all([action, approval, budget])
    await db_session.commit()

    async def return_waiting_action(*args, **kwargs):
        return await db_session.get(LabToolAction, action.id)

    async def deny_on_timeout(*args, **kwargs):
        return False

    monkeypatch.setattr(broker, "request_action", return_waiting_action)
    driver = object.__new__(lab_orchestrator._V2Orchestrator)
    driver.db = db_session
    driver.runtime_session_id = session.id
    driver.owner_id = OWNER
    driver.epoch = EPOCH
    driver.claims = object()
    driver.token = "unused-in-test"
    driver._await_approval = deny_on_timeout

    await driver._handle_v2_intent(event, committed)
    action_id = action.id
    approval_id = approval.id
    run_id = session.run_id
    db_session.expire_all()
    stored_action = await db_session.get(LabToolAction, action_id)
    stored_approval = await db_session.get(LabApproval, approval_id)
    stored_budget = await db_session.get(LabRunBudget, run_id)
    result = await db_session.scalar(
        select(LabRuntimeResult).where(
            LabRuntimeResult.runtime_intent_id == committed.intent_row_id
        )
    )
    assert stored_approval.decision == "expired"
    assert stored_action.status == "denied"
    assert stored_action.result_json == {"reason": "approval_timeout"}
    assert result.outcome == "denied"
    assert result.payload_json == {"reason": "approval_timeout"}
    assert result.receipt_id is None
    assert stored_budget.reserved_tool_calls == 0
    assert stored_budget.reserved_egress_requests == 0


@pytest.mark.anyio
async def test_oversized_broker_result_is_terminal_and_effect_runs_once(
    db_session, monkeypatch
):
    session = await _seed_runtime(db_session, run_id="oversized-result-run")
    session_id = session.id
    run_id = session.run_id
    event = _event(
        session,
        1,
        kind="tool_intent",
        turn_id="oversized-turn",
        intent_id="oversized-intent",
    )
    committed = await supervision.commit_runtime_event(
        db_session, event=event, owner_id=OWNER
    )
    monkeypatch.setattr(settings, "lab_grant_secret", "gateway-v2-test-secret")
    token, claims = await grants.issue_run_grant(
        db_session,
        tenant_id="tenant",
        task_id=f"task-{run_id}",
        run_id=run_id,
        agent_id="sage",
        capabilities=["web_search"],
        egress=["search.test"],
        fencing_epoch=EPOCH,
    )
    effects = 0

    async def oversized_effect(tool_name, args):
        nonlocal effects
        effects += 1
        return broker.TrustedEgressResult(
            payload={"payload": [False] * 60_000},
            requests=1,
            bytes=60_000,
        )

    driver = object.__new__(lab_orchestrator._V2Orchestrator)
    driver.db = db_session
    driver.runtime_session_id = session_id
    driver.owner_id = OWNER
    driver.epoch = EPOCH
    driver.claims = claims
    driver.token = token
    driver._select_executor = lambda tool_name, **kwargs: (oversized_effect, None)

    for _ in range(2):
        with pytest.raises(
            broker.RuntimeResultConflict, match="bounded Runtime command"
        ):
            await driver._handle_v2_intent(event, committed)

    assert effects == 1
    actions = (
        await db_session.execute(
            select(LabToolAction).where(
                LabToolAction.run_id == run_id
            )
        )
    ).scalars().all()
    assert len(actions) == 1
    assert actions[0].status == "succeeded"
    assert actions[0].attempts == 1
    assert await db_session.scalar(
        select(func.count())
        .select_from(LabRuntimeResult)
        .where(LabRuntimeResult.session_id == session_id)
    ) == 0


@pytest.mark.anyio
async def test_final_readiness_requires_real_runtime_acked_result(db_session):
    session = await _seed_runtime(db_session, run_id="final-gate-run")
    assert not await supervision.runtime_final_ready(
        db_session, session_id=session.id, require_real_result=True
    )

    event = _event(
        session,
        1,
        kind="tool_intent",
        turn_id="turn-final",
        intent_id="intent-final",
    )
    await supervision.commit_runtime_event(db_session, event=event, owner_id=OWNER)
    assert not await supervision.runtime_final_ready(
        db_session, session_id=session.id, require_real_result=True
    )


@pytest.mark.anyio
async def test_tool_result_event_must_match_persisted_broker_result(db_session):
    session = await _seed_runtime(db_session, run_id="result-event-run")
    intent_event = _event(
        session,
        1,
        kind="tool_intent",
        turn_id="turn-result-event",
        intent_id="intent-result-event",
    )
    committed = await supervision.commit_runtime_event(
        db_session, event=intent_event, owner_id=OWNER
    )
    payload = {"sentinel": "BROKER-RESULT-EVENT"}
    action = LabToolAction(
        id="action-result-event",
        tenant_id="tenant",
        run_id=session.run_id,
        task_id="task-result-event-run",
        tool_name="web.search",
        args_hash=intent_event.tool_args_digest,
        args_redacted_json=intent_event.tool_args,
        risk_class="R1",
        status="succeeded",
        fencing_epoch=EPOCH,
        policy_version="lab-policy-v2",
        idempotency_key="intent-result-event",
        result_json=payload,
    )
    db_session.add(action)
    await db_session.commit()
    command = await broker.persist_runtime_result(
        db_session,
        session_id=session.id,
        intent_row_id=committed.intent_row_id,
        action=action,
        owner_id=OWNER,
    )
    await supervision.record_runtime_result_receipt(
        db_session,
        command=command,
        receipt={
            "receipt_id": "result-event-receipt",
            "request_digest": protocol.content_digest(
                command.model_dump(mode="json")
            ),
            "session_id": command.session_id,
            "turn_id": command.turn_id,
            "intent_id": command.intent_id,
            "action_id": command.action_id,
            "state": "runtime_acked",
        },
        owner_id=OWNER,
    )

    changed = _event(
        session,
        2,
        kind="tool_result",
        turn_id=command.turn_id,
        intent_id=command.intent_id,
        outcome="succeeded",
        payload={"sentinel": "CHANGED"},
    )
    with pytest.raises(supervision.RuntimeProtocolConflict):
        await supervision.commit_runtime_event(
            db_session, event=changed, owner_id=OWNER
        )

    exact = changed.model_copy(
        update={
            "event_id": "exact-result-event",
            "payload": payload,
        }
    )
    accepted = await supervision.commit_runtime_event(
        db_session, event=exact, owner_id=OWNER
    )
    assert accepted.committed_through == 2
    db_session.expire_all()
    turn = await db_session.get(LabRuntimeTurn, committed.turn_row_id)
    assert turn.status == "completed"
    assert turn.completed_at is not None


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", ["denied", "failed"])
async def test_unsuccessful_result_final_is_terminal_but_never_success_ready(
    db_session, outcome
):
    session = await _seed_runtime(db_session, run_id=f"{outcome}-final-run")
    session_id = session.id
    turn = LabRuntimeTurn(
        id=f"{outcome}-turn-row",
        session_id=session.id,
        turn_id=f"{outcome}-turn",
        sequence=1,
        status="runtime_acked",
        provider_cursor=1,
    )
    intent = LabRuntimeIntent(
        id=f"{outcome}-intent-row",
        session_id=session.id,
        runtime_turn_id=turn.id,
        intent_id=f"{outcome}-intent",
        action_id=f"{outcome}-action",
        tool_name="web.search",
        args_digest=protocol.args_digest({"query": outcome}),
        args_redacted_json={"query": outcome},
        status="runtime_acked",
        provider_cursor=1,
        fencing_epoch=EPOCH,
    )
    result = LabRuntimeResult(
        id=f"{outcome}-result-row",
        session_id=session.id,
        runtime_turn_id=turn.id,
        runtime_intent_id=intent.id,
        intent_id=intent.intent_id,
        action_id=intent.action_id,
        command_id=f"{outcome}-command",
        receipt_id=f"{outcome}-receipt",
        outcome=outcome,
        request_digest="a" * 64,
        result_digest=protocol.content_digest({"reason": outcome}),
        payload_json={"reason": outcome},
        fencing_epoch=EPOCH,
        runtime_acked_at=datetime.now(UTC),
    )
    db_session.add_all([turn, intent, result])
    await db_session.commit()

    assert await supervision.runtime_final_ready(
        db_session,
        session_id=session.id,
        require_real_result=True,
        require_succeeded=False,
    )
    assert not await supervision.runtime_final_ready(
        db_session,
        session_id=session.id,
        require_real_result=True,
        require_succeeded=True,
    )
    final = _event(
        session,
        1,
        kind="final",
        turn_id=turn.turn_id,
        payload={"summary": f"{outcome} must not succeed"},
    )
    await supervision.commit_runtime_event(
        db_session, event=final, owner_id=OWNER
    )
    db_session.expire_all()
    assert (await db_session.get(LabRuntimeSession, session_id)).status == "failed"


@pytest.mark.anyio
async def test_final_lease_recheck_rolls_back_every_canonical_row(db_session, monkeypatch):
    session = await _seed_runtime(db_session, run_id="lease-recheck-run")
    db_session.add(
        LabRunBudget(
            run_id=session.run_id,
            tenant_id="tenant",
            limit_model_tokens=100,
        )
    )
    await db_session.commit()
    original = supervision._assert_v2_authority_live
    calls = 0

    async def expire_before_commit(db, *, session, owner_id):
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise supervision.RuntimeProtocolConflict("lease expired before commit")
        await original(db, session=session, owner_id=owner_id)

    monkeypatch.setattr(
        supervision, "_assert_v2_authority_live", expire_before_commit
    )
    with pytest.raises(supervision.RuntimeProtocolConflict):
        await supervision.commit_runtime_event(
            db_session,
            event=_event(
                session,
                1,
                payload={"summary": "rollback", "model_tokens": 11},
            ),
            owner_id=OWNER,
        )
    assert await db_session.scalar(
        select(func.count())
        .select_from(LabRunEvent)
        .where(LabRunEvent.run_id == "lease-recheck-run")
    ) == 0
    budget = await db_session.get(LabRunBudget, "lease-recheck-run")
    assert budget.used_model_tokens == 0


@pytest.mark.anyio
async def test_runtime_timeout_uses_durable_wall_balance(db_session):
    session = await _seed_runtime(db_session, run_id="durable-wall-timeout-run")
    budget = LabRunBudget(
        run_id=session.run_id,
        tenant_id="tenant",
        limit_wall_clock_ms=10_000,
        used_wall_clock_ms=7_000,
        reserved_wall_clock_ms=1_000,
    )
    db_session.add(budget)
    await db_session.commit()

    driver = object.__new__(lab_orchestrator._V2Orchestrator)
    driver.db = db_session
    driver.run_id = session.run_id
    driver.task = type(
        "DeadlineTask",
        (),
        {"deadline_at": datetime.now(UTC) + timedelta(minutes=5)},
    )()
    remaining = await driver._runtime_timeout_seconds()
    assert 1.9 <= remaining <= 2.0

    budget = await db_session.get(LabRunBudget, session.run_id)
    budget.used_wall_clock_ms = 9_000
    budget.reserved_wall_clock_ms = 1_000
    await db_session.commit()
    with pytest.raises(lab_orchestrator._RunFailed, match="runtime_timeout"):
        await driver._runtime_timeout_seconds()


@pytest.mark.anyio
async def test_retryable_runtime_attempts_still_debit_durable_wall_budget(
    db_session, monkeypatch
):
    session = await _seed_runtime(db_session, run_id="retry-wall-budget-run")
    run_id = session.run_id
    budget = LabRunBudget(
        run_id=run_id,
        tenant_id="tenant",
        limit_wall_clock_ms=5_000,
    )
    db_session.add(budget)
    await db_session.commit()
    clock = [0]

    class _RetryingAdapter:
        async def submit_goal_v2(self, *, provider_session_id):
            clock[0] += 1_200
            raise RuntimeV2RetryableError("goal.submit", status_code=503)

    driver = object.__new__(lab_orchestrator._V2Orchestrator)
    driver.db = db_session
    driver.run_id = run_id
    driver.provider_session_id = session.provider_session_id
    driver.adapter = _RetryingAdapter()
    driver.task = type("NoDeadlineTask", (), {"deadline_at": None})()
    monkeypatch.setattr(lab_orchestrator, "_now_ms", lambda: clock[0])

    for expected_used in (1_200, 2_400):
        with pytest.raises(RuntimeV2RetryableError):
            await driver._drive_runtime_v2_bounded()
        db_session.expire_all()
        stored = await db_session.get(LabRunBudget, run_id)
        assert stored.used_wall_clock_ms == expected_used

    assert await driver._runtime_timeout_seconds() == 2.6


@pytest.mark.anyio
async def test_successful_finalization_tail_is_charged(db_session, monkeypatch):
    run, task = await _seed_v2_task_run(
        db_session, run_id="finalization-tail-budget-run", status="running"
    )
    db_session.add(
        LabRunBudget(
            run_id=run.id,
            tenant_id="tenant",
            limit_wall_clock_ms=5_000,
        )
    )
    await db_session.commit()
    run_id = run.id
    clock = [0]
    driver = lab_orchestrator._V2Orchestrator(db_session, run, task)

    async def finalization_tail():
        clock[0] += 375

    driver._succeed = finalization_tail
    monkeypatch.setattr(lab_orchestrator, "_now_ms", lambda: clock[0])

    await driver._finalize_success_v2_bounded()

    db_session.expire_all()
    budget = await db_session.get(LabRunBudget, run_id)
    assert budget.used_wall_clock_ms == 375


@pytest.mark.anyio
async def test_runtime_empty_poll_loop_has_bounded_idle_timeout(
    db_session, monkeypatch
):
    session = await _seed_runtime(db_session, run_id="idle-timeout-run")

    class _IdleAdapter:
        def __init__(self):
            self.submits = 0
            self.reads = 0

        async def submit_goal_v2(self, *, provider_session_id):
            self.submits += 1

        async def read_runtime_events(self, **kwargs):
            self.reads += 1
            return RuntimeEventBatch(events=[], done=False)

        async def ack_runtime_events(self, **kwargs):
            raise AssertionError("an empty stream cannot be ACKed")

        async def send_runtime_result(self, command):
            raise AssertionError("an empty stream has no result command")

    adapter = _IdleAdapter()
    driver = object.__new__(lab_orchestrator._V2Orchestrator)
    driver.db = db_session
    driver.run = await db_session.get(LabRun, session.run_id)
    driver.run_id = session.run_id
    driver.runtime_session_id = session.id
    driver.provider_session_id = session.provider_session_id
    driver.owner_id = OWNER
    driver.epoch = EPOCH
    driver.runtime_epoch = EPOCH
    driver.adapter = adapter
    driver.fenced = False
    driver.task = type("NoDeadlineTask", (), {"deadline_at": None})()
    monkeypatch.setattr(lab_orchestrator, "_V2_IDLE_TIMEOUT_S", 0.01)
    monkeypatch.setattr(settings, "lab_budget_wall_clock_ms", 500)

    started = asyncio.get_running_loop().time()
    with pytest.raises(
        lab_orchestrator._RunFailed, match="runtime_idle_timeout"
    ):
        await driver._drive_runtime_v2_bounded()
    elapsed = asyncio.get_running_loop().time() - started
    assert elapsed < 0.5
    assert adapter.submits == 1
    assert adapter.reads >= 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("protocol_version", "should_requeue"),
    [(1, False), (2, True)],
)
async def test_runner_error_disposition_is_protocol_scoped(
    monkeypatch, protocol_version, should_requeue
):
    dequeues = 0
    dequeue_timeouts: list[float] = []
    requeued: list[tuple[str, int]] = []
    acked: list[tuple[str, int]] = []

    async def dequeue(*, protocol_version, timeout):
        nonlocal dequeues
        dequeues += 1
        dequeue_timeouts.append(timeout)
        if dequeues == 1:
            return "delivery-error-run"
        raise asyncio.CancelledError

    async def processing_error(run_id, *, protocol_version):
        raise RuntimeError("Runtime receipt unavailable")

    async def requeue(run_id, *, protocol_version):
        requeued.append((run_id, protocol_version))

    async def ack(run_id, *, protocol_version):
        acked.append((run_id, protocol_version))

    async def enabled():
        return True

    monkeypatch.setattr(settings, "lab_adapter", "simverse_ref")
    monkeypatch.setattr(settings, "lab_runtime_v2_canary_enabled", True)
    monkeypatch.setattr(queue, "require_legacy_queues_drained", lambda: _async_none())
    monkeypatch.setattr(queue, "dequeue_run", dequeue)
    monkeypatch.setattr(queue, "requeue_run", requeue)
    monkeypatch.setattr(queue, "ack_run", ack)
    monkeypatch.setattr(runner, "_process_run", processing_error)
    monkeypatch.setattr(runner, "_reconcile_v2_processing_safe", _async_none)
    monkeypatch.setattr(
        runner,
        "_claim_v2_queue_run",
        lambda *args, **kwargs: _async_value("queue-claim"),
    )
    monkeypatch.setattr(
        runner,
        "_settle_v2_queue_run",
        lambda *args, **kwargs: _async_none(),
    )
    monkeypatch.setattr("app.lab.is_lab_runtime_enabled", enabled)
    monkeypatch.setattr(runner.asyncio, "sleep", _async_noop)

    await runner.runner_loop(protocol_version=protocol_version)
    assert dequeue_timeouts == [runner._QUEUE_BLOCK_SECONDS] * 2
    assert runner._QUEUE_BLOCK_SECONDS < 5
    if should_requeue:
        assert requeued == [("delivery-error-run", protocol_version)]
        assert acked == []
    else:
        assert requeued == []
        assert acked == [("delivery-error-run", protocol_version)]


@pytest.mark.anyio
async def test_nonretryable_runtime_failure_terminalizes_without_requeue_surface(
    db_session, monkeypatch
):
    run, task = await _seed_v2_task_run(
        db_session, run_id="nonretryable-runtime-run"
    )
    run_id = run.id

    class _NonRetryableAdapter:
        name = "simverse_ref"

        def prepare_protocol_v2(self, **kwargs):
            return None

        async def supervision_handshake(self):
            raise RuntimeV2NonRetryableError("handshake", status_code=400)

    async def no_op(*args, **kwargs):
        return None

    monkeypatch.setattr(
        lab_orchestrator, "get_adapter", lambda name: _NonRetryableAdapter()
    )
    monkeypatch.setattr(lab_orchestrator, "_ws_task_update", no_op)
    monkeypatch.setattr(lab_orchestrator.lab_task_service, "fail_task", no_op)

    await lab_orchestrator._V2Orchestrator(db_session, run, task).execute()

    db_session.expire_all()
    stored = await db_session.get(LabRun, run_id)
    assert stored.status == "failed"
    assert stored.error == "Runtime v2 handshake failed: HTTP 400"


@pytest.mark.anyio
async def test_retryable_runtime_failure_propagates_to_runner_requeue_surface(
    db_session, monkeypatch
):
    run, task = await _seed_v2_task_run(
        db_session, run_id="retryable-runtime-run"
    )
    run_id = run.id

    class _RetryableAdapter:
        name = "simverse_ref"

        def prepare_protocol_v2(self, **kwargs):
            return None

        async def supervision_handshake(self):
            raise RuntimeV2RetryableError("handshake", status_code=503)

    monkeypatch.setattr(
        lab_orchestrator, "get_adapter", lambda name: _RetryableAdapter()
    )

    with pytest.raises(RuntimeV2RetryableError) as exc_info:
        await lab_orchestrator._V2Orchestrator(db_session, run, task).execute()
    assert exc_info.value.retryable is True
    assert exc_info.value.status_code == 503
    db_session.expire_all()
    stored = await db_session.get(LabRun, run_id)
    assert stored.status == "queued"


@pytest.mark.anyio
async def test_takeover_quarantines_missing_runtime_without_replaying_broker_effect(
    db_session, monkeypatch
):
    session = await _seed_runtime(db_session, run_id="takeover-quarantine-run")
    session_id = session.id
    run_id = session.run_id
    task = await db_session.get(LabTask, f"task-{run_id}")
    old_action = LabToolAction(
        id="takeover-existing-action",
        tenant_id="tenant",
        run_id=run_id,
        task_id=task.id,
        tool_name="web.search",
        args_hash=protocol.args_digest({"query": "already executed"}),
        args_redacted_json={"query": "already executed"},
        risk_class="R1",
        status="succeeded",
        attempts=1,
        fencing_epoch=EPOCH,
        policy_version="lab-policy-v2",
        idempotency_key="takeover-existing-action",
        result_json={"sentinel": "OLD-EPOCH-EFFECT"},
    )
    old_action_id = old_action.id
    db_session.add(old_action)
    lease = await db_session.get(LabRunLease, run_id)
    lease.heartbeat_at = datetime(2000, 1, 1, tzinfo=UTC)
    lease.expires_at = datetime(2000, 1, 1, tzinfo=UTC)
    await db_session.commit()
    provider_calls = 0

    class _MissingRuntimeAdapter:
        name = "simverse_ref"

        def prepare_protocol_v2(self, **kwargs):
            return None

        async def supervision_handshake(self):
            nonlocal provider_calls
            provider_calls += 1
            raise RuntimeV2NonRetryableError("handshake", status_code=404)

    async def no_op(*args, **kwargs):
        return None

    monkeypatch.setattr(
        lab_orchestrator, "get_adapter", lambda name: _MissingRuntimeAdapter()
    )
    monkeypatch.setattr(lab_orchestrator, "_ws_task_update", no_op)
    monkeypatch.setattr(lab_orchestrator.lab_task_service, "fail_task", no_op)

    run = await db_session.get(LabRun, run_id)
    await lab_orchestrator._V2Orchestrator(db_session, run, task).execute()

    db_session.expire_all()
    stored_session = await db_session.get(LabRuntimeSession, session_id)
    stored_run = await db_session.get(LabRun, run_id)
    stored_action = await db_session.get(LabToolAction, old_action_id)
    assert stored_session.status == "quarantined"
    assert stored_session.ended_at is not None
    assert stored_session.last_error == "Runtime v2 handshake failed: HTTP 404"
    assert stored_run.status == "failed"
    assert provider_calls == 1
    assert stored_action.status == "succeeded"
    assert stored_action.attempts == 1
    assert stored_action.result_json == {"sentinel": "OLD-EPOCH-EFFECT"}
    assert await db_session.scalar(
        select(func.count())
        .select_from(LabRuntimeResult)
        .where(LabRuntimeResult.session_id == session_id)
    ) == 0


@pytest.mark.anyio
async def test_success_state_and_completed_event_share_one_transaction(
    db_session, monkeypatch
):
    session = await _seed_runtime(db_session, run_id="atomic-final-success-run")
    run_id = session.run_id
    run = await db_session.get(LabRun, run_id)
    task = await db_session.get(LabTask, run.task_id)
    task_id = task.id
    driver = lab_orchestrator._V2Orchestrator(db_session, run, task)
    driver.owner_id = OWNER
    driver.epoch = EPOCH
    driver.runtime_session_id = session.id
    original_append = lab_orchestrator.ledger.append_event

    async def fail_after_staging_event(*args, **kwargs):
        await original_append(*args, **kwargs)
        raise RuntimeV2RetryableError(
            "gateway.run_finalization", status_code=503
        )

    monkeypatch.setattr(
        lab_orchestrator.ledger, "append_event", fail_after_staging_event
    )
    with pytest.raises(RuntimeV2RetryableError, match="run_finalization"):
        await driver._commit_v2_success(summary="atomic summary")

    db_session.expire_all()
    stored_run = await db_session.get(LabRun, run_id)
    stored_task = await db_session.get(LabTask, task_id)
    assert stored_run.status == "running"
    assert stored_task.status == "running"
    assert stored_task.result_summary_md is None
    assert await db_session.scalar(
        select(func.count())
        .select_from(LabRunEvent)
        .where(
            LabRunEvent.run_id == run_id,
            LabRunEvent.type == "run.completed",
        )
    ) == 0

    monkeypatch.setattr(lab_orchestrator.ledger, "append_event", original_append)
    assert await driver._commit_v2_success(summary="atomic summary") is True
    assert await driver._commit_v2_success(summary="atomic summary") is True

    db_session.expire_all()
    stored_run = await db_session.get(LabRun, run_id)
    stored_task = await db_session.get(LabTask, task_id)
    events = (
        await db_session.execute(
            select(LabRunEvent).where(
                LabRunEvent.run_id == run_id,
                LabRunEvent.type == "run.completed",
            )
        )
    ).scalars().all()
    assert stored_run.status == "succeeded"
    assert stored_task.status == "review"
    assert stored_task.accepted_run_id == run_id
    assert stored_task.result_summary_md == "atomic summary"
    assert len(events) == 1
    assert events[0].event_id == driver._v2_finalization_event_id("run.completed")


@pytest.mark.anyio
async def test_fenced_finalizer_cannot_write_any_success_state(db_session):
    session = await _seed_runtime(db_session, run_id="fenced-final-success-run")
    run_id = session.run_id
    task_id = f"task-{run_id}"
    run = await db_session.get(LabRun, run_id)
    task = await db_session.get(LabTask, task_id)
    driver = lab_orchestrator._V2Orchestrator(db_session, run, task)
    driver.owner_id = OWNER
    driver.epoch = EPOCH
    driver.runtime_session_id = session.id

    lease = await db_session.get(LabRunLease, run_id)
    lease.owner_id = "new-finalizer-owner"
    lease.fencing_epoch = EPOCH + 1
    lease.heartbeat_at = datetime.now(UTC)
    lease.expires_at = datetime.now(UTC) + timedelta(minutes=5)
    session.authority_epoch = EPOCH + 1
    await db_session.commit()

    with pytest.raises(lab_orchestrator.leases.StaleEpoch):
        await driver._commit_v2_success(summary="must not commit")

    db_session.expire_all()
    stored_run = await db_session.get(LabRun, run_id)
    stored_task = await db_session.get(LabTask, task_id)
    assert stored_run.status == "running"
    assert stored_task.status == "running"
    assert stored_task.result_summary_md is None
    assert await db_session.scalar(
        select(func.count())
        .select_from(LabRunEvent)
        .where(
            LabRunEvent.run_id == run_id,
            LabRunEvent.type == "run.completed",
        )
    ) == 0


async def _async_none():
    return None


async def _async_value(value):
    return value


async def _async_noop(*args, **kwargs):
    return None


def test_http_adapter_rejects_oversized_and_deep_json_responses():
    oversized = httpx.Response(
        200,
        content=b'{"padding":"' + b"x" * protocol.MAX_COMMAND_BYTES + b'"}',
    )
    with pytest.raises(RuntimeError, match="exceeds byte cap"):
        HttpAgentAdapter._response_object(
            oversized, max_bytes=protocol.MAX_COMMAND_BYTES
        )

    nested: dict = {}
    for _ in range(33):
        nested = {"child": nested}
    deep = httpx.Response(200, json=nested)
    with pytest.raises(RuntimeError, match="JSON depth cap"):
        HttpAgentAdapter._response_object(
            deep, max_bytes=protocol.MAX_COMMAND_BYTES
        )

    valid = {
        "schema_version": 2,
        "event_id": "wire-event",
        "run_id": "wire-run",
        "session_id": "wire-session",
        "cursor": 1,
        "epoch": 0,
        "event_kind": "think",
        "payload": {},
        "occurred_at": "2026-07-21T08:10:56Z",
    }
    parsed = HttpAgentAdapter._runtime_event_from_wire(valid)
    assert parsed.occurred_at.utcoffset() == timedelta(0)
    with pytest.raises(RuntimeV2NonRetryableError) as exc_info:
        HttpAgentAdapter._runtime_event_from_wire({**valid, "cursor": "1"})
    assert exc_info.value.retryable is False


@pytest.mark.parametrize(
    ("uri", "text_md"),
    [(None, None), ("", None), (None, ""), ("  ", "\n")],
)
def test_http_adapter_rejects_title_only_runtime_artifacts(uri, text_md):
    with pytest.raises(RuntimeV2NonRetryableError) as exc_info:
        HttpAgentAdapter._artifact_from_v2_wire({
            "artifact_id": "title-only-artifact",
            "kind": "text",
            "title": "A title is not a deliverable",
            "uri": uri,
            "text_md": text_md,
            "meta": {},
        })
    assert exc_info.value.retryable is False


@pytest.mark.anyio
async def test_v2_artifact_provenance_is_rebuilt_from_gateway_rows(db_session):
    session = await _seed_runtime(db_session, run_id="artifact-provenance-run")
    session_id = session.id
    provider_session_id = session.provider_session_id
    payload = {"sentinel": "GATEWAY-PROVENANCE-SENTINEL"}
    turn = LabRuntimeTurn(
        id="provenance-turn-row",
        session_id=session_id,
        turn_id="provenance-turn",
        sequence=1,
        status="runtime_acked",
        provider_cursor=1,
    )
    intent = LabRuntimeIntent(
        id="provenance-intent-row",
        session_id=session_id,
        runtime_turn_id=turn.id,
        intent_id="provenance-intent",
        action_id="gateway-action",
        tool_name="web.search",
        args_digest=protocol.args_digest({"query": "provenance"}),
        args_redacted_json={"query": "provenance"},
        status="runtime_acked",
        provider_cursor=1,
        fencing_epoch=EPOCH,
    )
    result = LabRuntimeResult(
        id="provenance-result-row",
        session_id=session_id,
        runtime_turn_id=turn.id,
        runtime_intent_id=intent.id,
        intent_id=intent.intent_id,
        action_id=intent.action_id,
        command_id="gateway-command",
        receipt_id="gateway-receipt",
        outcome="succeeded",
        request_digest="b" * 64,
        result_digest=protocol.content_digest(payload),
        payload_json=payload,
        fencing_epoch=EPOCH,
        runtime_acked_at=datetime.now(UTC),
    )
    session.status = "completed"
    db_session.add_all([turn, intent, result])
    await db_session.commit()

    class _ArtifactAdapter:
        async def collect_artifacts_v2(self, *, provider_session_id):
            return [ArtifactSpec(
                kind="text",
                title="runtime report",
                text_md=f"report {payload['sentinel']}",
                meta={
                    "broker_result_digest": "runtime-lie",
                    "broker_result_provenance": {"action_id": "runtime-lie"},
                    "broker_results": [{"command_id": "runtime-lie"}],
                    "runtime_note": "preserved non-authoritative metadata",
                },
            )]

    driver = object.__new__(lab_orchestrator._V2Orchestrator)
    driver.db = db_session
    driver.runtime_session_id = session_id
    driver.provider_session_id = provider_session_id
    driver.adapter = _ArtifactAdapter()
    artifacts = await driver._collect_success_artifacts()
    meta = artifacts[0].meta
    assert meta["broker_result_digest"] == result.result_digest
    assert meta["broker_result_provenance"] == {
        "command_id": result.command_id,
        "intent_id": result.intent_id,
        "action_id": result.action_id,
    }
    assert meta["broker_results"] == [{
        "command_id": result.command_id,
        "intent_id": result.intent_id,
        "action_id": result.action_id,
        "outcome": "succeeded",
        "result_digest": result.result_digest,
    }]

    class _EmptyArtifactAdapter:
        async def collect_artifacts_v2(self, *, provider_session_id):
            return []

    driver.adapter = _EmptyArtifactAdapter()
    with pytest.raises(
        supervision.RuntimeProtocolConflict,
        match="without a deliverable artifact",
    ):
        await driver._collect_success_artifacts()


@pytest.mark.anyio
async def test_http_adapter_v2_round_trip_never_uses_step_stream(tmp_path, monkeypatch):
    issuer = "simverse-gateway"
    current_kid = "runtime-current"
    current_key = "runtime-current-test-secret-at-least-32-bytes"
    next_key = "runtime-next-test-secret-at-least-32-bytes"
    completer = _TwoTurnCompleter()
    app = create_app(
        completer_factory=lambda: completer,
        max_steps=3,
        protocol_version=2,
        runtime_store_path=str(tmp_path / "runtime.sqlite3"),
        service_auth={
            "issuer": issuer,
            "audience": "lab-runtime",
            "keys": {current_kid: current_key, "runtime-next": next_key},
        },
    )
    token_issuer = ServiceTokenIssuer({
        "issuer": issuer,
        "audience": "lab-runtime",
        "current_kid": current_kid,
        "current_key": current_key,
        "token_ttl_seconds": 300,
    })
    adapter = HttpAgentAdapter(
        base_url="http://runtime.test", service_token_issuer=token_issuer
    )
    adapter.name = "simverse_ref"
    spec = RunSpec(
        run_id="adapter-round-trip",
        task_id="task-adapter-round-trip",
        researcher_slug="sage",
        brief="produce a sentinel-backed report",
        scopes=["web_search"],
        budget_usd=0.5,
    )
    client_run_id = "client-adapter-round-trip"
    adapter.prepare_protocol_v2(
        spec=spec, epoch=EPOCH, client_run_id=client_run_id
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://runtime.test"
    ) as client:
        monkeypatch.setattr("app.http.get_client", lambda: client)
        proof = await adapter.supervision_handshake()
        assert proof.manifest.effect_mode == "broker_only"
        binding = await adapter.create_session(
            client_run_id=client_run_id, epoch=EPOCH
        )
        provider_session_id = binding["session_id"]
        await adapter.submit_goal_v2(provider_session_id=provider_session_id)

        after = 0
        intent_event = None
        while intent_event is None:
            page = await adapter.read_runtime_events(
                provider_session_id=provider_session_id,
                after=after,
                limit=2,
                max_bytes=protocol.MAX_UNACKED_BYTES,
            )
            assert page.events
            after = page.events[-1].cursor
            await adapter.ack_runtime_events(
                provider_session_id=provider_session_id, cursor=after
            )
            intent_event = next(
                (
                    event
                    for event in page.events
                    if event.event_kind == "tool_intent"
                ),
                None,
            )
        payload = {"sentinel": "BROKER-ASGI-SENTINEL"}
        command = ToolResultCommand(
            command_id="adapter-result-command",
            run_id=spec.run_id,
            session_id=provider_session_id,
            turn_id=intent_event.turn_id,
            intent_id=intent_event.intent_id,
            action_id="adapter-action",
            outcome="succeeded",
            payload=payload,
            result_digest=protocol.content_digest(payload),
            epoch=EPOCH,
        )
        receipt = await adapter.send_runtime_result(command)
        assert receipt["state"] == "runtime_acked"

        saw_final = False
        saw_result = False
        while not saw_final:
            page = await adapter.read_runtime_events(
                provider_session_id=provider_session_id,
                after=after,
                limit=2,
                max_bytes=protocol.MAX_UNACKED_BYTES,
            )
            assert page.events
            saw_result = saw_result or any(
                event.event_kind == "tool_result" and event.payload == payload
                for event in page.events
            )
            after = page.events[-1].cursor
            await adapter.ack_runtime_events(
                provider_session_id=provider_session_id, cursor=after
            )
            saw_final = any(event.event_kind == "final" for event in page.events)
        assert saw_result
        artifacts = await adapter.collect_artifacts_v2(
            provider_session_id=provider_session_id
        )
        assert len(artifacts) == 1
        assert artifacts[0].provider_artifact_id
        assert artifacts[0].producer_action_id == "adapter-action"
        assert artifacts[0].declared_byte_size
        assert len(artifacts[0].expected_sha256 or "") == 64
    assert completer.calls == 2


@pytest.mark.anyio
async def test_v2_orchestrator_execute_full_sentinel_round_trip(
    db_session, tmp_path, monkeypatch
):
    issuer = "simverse-gateway"
    current_kid = "orchestrator-current"
    current_key = "orchestrator-current-test-secret-at-least-32-bytes"
    next_key = "orchestrator-next-test-secret-at-least-32-bytes"
    completer = _TwoTurnCompleter()
    runtime_app = create_app(
        completer_factory=lambda: completer,
        max_steps=3,
        protocol_version=2,
        runtime_store_path=str(tmp_path / "orchestrator-runtime.sqlite3"),
        service_auth={
            "issuer": issuer,
            "audience": "lab-runtime",
            "keys": {current_kid: current_key, "orchestrator-next": next_key},
        },
    )
    adapter = HttpAgentAdapter(
        base_url="http://runtime.test",
        service_token_issuer=ServiceTokenIssuer({
            "issuer": issuer,
            "audience": "lab-runtime",
            "current_kid": current_kid,
            "current_key": current_key,
            "token_ttl_seconds": 300,
        }),
    )
    adapter.name = "simverse_ref"

    def forbidden_step_stream(*args, **kwargs):
        raise AssertionError("protocol-v2 must never call step_stream")

    adapter.step_stream = forbidden_step_stream
    original_read = adapter.read_runtime_events
    original_ack = adapter.ack_runtime_events
    original_collect = adapter.collect_artifacts_v2
    final_cursor = None
    final_ack_failures = 1
    artifact_read_failures = 1

    async def flaky_read(**kwargs):
        nonlocal final_cursor
        batch = await original_read(**kwargs)
        final_event = next(
            (
                event
                for event in batch.events
                if event.event_kind == "final"
            ),
            None,
        )
        if final_event is not None:
            final_cursor = final_event.cursor
        return batch

    async def flaky_ack(**kwargs):
        nonlocal final_ack_failures
        if (
            final_cursor is not None
            and kwargs.get("cursor") == final_cursor
            and final_ack_failures
        ):
            final_ack_failures -= 1
            raise RuntimeV2RetryableError("events.ack", status_code=503)
        return await original_ack(**kwargs)

    async def flaky_collect(**kwargs):
        nonlocal artifact_read_failures
        if artifact_read_failures:
            artifact_read_failures -= 1
            raise RuntimeV2RetryableError("artifacts.read", status_code=503)
        return await original_collect(**kwargs)

    adapter.read_runtime_events = flaky_read
    adapter.ack_runtime_events = flaky_ack
    adapter.collect_artifacts_v2 = flaky_collect
    run_id = "orchestrator-v2-e2e-run"
    task_id = "orchestrator-v2-e2e-task"
    task = LabTask(
        id=task_id,
        issuer_user_id="orchestrator-v2-issuer",
        researcher_slug="sage",
        title="v2 sentinel report",
        brief_md="produce a sentinel-backed report",
        scopes_json=["web_search"],
        status="assigned",
        accepted_run_id=run_id,
        deliverable_kind="report",
    )
    run = LabRun(
        id=run_id,
        task_id=task_id,
        researcher_slug="sage",
        adapter="simverse_ref",
        protocol_version=2,
        status="queued",
        scopes_json=["web_search"],
        budget_usd_cents=50,
    )
    db_session.add_all([task, run])
    await db_session.commit()

    async def no_ws(*args, **kwargs):
        return None

    async def sentinel_executor(tool_name, args):
        assert tool_name == "web.search"
        assert args == {"query": "approved-v10 sentinel"}
        return broker.TrustedEgressResult(
            payload={"sentinel": "BROKER-FULL-E2E-SENTINEL", "ok": True},
            requests=1,
            bytes=48,
        )

    monkeypatch.setattr(settings, "lab_grant_secret", "gateway-v2-grant-secret")
    monkeypatch.setattr(settings, "lab_egress_allowlist", ["search.test"])
    monkeypatch.setattr(lab_orchestrator, "get_adapter", lambda name: adapter)
    monkeypatch.setattr(lab_orchestrator, "_ws_task_update", no_ws)
    monkeypatch.setattr(lab_orchestrator, "_ws_run_step", no_ws)
    monkeypatch.setattr(lab_orchestrator, "_ws_run_approval", no_ws)

    async def persist_at_pipeline_boundary(driver, artifacts):
        existing = (
            await driver.db.execute(
                select(LabArtifact).where(LabArtifact.run_id == driver.run_id)
            )
        ).scalars().all()
        if existing:
            return existing
        spec = artifacts[0]
        text = "BROKER-FULL-E2E-SENTINEL"
        artifact = LabArtifact(
            run_id=driver.run_id,
            task_id=driver.task_id,
            kind=spec.kind,
            title=spec.title,
            text_md=text,
            meta_json=spec.meta,
            tenant_id=driver.tenant_id,
            provider_artifact_id=spec.provider_artifact_id,
            runtime_session_id=driver.runtime_session_id,
            provider_session_id=driver.provider_session_id,
            producer_epoch=driver.runtime_epoch,
            required=spec.required,
            declared_content_type=spec.content_type,
            content_type=spec.content_type,
            expected_sha256=hashlib.sha256(text.encode()).hexdigest(),
            declared_byte_size=len(text.encode()),
            sha256=hashlib.sha256(text.encode()).hexdigest(),
            byte_size=len(text.encode()),
            producer_action_id=spec.producer_action_id,
            provenance="runtime",
            storage_status="legacy",
        )
        driver.db.add(artifact)
        budget = await driver.db.get(LabRunBudget, driver.run_id)
        budget.used_artifact_count += 1
        budget.used_artifact_bytes += artifact.byte_size
        await driver.db.commit()
        return [artifact]

    monkeypatch.setattr(
        lab_orchestrator._V2Orchestrator,
        "_persist_v2_artifacts",
        persist_at_pipeline_boundary,
    )

    driver = lab_orchestrator._V2Orchestrator(db_session, run, task)
    driver._select_executor = lambda tool_name, **kwargs: (sentinel_executor, None)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=runtime_app),
        base_url="http://runtime.test",
    ) as client:
        monkeypatch.setattr("app.http.get_client", lambda: client)
        with pytest.raises(RuntimeV2RetryableError, match="events.ack"):
            await driver.execute()

        db_session.expire_all()
        runtime_session = await db_session.scalar(
            select(LabRuntimeSession).where(LabRuntimeSession.run_id == run_id)
        )
        assert runtime_session.status == "completed"
        assert runtime_session.provider_cursor_acked < (
            runtime_session.provider_cursor_committed
        )
        lease = await db_session.get(LabRunLease, run_id)
        lease.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.commit()

        run = await db_session.get(LabRun, run_id)
        task = await db_session.get(LabTask, task_id)
        restarted = lab_orchestrator._V2Orchestrator(db_session, run, task)

        async def forbidden_executor(*args, **kwargs):
            raise AssertionError("completed recovery cannot execute a new effect")

        restarted._select_executor = lambda tool_name: forbidden_executor
        with pytest.raises(RuntimeV2RetryableError, match="artifacts.read"):
            await restarted.execute()

        original_finalize_event = restarted._emit_v2_finalization_once
        artifact_event_failures = 1

        async def fail_after_artifact_event_commit(*, type, payload):
            nonlocal artifact_event_failures
            await original_finalize_event(type=type, payload=payload)
            if type == "artifact.emitted" and artifact_event_failures:
                artifact_event_failures -= 1
                raise RuntimeV2RetryableError(
                    "gateway.artifact_finalization", status_code=503
                )

        restarted._emit_v2_finalization_once = fail_after_artifact_event_commit
        with pytest.raises(
            RuntimeV2RetryableError, match="gateway.artifact_finalization"
        ):
            await restarted.execute()

        adapter.collect_artifacts_v2 = original_collect
        await restarted.execute()

    db_session.expire_all()
    stored_run = await db_session.get(LabRun, run_id)
    stored_task = await db_session.get(LabTask, task_id)
    runtime_session = await db_session.scalar(
        select(LabRuntimeSession).where(LabRuntimeSession.run_id == run_id)
    )
    result = await db_session.scalar(
        select(LabRuntimeResult).where(
            LabRuntimeResult.session_id == runtime_session.id
        )
    )
    artifact = await db_session.scalar(
        select(LabArtifact).where(LabArtifact.run_id == run_id)
    )
    assert stored_run.status == "succeeded"
    assert stored_task.status == "review"
    assert runtime_session.status == "completed"
    assert result.outcome == "succeeded"
    assert result.runtime_acked_at is not None
    assert result.payload_json["sentinel"] == "BROKER-FULL-E2E-SENTINEL"
    assert "BROKER-FULL-E2E-SENTINEL" in artifact.text_md
    assert artifact.meta_json["broker_result_digest"] == result.result_digest
    assert artifact.meta_json["broker_result_provenance"] == {
        "command_id": result.command_id,
        "intent_id": result.intent_id,
        "action_id": result.action_id,
    }
    budget = await db_session.get(LabRunBudget, run_id)
    assert budget.used_artifact_count == 1
    assert budget.used_artifact_bytes == artifact.byte_size
    assert await db_session.scalar(
        select(func.count())
        .select_from(LabRunEvent)
        .where(
            LabRunEvent.run_id == run_id,
            LabRunEvent.type == "artifact.emitted",
        )
    ) == 1
    assert await db_session.scalar(
        select(func.count())
        .select_from(LabRunEvent)
        .where(
            LabRunEvent.run_id == run_id,
            LabRunEvent.type == "run.completed",
        )
    ) == 1
    provider_ids = (
        await db_session.execute(
            select(LabRunEvent.provider_event_id).where(
                LabRunEvent.run_id == run_id,
                LabRunEvent.provider_event_id.isnot(None),
            )
        )
    ).scalars().all()
    assert provider_ids
    assert all(value.isdecimal() for value in provider_ids)
    assert (await db_session.get(LabRunLease, run_id)).fencing_epoch == 1
    assert completer.calls == 2
