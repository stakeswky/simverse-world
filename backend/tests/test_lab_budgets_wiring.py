"""P2-C — the other six budget dimensions wired into the live broker /
orchestrator paths (PRD §Hard Budgets, V10 「每维独立触发」).

Only ``tool_calls`` (broker.request_action) and ``artifact_count``
(orchestrator._succeed) had a live spend path before this task. Here we pin the
remaining six — ``model_tokens`` / ``wall_clock_ms`` / ``active_workers`` in the
orchestrator, ``egress_requests`` / ``egress_bytes`` in the broker, and
``artifact_bytes`` in ``_succeed`` — each independently triggerable on Mock by
squeezing its own limit, and each driving the ONE existing budget-termination
path: a ``budget.exhausted`` event carrying the dimension, every grant revoked,
the run ``failed`` with ``error == budget_exhausted:{dim}``, and the task
refunded. ``active_workers`` also gets a normal-terminal release assertion
(reserved returns to 0) because a single Mock worker can never exhaust it.

Setup mirrors test_lab_e2e: the orchestrator + services open their own
``async_session`` patched onto the shared in-memory engine; runs are driven
through ``runner.run_one`` with ``lab_agent_v1_enabled`` on.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.lab import broker, budgets
from app.lab.runner import run_one
from app.lab.sandbox.base import ArtifactSpec, SandboxHandle, StepEvent
from app.models.lab_budget import LabRunBudget
from app.models.lab_event import LabRunEvent
from app.models.lab_grant import LabCapabilityGrant
from app.models.lab_run import LabRun
from app.models.lab_task import LabTask
from app.models.resident import Resident
from app.models.user import User
from app.services import coin_service
from app.services import lab_task_service as svc


# ── fixtures (mirror test_lab_e2e.lab_env) ────────────────────────────

@pytest.fixture
def lab_env(db_engine, monkeypatch):
    from app.config import settings
    for k, v in {
        "lab_enabled": True, "lab_adapter": "mock", "lab_creator_share": 0.2,
        "lab_platform_fee_rate": 0.1, "lab_default_budget_usd": 0.5,
        "lab_daily_tasks_per_user": 20, "lab_auto_release_hours": 72,
        "lab_task_deadline_hours": 24,
        "lab_agent_v1_enabled": True, "lab_grant_secret": "test-secret",
        "lab_approval_timeout_s": 5, "lab_egress_allowlist": ["*.example.org"],
    }.items():
        monkeypatch.setattr(settings, k, v, raising=False)
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    with patch("app.lab.runner.async_session", factory), \
         patch("app.lab.orchestrator.async_session", factory), \
         patch("app.services.lab_task_service.async_session", factory), \
         patch("app.services.lab_task_service.emit", new_callable=AsyncMock):
        yield factory


async def _seed(factory, *, issuer_balance=1000):
    async with factory() as s:
        s.add(User(id="issuer", name="Issuer", email="i@t.com", soul_coin_balance=issuer_balance))
        s.add(User(id="creator_user", name="Creator", email="c@t.com", soul_coin_balance=0))
        s.add(Resident(
            slug="sage", name="Sage", creator_id="creator_user", resident_type="npc",
            meta_json={"lab": {"access": True, "tier": "senior", "skills": ["web_search"]}},
        ))
        await s.commit()


async def _make_task(factory, *, scopes, reward_sc=100, deliverable_kind="report", title="预算任务"):
    async with factory() as s:
        task = await svc.create_task(
            s, issuer_id="issuer", title=title, brief="调研一下 X",
            scopes=scopes, reward_sc=reward_sc, deliverable_kind=deliverable_kind,
            researcher_slug="sage",
        )
        return task.id, task.accepted_run_id


async def _event_types(factory, run_id):
    async with factory() as s:
        rows = (await s.execute(
            select(LabRunEvent).where(LabRunEvent.run_id == run_id).order_by(LabRunEvent.seq)
        )).scalars().all()
        return [(e.type, e.payload_json) for e in rows]


async def _assert_budget_termination(factory, task_id, run_id, dimension):
    """The shared shape every one of the six exhaustion paths must produce."""
    async with factory() as s:
        run = await s.get(LabRun, run_id)
        assert run.status == "failed"
        assert run.error == f"budget_exhausted:{dimension}"
        task = await s.get(LabTask, task_id)
        assert task.status == "failed"
        assert await coin_service.get_balance(s, "issuer") == 1000  # fully refunded

        gr = (await s.execute(
            select(LabCapabilityGrant).where(LabCapabilityGrant.run_id == run_id)
        )).scalars().all()
        assert gr and all(g.revoked_at is not None for g in gr)  # every grant revoked

        budget = await s.get(LabRunBudget, run_id)
        assert budget.exhausted_dimension == dimension

    events = await _event_types(factory, run_id)
    types = [t for t, _ in events]
    assert "budget.exhausted" in types and "run.failed" in types
    exhausted = [p for t, p in events if t == "budget.exhausted"]
    assert exhausted and exhausted[-1]["dimension"] == dimension


# ── fake adapters ─────────────────────────────────────────────────────

class _FakeHandle(SandboxHandle):
    def __init__(self, spec):
        self.spec = spec


class _BaseFake:
    name = "mock"

    async def start(self, spec):
        return _FakeHandle(spec)

    async def submit_goal(self, handle, brief, scopes):
        return None

    async def approve(self, handle, approval_id, decision):
        return None

    async def collect_artifacts(self, handle):
        return [ArtifactSpec(kind="text", title="研究简报（Fake）", text_md="done", meta={"fake": True})]

    async def stop(self, handle):
        return None


class FakePlainAdapter(_BaseFake):
    """Two non-tool steps, no declared model_tokens — trips nothing on its own.
    Base for the wall_clock / artifact_bytes / active_workers scenarios."""

    async def step_stream(self, handle):
        yield StepEvent(phase="think", summary="规划")
        yield StepEvent(phase="message", summary="收尾")


class FakeModelTokensAdapter(_BaseFake):
    """One think step declaring a large model_tokens count."""

    async def step_stream(self, handle):
        yield StepEvent(phase="think", summary="规划", model_tokens=500)
        yield StepEvent(phase="message", summary="收尾")


class FakeEgressAdapter(_BaseFake):
    """Two allow-passthrough browser.navigate (browse) egress steps to
    example.org — no approval pause, so egress budgets can be driven directly."""

    async def step_stream(self, handle):
        yield StepEvent(phase="think", summary="需要访问两个来源")
        yield StepEvent(phase="tool_call", tool="browser.navigate", summary="打开来源甲",
                        payload={"url": "https://example.org/a"}, cost_usd_cents=1)
        yield StepEvent(phase="tool_call", tool="browser.navigate", summary="打开来源乙",
                        payload={"url": "https://example.org/b"}, cost_usd_cents=1)
        yield StepEvent(phase="message", summary="收尾")


async def _trusted_test_egress_executor(tool_name: str, args: dict):
    return broker.TrustedEgressResult(
        payload={
            "tool": tool_name,
            "ok": True,
            "summary": f"executed {tool_name} (trusted test egress)",
        },
        requests=1,
        bytes=64,
    )


def _make_clock(step_ms):
    """A monotonic-ms source that advances a fixed amount on every read, so the
    Nth orchestrator step accrues a predictable wall-clock delta."""
    state = {"t": 0}

    def clock():
        v = state["t"]
        state["t"] += step_ms
        return v

    return clock


# ── 1. model_tokens ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_model_tokens_exhaustion_terminates_run(lab_env, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "lab_budget_model_tokens", 100)
    factory = lab_env
    await _seed(factory)
    monkeypatch.setattr("app.lab.orchestrator.get_adapter", lambda name: FakeModelTokensAdapter())
    task_id, run_id = await _make_task(factory, scopes=["web_search"], title="token")

    await run_one(run_id)

    await _assert_budget_termination(factory, task_id, run_id, "model_tokens")


# ── 2. wall_clock_ms (patched monotonic source) ───────────────────────

@pytest.mark.anyio
async def test_wall_clock_exhaustion_terminates_run(lab_env, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "lab_budget_wall_clock_ms", 3000)
    factory = lab_env
    await _seed(factory)
    monkeypatch.setattr("app.lab.orchestrator.get_adapter", lambda name: FakePlainAdapter())
    monkeypatch.setattr("app.lab.orchestrator._now_ms", _make_clock(2000))
    task_id, run_id = await _make_task(factory, scopes=["web_search"], title="wall")

    await run_one(run_id)

    await _assert_budget_termination(factory, task_id, run_id, "wall_clock_ms")


# ── 3. egress_requests ────────────────────────────────────────────────

@pytest.mark.anyio
async def test_egress_requests_exhaustion_terminates_run(lab_env, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "lab_budget_egress_requests", 1)
    factory = lab_env
    await _seed(factory)
    monkeypatch.setattr("app.lab.orchestrator.get_adapter", lambda name: FakeEgressAdapter())
    monkeypatch.setattr(
        "app.lab.orchestrator._mock_executor", _trusted_test_egress_executor
    )
    task_id, run_id = await _make_task(factory, scopes=["browse"], title="egress-req")

    await run_one(run_id)

    await _assert_budget_termination(factory, task_id, run_id, "egress_requests")

    # The first egress request settled before the second exhausted.
    async with factory() as s:
        budget = await s.get(LabRunBudget, run_id)
        assert budget.used_egress_requests == 1


# ── 4. egress_bytes ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_egress_bytes_exhaustion_terminates_run(lab_env, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "lab_budget_egress_bytes", 10)  # < one mock result
    factory = lab_env
    await _seed(factory)
    monkeypatch.setattr("app.lab.orchestrator.get_adapter", lambda name: FakeEgressAdapter())
    monkeypatch.setattr(
        "app.lab.orchestrator._mock_executor", _trusted_test_egress_executor
    )
    task_id, run_id = await _make_task(factory, scopes=["browse"], title="egress-bytes")

    await run_one(run_id)

    await _assert_budget_termination(factory, task_id, run_id, "egress_bytes")


# ── 5. artifact_bytes ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_artifact_bytes_exhaustion_terminates_run(lab_env, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "lab_budget_artifact_bytes", 2)  # < len("done")
    factory = lab_env
    await _seed(factory)
    monkeypatch.setattr("app.lab.orchestrator.get_adapter", lambda name: FakePlainAdapter())
    task_id, run_id = await _make_task(factory, scopes=["web_search"], title="artifact-bytes")

    await run_one(run_id)

    await _assert_budget_termination(factory, task_id, run_id, "artifact_bytes")

    # A byte-exhausted run must not half-commit the artifact row.
    from app.models.lab_artifact import LabArtifact
    async with factory() as s:
        arts = (await s.execute(select(LabArtifact).where(LabArtifact.run_id == run_id))).scalars().all()
        assert arts == []


# ── 6a. active_workers: normal terminal release (reserved → 0) ────────

@pytest.mark.anyio
async def test_active_workers_released_on_normal_terminal(lab_env, monkeypatch):
    factory = lab_env
    await _seed(factory)
    monkeypatch.setattr("app.lab.orchestrator.get_adapter", lambda name: FakePlainAdapter())
    task_id, run_id = await _make_task(factory, scopes=["web_search"], title="worker-release")

    await run_one(run_id)

    async with factory() as s:
        run = await s.get(LabRun, run_id)
        assert run.status == "succeeded"
        budget = await s.get(LabRunBudget, run_id)
        # reserve(1) at start + release(1) at terminal → balanced back to 0;
        # active_workers is a gauge, never settled into used.
        assert budget.reserved_active_workers == 0
        assert budget.used_active_workers == 0


# ── 6b. active_workers: exhaustion drives the unified termination path ─

@pytest.mark.anyio
async def test_active_workers_exhaustion_terminates_run(lab_env, monkeypatch):
    """A single Mock worker can't exhaust active_workers on its own, so simulate
    a slot already taken (P4 concurrency shape): pre-seed the run's budget row
    with limit 1 and one reserved unit, then the orchestrator's own reserve must
    trip and drive the standard budget-termination path."""
    factory = lab_env
    await _seed(factory)
    monkeypatch.setattr("app.lab.orchestrator.get_adapter", lambda name: FakePlainAdapter())
    task_id, run_id = await _make_task(factory, scopes=["web_search"], title="worker-exhaust")

    async with factory() as s:
        await budgets.init_run_budget(s, run_id=run_id, tenant_id="issuer",
                                      limits={"active_workers": 1})
        await budgets.reserve(s, run_id=run_id, dimension="active_workers")  # the other worker

    await run_one(run_id)

    await _assert_budget_termination(factory, task_id, run_id, "active_workers")


# ── 7. regression: default (large) limits keep the happy path green ───

@pytest.mark.anyio
async def test_default_limits_do_not_terminate_happy_path(lab_env, monkeypatch):
    """With settings defaults, none of the newly wired dimensions may trip — the
    run succeeds and each new dimension shows real, bounded usage."""
    factory = lab_env
    await _seed(factory)
    monkeypatch.setattr("app.lab.orchestrator.get_adapter", lambda name: FakeEgressAdapter())
    monkeypatch.setattr(
        "app.lab.orchestrator._mock_executor", _trusted_test_egress_executor
    )
    task_id, run_id = await _make_task(factory, scopes=["browse"], title="happy")

    await run_one(run_id)

    async with factory() as s:
        run = await s.get(LabRun, run_id)
        assert run.status == "succeeded"
        budget = await s.get(LabRunBudget, run_id)
        assert budget.exhausted_dimension is None
        assert budget.used_egress_requests == 2      # two browser.navigate calls
        assert budget.used_egress_bytes > 0          # result bytes accrued
        assert budget.reserved_active_workers == 0    # released at terminal
        assert budget.reserved_egress_requests == 0   # all settled
