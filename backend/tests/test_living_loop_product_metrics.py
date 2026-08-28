"""Admin authorization and deterministic Living Loop funnel metrics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.config import settings

from tests.test_living_loop_support import auth_headers, create_user

pytestmark = pytest.mark.anyio


async def _event(
    db,
    *,
    user_id: str,
    name: str,
    occurred_at: datetime,
    properties: dict | None = None,
):
    from app.models.product_event import ProductEvent

    db.add(ProductEvent(
        event_id=str(uuid4()),
        user_id=user_id,
        session_id=str(uuid4()),
        event_name=name,
        properties_json=properties or {},
        occurred_at=occurred_at,
        client_occurred_at=None,
        created_at=occurred_at,
    ))


async def _day(
    db,
    *,
    user_id: str,
    index: int,
    choice_key: str,
    first_viewed_at: datetime,
    choice_confirmed_at: datetime,
    result_viewed_at: datetime,
):
    from app.models.living_loop_day import LivingLoopDay

    db.add(LivingLoopDay(
        user_id=user_id,
        experiment_key="living_loop_p0",
        day_key=first_viewed_at.date(),
        scenario_key="harbor_wage_dispute_v1",
        scenario_version=1,
        state="result_viewed",
        scenario_snapshot_json={
            "scenario_key": "harbor_wage_dispute_v1",
            "private_marker": f"must-not-leak-{index}",
        },
        choice_key=choice_key,
        immediate_result_json={"effects": {"city_credit_delta": index}},
        delayed_result_json={"summary": f"private result body {index}"},
        first_viewed_at=first_viewed_at,
        choice_confirmed_at=choice_confirmed_at,
        result_available_at=choice_confirmed_at + timedelta(hours=8),
        result_settled_at=choice_confirmed_at + timedelta(hours=8),
        result_viewed_at=result_viewed_at,
        created_at=first_viewed_at,
        updated_at=result_viewed_at,
    ))


async def test_metrics_endpoint_requires_admin(client, db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "living_loop_p0_enabled", True)
    normal, _ = await create_user(db_session, "metrics-normal")

    missing = await client.get("/admin/product-metrics/living-loop-p0")
    forbidden = await client.get(
        "/admin/product-metrics/living-loop-p0",
        headers=auth_headers(normal),
    )

    assert missing.status_code == 401
    assert forbidden.status_code == 403


async def test_metrics_calculate_unique_funnel_median_distribution_and_48h_return(
    client, db_session, monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "living_loop_p0_enabled", True)
    admin, _ = await create_user(db_session, "metrics-admin", is_admin=True)
    first, _ = await create_user(db_session, "metrics-first")
    second, _ = await create_user(db_session, "metrics-second")
    visitor_only, _ = await create_user(db_session, "metrics-visitor-only")
    now = datetime.now(UTC)
    start = now - timedelta(days=3)

    # Three unique Today visitors, two decision viewers and two confirmations.
    for user in (first, second, visitor_only):
        await _event(
            db_session,
            user_id=user.id,
            name="living_loop_today_viewed",
            occurred_at=start,
        )
    for user in (first, second):
        await _event(
            db_session,
            user_id=user.id,
            name="living_loop_decision_viewed",
            occurred_at=start,
        )

    await _day(
        db_session,
        user_id=first.id,
        index=1,
        choice_key="public_support",
        first_viewed_at=start,
        choice_confirmed_at=start + timedelta(seconds=30),
        result_viewed_at=start + timedelta(hours=9),
    )
    await _day(
        db_session,
        user_id=second.id,
        index=2,
        choice_key="private_mediation",
        first_viewed_at=start,
        choice_confirmed_at=start + timedelta(seconds=90),
        result_viewed_at=start + timedelta(hours=57),
    )
    for user, choice, viewed_at in (
        (first, "public_support", start + timedelta(hours=9)),
        (second, "private_mediation", start + timedelta(hours=57)),
    ):
        await _event(
            db_session,
            user_id=user.id,
            name="living_loop_choice_confirmed",
            occurred_at=start + timedelta(seconds=30 if user.id == first.id else 90),
            properties={"choice_key": choice},
        )
        await _event(
            db_session,
            user_id=user.id,
            name="living_loop_result_settled",
            occurred_at=start + timedelta(hours=8),
            properties={"choice_key": choice},
        )
        await _event(
            db_session,
            user_id=user.id,
            name="living_loop_result_first_viewed",
            occurred_at=viewed_at,
            properties={"choice_key": choice},
        )
    await db_session.commit()

    response = await client.get(
        "/admin/product-metrics/living-loop-p0",
        headers=auth_headers(admin),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["today_unique_users"] == 3
    assert body["decision_viewed_unique_users"] == 2
    assert body["choice_confirmed_unique_users"] == 2
    assert body["choice_completion_rate"] == 1.0
    assert body["settled_result_count"] == 2
    assert body["delayed_result_viewed_unique_users"] == 2
    assert body["return_within_48h_rate"] == 0.5
    assert body["median_choice_seconds"] == 60.0
    assert body["choice_distribution"] == [
        {"choice_key": "public_support", "count": 1, "share": 0.5},
        {"choice_key": "private_mediation", "count": 1, "share": 0.5},
        {"choice_key": "collect_evidence", "count": 0, "share": 0.0},
    ]
    assert set(body["window"]) == {"from", "to"}
    assert isinstance(body["generated_at"], str)

    serialized = response.text
    for forbidden in (
        admin.email,
        first.email,
        second.email,
        first.name,
        "private result body",
        "must-not-leak",
    ):
        assert forbidden not in serialized


async def test_48h_return_rate_uses_mature_decisions_not_unique_users(
    client, db_session, monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "living_loop_p0_enabled", True)
    admin, _ = await create_user(db_session, "metrics-decision-admin", is_admin=True)
    returning_user, _ = await create_user(db_session, "metrics-repeat-user")
    now = datetime.now(UTC)
    first_start = now - timedelta(days=5)
    second_start = now - timedelta(days=3)

    await _day(
        db_session,
        user_id=returning_user.id,
        index=11,
        choice_key="public_support",
        first_viewed_at=first_start,
        choice_confirmed_at=first_start + timedelta(seconds=20),
        result_viewed_at=first_start + timedelta(hours=9),
    )
    await _day(
        db_session,
        user_id=returning_user.id,
        index=12,
        choice_key="collect_evidence",
        first_viewed_at=second_start,
        choice_confirmed_at=second_start + timedelta(seconds=40),
        result_viewed_at=second_start + timedelta(hours=60),
    )
    await db_session.commit()

    response = await client.get(
        "/admin/product-metrics/living-loop-p0",
        headers=auth_headers(admin),
    )

    assert response.status_code == 200, response.text
    assert response.json()["return_within_48h_rate"] == 0.5
