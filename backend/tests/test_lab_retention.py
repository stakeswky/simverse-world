"""P2-B / V12 — artifact retention holds + expired-artifact cleanup tombstones
(DB-slice, no object store; scope ruling in .superpowers/sdd/task-9-brief.md).
Retention: 30-day artifact window (``settings.lab_artifact_retention_days``);
referenced evidence (a completed task's artifacts, or a run cited by a
``lab_run``-origin world-change proposal) is held and never swept. Cleanup
clears content but keeps the row (audit trail) and writes one outbox
``cleanup.completed`` event per sweep.
"""
import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.lab_artifact import LabArtifact
from app.models.lab_event import OutboxEvent
from app.models.lab_task import LabTask
from app.models.world_change_proposal import WorldChangeProposal
from app.services import lab_artifact_service


@pytest.fixture(autouse=True)
def _v1_enabled(monkeypatch):
    """cleanup_expired is gated behind the flag (destructive; paused during a
    flag-off rollback window — P2-B review). Default it on for this module so
    each scenario below tests the sweep itself; the no-op scenario flips it
    back off explicitly."""
    monkeypatch.setattr(settings, "lab_agent_v1_enabled", True, raising=False)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _expired_task_and_artifact(db_session, *, task_status="review", text="hello", title="x"):
    task = LabTask(issuer_user_id="owner-a", title="t", reward_sc=10, status=task_status)
    db_session.add(task)
    await db_session.flush()
    artifact = LabArtifact(
        run_id="run1", task_id=task.id, kind="text", title=title, text_md=text,
        sha256=_digest(text), byte_size=len(text.encode("utf-8")),
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(artifact)
    await db_session.commit()
    return task, artifact


# ── 1. expired, unheld → tombstoned; row survives; stats correct ──────

@pytest.mark.anyio
async def test_cleanup_tombstones_expired_unheld_artifact(db_session):
    task, artifact = await _expired_task_and_artifact(db_session, text="hello")

    stats = await lab_artifact_service.cleanup_expired(db_session)

    assert stats["deleted_count"] == 1
    assert stats["byte_count"] == len("hello".encode("utf-8"))
    refreshed = await db_session.get(LabArtifact, artifact.id)
    assert refreshed is not None  # row survives
    assert refreshed.text_md is None and refreshed.uri is None
    assert refreshed.meta_json["tombstone"] == _digest("hello")
    assert "cleaned_at" in refreshed.meta_json


# ── 2. task completed → hold; cleanup skips, held_count counted ───────

@pytest.mark.anyio
async def test_apply_retention_holds_task_completed_then_cleanup_skips(db_session):
    task, artifact = await _expired_task_and_artifact(db_session, task_status="completed", text="hello")

    held = await lab_artifact_service.apply_retention_holds(db_session)
    assert held == 1
    refreshed = await db_session.get(LabArtifact, artifact.id)
    assert refreshed.retention_hold is True

    stats = await lab_artifact_service.cleanup_expired(db_session)
    assert stats["deleted_count"] == 0
    assert stats["held_count"] == 1
    refreshed2 = await db_session.get(LabArtifact, artifact.id)
    assert refreshed2.text_md == "hello"  # untouched


# ── 3. proposal-referenced (origin=lab_run, origin_ref==run_id) → hold ─

@pytest.mark.anyio
async def test_apply_retention_holds_proposal_referenced(db_session):
    task = LabTask(issuer_user_id="owner-a", title="t", reward_sc=10, status="review")
    db_session.add(task)
    await db_session.flush()
    artifact = LabArtifact(
        run_id="run-x", task_id=task.id, kind="text", title="x", text_md="hello",
        sha256=_digest("hello"), byte_size=5,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(artifact)
    db_session.add(WorldChangeProposal(
        origin="lab_run", origin_ref="run-x", kind="add_lore", title="p", patch_json={},
    ))
    await db_session.commit()

    held = await lab_artifact_service.apply_retention_holds(db_session)
    assert held == 1
    refreshed = await db_session.get(LabArtifact, artifact.id)
    assert refreshed.retention_hold is True


# ── 4. cleanup writes cleanup.completed outbox event, full payload ────

@pytest.mark.anyio
async def test_cleanup_writes_outbox_event_with_full_payload(db_session):
    task = LabTask(issuer_user_id="owner-a", title="t", reward_sc=10, status="review")
    db_session.add(task)
    await db_session.flush()
    a1 = LabArtifact(run_id="run1", task_id=task.id, kind="text", title="a", text_md="hello",
                      sha256=_digest("hello"), byte_size=5,
                      expires_at=datetime.now(UTC) - timedelta(days=1))
    a2 = LabArtifact(run_id="run1", task_id=task.id, kind="text", title="b", text_md="world",
                      sha256=_digest("world"), byte_size=5,
                      expires_at=datetime.now(UTC) - timedelta(days=1))
    db_session.add_all([a1, a2])
    await db_session.commit()

    await lab_artifact_service.cleanup_expired(db_session)

    rows = (await db_session.execute(
        select(OutboxEvent).where(
            OutboxEvent.topic == "artifact.cleanup.completed"
        )
    )).scalars().all()
    assert len(rows) == 1
    payload = rows[0].payload_json
    assert payload["scope"] == "lab_artifacts"
    assert payload["deleted_count"] == 2
    assert payload["held_count"] == 0
    assert payload["byte_count"] == 10
    assert len(payload["tombstone_digest"]) == 64
    int(payload["tombstone_digest"], 16)  # valid hex


# ── 5. single-row cleanup failure quarantined, batch continues ────────

@pytest.mark.anyio
async def test_cleanup_quarantines_single_row_failure_without_aborting_batch(db_session, monkeypatch):
    task = LabTask(issuer_user_id="owner-a", title="t", reward_sc=10, status="review")
    db_session.add(task)
    await db_session.flush()
    good = LabArtifact(run_id="run1", task_id=task.id, kind="text", title="good", text_md="hello",
                        sha256=_digest("hello"), byte_size=5,
                        expires_at=datetime.now(UTC) - timedelta(days=1))
    bad = LabArtifact(run_id="run1", task_id=task.id, kind="text", title="bad", text_md="boom",
                       sha256=_digest("boom"), byte_size=4,
                       expires_at=datetime.now(UTC) - timedelta(days=1))
    db_session.add_all([good, bad])
    await db_session.commit()
    bad_id = bad.id

    original = lab_artifact_service._tombstone_row

    def _flaky(a, *, now):
        if a.id == bad_id:
            raise RuntimeError("boom")
        return original(a, now=now)

    monkeypatch.setattr(lab_artifact_service, "_tombstone_row", _flaky)

    stats = await lab_artifact_service.cleanup_expired(db_session)

    assert stats["deleted_count"] == 1
    assert stats["quarantined_count"] == 1

    refreshed_good = await db_session.get(LabArtifact, good.id)
    assert refreshed_good.text_md is None

    refreshed_bad = await db_session.get(LabArtifact, bad_id)
    assert refreshed_bad.text_md == "boom"  # content untouched by the failed attempt
    assert refreshed_bad.meta_json["cleanup_failed"] is True


# ── 6. unexpired rows are left completely alone ────────────────────────

@pytest.mark.anyio
async def test_cleanup_leaves_unexpired_rows_untouched(db_session):
    task = LabTask(issuer_user_id="owner-a", title="t", reward_sc=10, status="review")
    db_session.add(task)
    await db_session.flush()
    artifact = LabArtifact(
        run_id="run1", task_id=task.id, kind="text", title="x", text_md="hello",
        sha256=_digest("hello"), byte_size=5,
        expires_at=datetime.now(UTC) + timedelta(days=10),
    )
    db_session.add(artifact)
    await db_session.commit()

    stats = await lab_artifact_service.cleanup_expired(db_session)

    assert stats["deleted_count"] == 0
    assert stats["held_count"] == 0
    refreshed = await db_session.get(LabArtifact, artifact.id)
    assert refreshed.text_md == "hello"


# ── 7. flag off → cleanup_expired is a hard no-op (rollback-window safety) ──

@pytest.mark.anyio
async def test_cleanup_expired_is_noop_when_flag_off(db_session, monkeypatch):
    monkeypatch.setattr(settings, "lab_agent_v1_enabled", False, raising=False)
    task, artifact = await _expired_task_and_artifact(db_session, text="hello")

    stats = await lab_artifact_service.cleanup_expired(db_session)

    assert stats["deleted_count"] == 0
    assert stats["held_count"] == 0
    assert stats["quarantined_count"] == 0
    refreshed = await db_session.get(LabArtifact, artifact.id)
    assert refreshed.text_md == "hello"  # untouched — expired, but flag is off
    rows = (await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.topic == "cleanup.completed")
    )).scalars().all()
    assert rows == []  # no event written for a paused sweep
