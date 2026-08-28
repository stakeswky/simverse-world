"""Manual Product Event retention cleanup is bounded and dry-run by default."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select


pytestmark = pytest.mark.anyio


async def _seed_event(db, *, created_at: datetime) -> str:
    from app.models.product_event import ProductEvent

    event_id = str(uuid4())
    db.add(ProductEvent(
        event_id=event_id,
        user_id="retention-user",
        session_id=str(uuid4()),
        event_name="living_loop_today_viewed",
        properties_json={"surface_version": 1, "entry_point": "direct"},
        occurred_at=created_at,
        client_occurred_at=None,
        created_at=created_at,
    ))
    await db.commit()
    return event_id


async def _count(db) -> int:
    from app.models.product_event import ProductEvent

    return int((await db.execute(
        select(func.count()).select_from(ProductEvent)
    )).scalar() or 0)


async def test_cleanup_dry_run_reports_candidates_without_writing(db_session) -> None:
    from scripts.cleanup_product_events import cleanup_product_events

    now = datetime(2026, 8, 28, 12, tzinfo=UTC)
    await _seed_event(db_session, created_at=now - timedelta(days=91))
    await _seed_event(db_session, created_at=now - timedelta(days=30))

    report = await cleanup_product_events(
        db_session,
        retention_days=90,
        apply=False,
        now=now,
    )

    assert report == {
        "mode": "dry-run",
        "cutoff": "2026-05-30T12:00:00Z",
        "candidates": 1,
        "deleted": 0,
    }
    assert await _count(db_session) == 2


async def test_cleanup_apply_deletes_only_strictly_older_rows(db_session) -> None:
    from app.models.product_event import ProductEvent
    from scripts.cleanup_product_events import cleanup_product_events

    now = datetime(2026, 8, 28, 12, tzinfo=UTC)
    expired = await _seed_event(db_session, created_at=now - timedelta(days=90, seconds=1))
    boundary = await _seed_event(db_session, created_at=now - timedelta(days=90))
    recent = await _seed_event(db_session, created_at=now - timedelta(days=1))

    report = await cleanup_product_events(
        db_session,
        retention_days=90,
        apply=True,
        now=now,
    )

    assert report["mode"] == "apply"
    assert report["candidates"] == 1
    assert report["deleted"] == 1
    remaining = set((await db_session.execute(
        select(ProductEvent.event_id)
    )).scalars())
    assert remaining == {boundary, recent}
    assert expired not in remaining


@pytest.mark.parametrize("retention_days", [0, -1, 366])
async def test_cleanup_rejects_unsafe_retention_windows(
    db_session,
    retention_days: int,
) -> None:
    from scripts.cleanup_product_events import cleanup_product_events

    with pytest.raises(ValueError, match="retention_days"):
        await cleanup_product_events(
            db_session,
            retention_days=retention_days,
            apply=False,
            now=datetime(2026, 8, 28, tzinfo=UTC),
        )
