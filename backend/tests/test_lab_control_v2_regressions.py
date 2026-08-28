"""Approved-v10 P4 control-plane regressions.

These tests deliberately describe the durable v2 contract rather than the
legacy in-process ``adapter.cancel(handle=None)`` path.  Imports for the new
contract stay inside fixtures/tests so the pre-P4 tree still collects cleanly
and fails at execution with a useful missing-contract error.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.models.lab_event import OutboxEvent
from app.models.lab_run import LabRun
from app.models.user import User


pytestmark = pytest.mark.anyio


class _RedisUnavailable:
    """Fail every Redis operation: DB polling must remain the control truth."""

    def __getattr__(self, name):
        async def _down(*args, **kwargs):
            raise ConnectionError(f"redis unavailable during {name}")

        return _down


class _RecordingController:
    def __init__(self, *, unreachable: set[str] | None = None):
        self.unreachable = unreachable or set()
        self.commands: list[dict] = []

    async def __call__(self, command: dict) -> dict:
        self.commands.append(dict(command))
        target_id = command["target_id"]
        if target_id in self.unreachable:
            return {
                "status": "unreachable",
                "error": "injected target outage",
            }
        return {
            "status": "confirmed_stopped",
            "receipt_id": f"receipt:{command['request_id']}:{target_id}",
            "observed_at": datetime.now(UTC).isoformat(),
        }


@pytest.fixture
async def control_factory(monkeypatch):
    # Contract imports are intentionally delayed: 77b64c2 has neither module.
    import app.models.lab_control  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    monkeypatch.setattr(settings, "lab_agent_v2_enabled", True, raising=False)
    monkeypatch.setattr(settings, "lab_global_admission_enabled", True, raising=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_run(factory, run_id: str, *, status: str = "running") -> User:
    async with factory() as db:
        admin = User(
            id=f"admin-{run_id}",
            name="Lab admin",
            email=f"admin-{run_id}@control.test",
            is_admin=True,
        )
        db.add(admin)
        db.add(
            LabRun(
                id=run_id,
                task_id=f"task-{run_id}",
                researcher_slug="sage",
                adapter="hermes",
                protocol_version=2,
                status=status,
                scopes_json=["web_search"],
            )
        )
        await db.commit()
        return admin


async def _register_runtime_and_executor(factory, run_id: str, *, epoch: int = 7) -> None:
    from app.lab import control_plane

    async with factory() as db:
        await control_plane.register_runtime_target(
            db,
            run_id=run_id,
            session_id=f"session-{run_id}",
            locator={"provider": "hermes", "handle": f"runtime-{run_id}"},
            epoch=epoch,
        )
        await control_plane.register_executor_target(
            db,
            run_id=run_id,
            action_id=f"action-{run_id}",
            job_locator={"job_id": f"job-{run_id}", "epoch": epoch},
            epoch=epoch,
        )
        await db.commit()


async def test_admin_cancel_persists_one_pending_request_and_never_builds_a_null_handle(
    control_factory, monkeypatch
):
    """The API submits intent; only the lease-owning Runner touches providers."""
    from app.lab import sandbox
    from app.models.lab_control import LabRunControlRequest
    from app.routers.admin.lab import cancel_run

    factory = control_factory
    admin = await _seed_run(factory, "run-api")

    def _forbidden_adapter_lookup(*args, **kwargs):
        raise AssertionError("the API must not construct an adapter or handle")

    monkeypatch.setattr(sandbox, "get_adapter", _forbidden_adapter_lookup)

    async with factory() as db:
        first = await cancel_run("run-api", admin=admin, db=db)
    async with factory() as db:
        second = await cancel_run("run-api", admin=admin, db=db)

    assert first["status"] == "pending"
    assert second["status"] == "pending"
    assert second["control_request_id"] == first["control_request_id"]

    async with factory() as db:
        requests = (
            await db.execute(
                select(LabRunControlRequest).where(
                    LabRunControlRequest.run_id == "run-api"
                )
            )
        ).scalars().all()
        outbox = (
            await db.execute(
                select(OutboxEvent).where(
                    OutboxEvent.run_id == "run-api",
                    OutboxEvent.topic == "lab_control",
                )
            )
        ).scalars().all()
        run = await db.get(LabRun, "run-api")

    assert len(requests) == 1
    request = requests[0]
    assert request.id == first["control_request_id"]
    assert request.action == "cancel"
    assert request.status == "pending"
    assert request.requested_by == admin.id
    assert request.claim_owner is None
    assert request.attempts == 0
    assert request.fenced_at is None
    assert request.provider_stopped_at is None
    assert request.executor_stopped_at is None
    assert run.status == "running", "API intent must not fabricate provider completion"

    assert len(outbox) == 1
    assert outbox[0].published_at is None
    assert outbox[0].payload_json == {
        "request_id": request.id,
        "run_id": "run-api",
        "action": "cancel",
        "epoch": request.fencing_epoch,
    }


async def test_durable_cancel_is_polled_after_redis_loss_and_runner_restart(
    control_factory,
):
    """Losing the wakeup cannot lose the DB request or duplicate target effects."""
    from app.lab import control_plane
    from app.models.lab_control import LabControlTarget, LabRunControlRequest
    from app.redis_client import set_redis
    from app.routers.admin.lab import cancel_run

    factory = control_factory
    admin = await _seed_run(factory, "run-restart")
    await _register_runtime_and_executor(factory, "run-restart", epoch=11)

    set_redis(_RedisUnavailable())
    try:
        async with factory() as db:
            response = await cancel_run("run-restart", admin=admin, db=db)
    finally:
        # The restarted Runner may have a fresh Redis client, but correctness is
        # proved by polling with a newly-created DB session below.
        set_redis(None)

    runtime = _RecordingController()
    executor = _RecordingController()
    async with factory() as restarted_db:
        stats = await control_plane.process_pending_controls(
            restarted_db,
            owner_id="runner-after-restart",
            controllers={"runtime": runtime, "executor": executor},
            now=datetime.now(UTC),
        )

    assert stats == {
        "claimed": 1,
        "completed": 1,
        "quarantined": 0,
        "targets_confirmed": 2,
    }
    assert {command["target_kind"] for command in runtime.commands + executor.commands} == {
        "runtime",
        "executor",
    }
    assert all(command["request_id"] == response["control_request_id"] for command in runtime.commands + executor.commands)

    async with factory() as db:
        request = await db.get(LabRunControlRequest, response["control_request_id"])
        targets = (
            await db.execute(
                select(LabControlTarget).where(
                    LabControlTarget.request_id == request.id
                )
            )
        ).scalars().all()

    assert request.status == "completed"
    assert request.claim_owner == "runner-after-restart"
    assert request.fenced_at is not None
    assert request.provider_stopped_at is not None
    assert request.executor_stopped_at is not None
    assert request.fenced_at <= request.provider_stopped_at
    assert request.fenced_at <= request.executor_stopped_at
    assert len(targets) == 2
    assert {target.target_kind for target in targets} == {"runtime", "executor"}
    assert {target.status for target in targets} == {"confirmed_stopped"}
    assert all(target.receipt_json["receipt_id"] for target in targets)

    # A later polling pass sees terminal durable state and emits no second effect.
    async with factory() as db:
        again = await control_plane.process_pending_controls(
            db,
            owner_id="runner-after-restart",
            controllers={"runtime": runtime, "executor": executor},
            now=datetime.now(UTC) + timedelta(seconds=1),
        )
    assert again["claimed"] == 0
    assert len(runtime.commands) == 1
    assert len(executor.commands) == 1


async def test_running_cancel_without_runtime_inventory_is_quarantined(
    control_factory,
):
    """Missing durable provider truth can never be reported as stopped."""
    from app.lab import control_plane
    from app.models.lab_control import LabControlTarget, LabRunControlRequest

    factory = control_factory
    await _seed_run(factory, "run-missing-runtime", status="running")
    now = datetime.now(UTC)
    async with factory() as db:
        request = await control_plane.submit_run_control(
            db,
            run_id="run-missing-runtime",
            requested_by="admin",
            deadline_at=now + timedelta(seconds=30),
            now=now,
        )

    async with factory() as db:
        stats = await control_plane.process_pending_controls(
            db,
            owner_id="runner-missing-runtime",
            controllers={"runtime": _RecordingController(), "executor": _RecordingController()},
            now=now,
        )

    async with factory() as db:
        stored = await db.get(LabRunControlRequest, request.id)
        run = await db.get(LabRun, "run-missing-runtime")
        targets = (
            await db.execute(
                select(LabControlTarget).where(
                    LabControlTarget.request_id == request.id
                )
            )
        ).scalars().all()

    assert stats["completed"] == 0
    assert stats["quarantined"] == 1
    assert stored.status == "quarantined"
    assert run.status == "running"
    assert len(targets) == 1
    assert targets[0].status == "quarantined"
    assert targets[0].last_error == "runtime target inventory missing"


async def test_global_kill_state_and_target_materialization_are_one_transaction(
    control_factory, monkeypatch
):
    """A target-build fault must not leave admission closed without fanout truth."""
    from app.lab import control_plane
    from app.models.lab_control import LabGlobalControl, LabGlobalKill

    factory = control_factory
    await _seed_run(factory, "run-atomic")
    await _register_runtime_and_executor(factory, "run-atomic", epoch=3)

    async def _explode(*args, **kwargs):
        raise RuntimeError("injected target materialization fault")

    monkeypatch.setattr(control_plane, "_materialize_global_kill_targets", _explode)

    async with factory() as db:
        with pytest.raises(RuntimeError, match="materialization"):
            await control_plane.activate_global_kill(
                db,
                requested_by="admin",
                idempotency_key="kill-atomic",
                deadline_at=datetime.now(UTC) + timedelta(seconds=30),
                now=datetime.now(UTC),
            )
        await db.rollback()

    async with factory() as db:
        state = await db.get(LabGlobalControl, "global")
        kills = (await db.execute(select(func.count()).select_from(LabGlobalKill))).scalar_one()

    assert state is None or (
        state.admission_open is True
        and state.fencing_epoch == 0
        and state.active_kill_id is None
    )
    assert kills == 0


async def test_global_kill_closes_admission_advances_epoch_and_fans_out_both_planes(
    control_factory,
):
    """The persisted target set is complete before any provider call is made."""
    from app.lab import control_plane
    from app.models.lab_control import LabControlTarget, LabGlobalControl

    factory = control_factory
    for run_id in ("run-one", "run-two"):
        await _seed_run(factory, run_id)
        await _register_runtime_and_executor(factory, run_id, epoch=5)

    now = datetime.now(UTC)
    async with factory() as db:
        kill = await control_plane.activate_global_kill(
            db,
            requested_by="admin",
            idempotency_key="kill-complete-inventory",
            deadline_at=now + timedelta(seconds=30),
            now=now,
        )

    async with factory() as db:
        state = await db.get(LabGlobalControl, "global")
        targets = (
            await db.execute(
                select(LabControlTarget).where(LabControlTarget.kill_id == kill.id)
            )
        ).scalars().all()

        with pytest.raises(control_plane.AdmissionClosed):
            await control_plane.assert_admission_allowed(
                db, expected_global_epoch=kill.fencing_epoch - 1
            )

    assert state.admission_open is False
    assert state.fencing_epoch == kill.fencing_epoch == 1
    assert state.active_kill_id == kill.id
    assert kill.watermark_run_count == 2
    assert len(targets) == 4
    assert {(target.run_id, target.target_kind) for target in targets} == {
        ("run-one", "runtime"),
        ("run-one", "executor"),
        ("run-two", "runtime"),
        ("run-two", "executor"),
    }
    assert {target.status for target in targets} == {"pending"}
    assert {
        (target.target_kind, target.epoch) for target in targets
    } == {
        ("runtime", kill.fencing_epoch),
        ("executor", 5),
    }


async def test_global_kill_nominal_has_no_quarantine(control_factory):
    """Every nominal Runtime and Executor target must confirm stopped."""
    from app.lab import control_plane

    factory = control_factory
    await _seed_run(factory, "run-nominal")
    await _register_runtime_and_executor(factory, "run-nominal", epoch=1)

    async with factory() as db:
        nominal = await control_plane.activate_global_kill(
            db,
            requested_by="admin",
            idempotency_key="kill-nominal",
            deadline_at=datetime.now(UTC) + timedelta(seconds=30),
            now=datetime.now(UTC),
        )
    runtime = _RecordingController()
    executor = _RecordingController()
    async with factory() as db:
        nominal_stats = await control_plane.process_global_kill(
            db,
            kill_id=nominal.id,
            owner_id="runner-nominal",
            controllers={"runtime": runtime, "executor": executor},
            now=datetime.now(UTC),
        )
    assert nominal_stats["confirmed_stopped"] == 2
    assert nominal_stats["quarantined"] == 0
    assert nominal_stats["pending"] == 0


async def test_global_kill_fault_quarantines_only_the_injected_target(control_factory):
    """Fault quarantine is not a relaxed version of the nominal oracle."""
    from app.lab import control_plane
    from app.models.lab_control import LabControlTarget

    factory = control_factory
    await _seed_run(factory, "run-fault")
    await _register_runtime_and_executor(factory, "run-fault", epoch=2)
    async with factory() as db:
        fault = await control_plane.activate_global_kill(
            db,
            requested_by="admin",
            idempotency_key="kill-fault",
            deadline_at=datetime.now(UTC) + timedelta(seconds=30),
            now=datetime.now(UTC),
        )

    runtime_fault = _RecordingController(unreachable={"session-run-fault"})
    executor_ok = _RecordingController()
    async with factory() as db:
        fault_stats = await control_plane.process_global_kill(
            db,
            kill_id=fault.id,
            owner_id="runner-fault",
            controllers={"runtime": runtime_fault, "executor": executor_ok},
            now=datetime.now(UTC) + timedelta(seconds=31),
        )
    assert fault_stats["confirmed_stopped"] == 1
    assert fault_stats["quarantined"] == 1
    assert fault_stats["pending"] == 0

    async with factory() as db:
        targets = (
            await db.execute(
                select(LabControlTarget).where(LabControlTarget.kill_id == fault.id)
            )
        ).scalars().all()
    quarantined = [target for target in targets if target.status == "quarantined"]
    stopped = [target for target in targets if target.status == "confirmed_stopped"]
    assert [(target.target_kind, target.target_id) for target in quarantined] == [
        ("runtime", "session-run-fault")
    ]
    assert quarantined[0].stopped_at is None
    assert quarantined[0].quarantined_at is not None
    assert [(target.target_kind, target.target_id) for target in stopped] == [
        ("executor", "action-run-fault")
    ]


async def test_global_epoch_rejects_every_stale_effect_class(control_factory):
    """One fence epoch covers Runtime, Broker, Executor, world, and old actions."""
    from app.lab import control_plane

    factory = control_factory
    await _seed_run(factory, "run-stale")
    await _register_runtime_and_executor(factory, "run-stale", epoch=0)
    async with factory() as db:
        kill = await control_plane.activate_global_kill(
            db,
            requested_by="admin",
            idempotency_key="kill-stale-effects",
            deadline_at=datetime.now(UTC) + timedelta(seconds=30),
            now=datetime.now(UTC),
        )

    denied = set()
    async with factory() as db:
        for effect in ("runtime", "broker", "executor", "world", "old_action"):
            with pytest.raises(control_plane.StaleEffect) as error:
                await control_plane.assert_effect_epoch(
                    db,
                    run_id="run-stale",
                    expected_global_epoch=kill.fencing_epoch - 1,
                    effect=effect,
                )
            denied.add(error.value.effect)

        current = await control_plane.assert_effect_epoch(
            db,
            run_id="run-stale",
            expected_global_epoch=kill.fencing_epoch,
            effect="terminalization",
        )

    assert denied == {"runtime", "broker", "executor", "world", "old_action"}
    assert current == kill.fencing_epoch
