"""Living Loop P0 user API and deterministic decision contracts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from sqlalchemy import func, select, text

from app.challenge.repository import SESSION_PREFIX
from app.config import settings
from app.models.digest import Digest
from app.models.notification import Notification
from app.models.resident_relation import ResidentRelation
from app.redis_client import get_redis

from tests.test_living_loop_support import auth_headers, create_user

pytestmark = pytest.mark.anyio


CHOICES = {
    "public_support": {
        "worker_trust_delta": 8,
        "management_trust_delta": -5,
        "city_credit_delta": 2,
    },
    "private_mediation": {
        "worker_trust_delta": 3,
        "management_trust_delta": 3,
        "city_credit_delta": 1,
    },
    "collect_evidence": {
        "worker_trust_delta": 2,
        "management_trust_delta": 0,
        "city_credit_delta": 4,
    },
}


def _enable(monkeypatch, *, delay_seconds: int = 3600) -> None:
    monkeypatch.setattr(settings, "living_loop_p0_enabled", True)
    monkeypatch.setattr(settings, "living_loop_p0_delay_seconds", delay_seconds)


async def _today(client, user):
    response = await client.get("/living-loop/today", headers=auth_headers(user))
    assert response.status_code == 200, response.text
    return response.json()


async def _choose(client, user, decision_id: str, choice_key: str, key=None):
    return await client.post(
        f"/living-loop/decisions/{decision_id}/choose",
        headers=auth_headers(user),
        json={
            "choice_key": choice_key,
            "idempotency_key": str(key or uuid4()),
        },
    )


async def _count(db, model, *criteria) -> int:
    statement = select(func.count()).select_from(model)
    if criteria:
        statement = statement.where(*criteria)
    return int((await db.execute(statement)).scalar() or 0)


async def test_all_user_endpoints_require_authentication(client) -> None:
    decision_id = str(uuid4())
    event_id = str(uuid4())

    responses = [
        await client.get("/living-loop/today"),
        await client.post(
            f"/living-loop/decisions/{decision_id}/choose",
            json={"choice_key": "public_support", "idempotency_key": str(uuid4())},
        ),
        await client.post(f"/living-loop/decisions/{decision_id}/result-viewed"),
        await client.post(
            "/product-events/batch",
            json={
                "events": [{
                    "event_id": event_id,
                    "session_id": None,
                    "event_name": "living_loop_today_viewed",
                    "properties": {"surface_version": 1, "entry_point": "direct"},
                }],
            },
        ),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401, 401]


async def test_feature_off_is_predictable_and_writes_no_day(
    client, db_session, monkeypatch,
) -> None:
    from app.models.living_loop_day import LivingLoopDay

    user, _ = await create_user(db_session, "disabled")
    monkeypatch.setattr(settings, "living_loop_p0_enabled", False)

    response = await client.get("/living-loop/today", headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json()["experiment"] == {
        "key": "living_loop_p0",
        "enabled": False,
    }
    assert response.json()["status"] == "feature_disabled"
    assert response.json()["decision"] is None
    assert response.json()["journey"]["town_path"] == "/play"
    assert await _count(db_session, LivingLoopDay) == 0


async def test_missing_player_binding_returns_setup_required_without_writing(
    client, db_session, monkeypatch,
) -> None:
    from app.models.living_loop_day import LivingLoopDay

    _enable(monkeypatch)
    user, _ = await create_user(db_session, "setup", with_resident=False)

    response = await client.get("/living-loop/today", headers=auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["experiment"]["enabled"] is True
    assert body["status"] == "setup_required"
    assert body["player_resident"] is None
    assert body["decision"] is None
    assert await _count(db_session, LivingLoopDay) == 0


async def test_first_get_creates_one_persisted_day_and_same_day_get_is_idempotent(
    client, db_session, monkeypatch,
) -> None:
    from app.models.living_loop_day import LivingLoopDay

    _enable(monkeypatch)
    user, resident = await create_user(db_session, "first")

    first = await _today(client, user)
    second = await _today(client, user)

    assert first["status"] == "ready"
    assert first["player_resident"] == {
        "id": resident.id,
        "slug": resident.slug,
        "name": resident.name,
        "district": resident.district,
        "sprite_key": resident.sprite_key,
    }
    assert first["decision"]["id"] == second["decision"]["id"]
    assert first["decision"]["scenario_key"] == "harbor_wage_dispute_v1"
    assert first["decision"]["scenario_version"] == 1
    assert first["decision"]["state"] == "pending"
    assert {choice["key"] for choice in first["decision"]["choices"]} == set(CHOICES)
    assert first["decision"]["selected_choice"] is None
    assert first["decision"]["immediate_result"] is None
    assert first["decision"]["delayed_result"] is None
    assert first["journey"] == {"town_path": "/play", "profile_path": "/profile"}
    assert await _count(db_session, LivingLoopDay) == 1

    row = (await db_session.execute(select(LivingLoopDay))).scalar_one()
    assert row.user_id == user.id
    assert row.experiment_key == "living_loop_p0"
    assert row.day_key == datetime.fromisoformat(
        first["server_now"].replace("Z", "+00:00")
    ).astimezone(UTC).date()
    assert row.first_viewed_at is not None
    assert row.scenario_snapshot_json["scenario_key"] == "harbor_wage_dispute_v1"


async def test_different_users_receive_isolated_decisions_and_cannot_read_by_id(
    client, db_session, monkeypatch,
) -> None:
    from app.models.living_loop_day import LivingLoopDay

    _enable(monkeypatch)
    first_user, _ = await create_user(db_session, "owner-a")
    second_user, _ = await create_user(db_session, "owner-b")
    first = await _today(client, first_user)
    second = await _today(client, second_user)

    assert first["decision"]["id"] != second["decision"]["id"]
    assert await _count(db_session, LivingLoopDay) == 2

    foreign = await _choose(
        client,
        second_user,
        first["decision"]["id"],
        "public_support",
    )
    assert foreign.status_code == 404


@pytest.mark.parametrize(("choice_key", "expected"), CHOICES.items())
async def test_each_registered_choice_uses_server_owned_effects(
    client, db_session, monkeypatch, choice_key, expected,
) -> None:
    from app.models.living_loop_day import LivingLoopDay

    _enable(monkeypatch)
    user, _ = await create_user(db_session, f"choice-{choice_key}")
    today = await _today(client, user)

    response = await _choose(client, user, today["decision"]["id"], choice_key)

    assert response.status_code == 200, response.text
    decision = response.json()["decision"]
    assert decision["state"] == "chosen"
    assert decision["selected_choice"] == choice_key
    assert decision["immediate_result"]["effects"] == expected
    assert decision["result_available_at"] is not None
    assert decision["delayed_result"] is None

    row = await db_session.get(LivingLoopDay, decision["id"])
    await db_session.refresh(row)
    assert row.choice_key == choice_key
    assert row.immediate_result_json["effects"] == expected
    assert row.delayed_result_json


async def test_invalid_choice_and_client_supplied_effects_are_rejected(
    client, db_session, monkeypatch,
) -> None:
    _enable(monkeypatch)
    user, _ = await create_user(db_session, "invalid-choice")
    today = await _today(client, user)
    decision_id = today["decision"]["id"]

    unknown = await _choose(client, user, decision_id, "mint_free_coins")
    injected = await client.post(
        f"/living-loop/decisions/{decision_id}/choose",
        headers=auth_headers(user),
        json={
            "choice_key": "public_support",
            "idempotency_key": str(uuid4()),
            "immediate_result": {"soul_coin_delta": 999999},
        },
    )

    assert unknown.status_code in {400, 422}
    assert injected.status_code == 422


async def test_choose_is_idempotent_and_a_later_change_conflicts(
    client, db_session, monkeypatch,
) -> None:
    from app.models.product_event import ProductEvent

    _enable(monkeypatch)
    user, _ = await create_user(db_session, "idempotency")
    today = await _today(client, user)
    decision_id = today["decision"]["id"]
    idempotency_key = uuid4()

    first = await _choose(
        client, user, decision_id, "private_mediation", idempotency_key,
    )
    replay = await _choose(
        client, user, decision_id, "private_mediation", idempotency_key,
    )
    same_choice_new_key = await _choose(
        client, user, decision_id, "private_mediation", uuid4(),
    )
    changed = await _choose(
        client, user, decision_id, "collect_evidence", uuid4(),
    )

    assert first.status_code == replay.status_code == same_choice_new_key.status_code == 200
    assert first.json() == replay.json() == same_choice_new_key.json()
    assert changed.status_code == 409
    assert await _count(
        db_session,
        ProductEvent,
        ProductEvent.user_id == user.id,
        ProductEvent.event_name == "living_loop_choice_confirmed",
    ) == 1


async def test_choice_does_not_touch_coins_relations_or_challenge_state(
    client, db_session, monkeypatch,
) -> None:
    _enable(monkeypatch)
    user, resident = await create_user(db_session, "invariants")
    relation = ResidentRelation(
        party_a=resident.id,
        party_a_type="resident",
        party_b="worker-representative",
        party_b_type="resident",
        familiarity=0.4,
        affinity=-0.2,
        interact_count=7,
    )
    db_session.add(relation)
    await db_session.commit()
    await db_session.refresh(user)
    before_user_balance = user.soul_coin_balance
    before_relation = (
        relation.familiarity,
        relation.affinity,
        relation.interact_count,
    )
    redis = get_redis()
    challenge_key = f"{SESSION_PREFIX}living-loop-invariant"
    await redis.set(challenge_key, '{"sentinel":"must-stay-byte-identical"}')
    before_challenge = await redis.get(challenge_key)
    today = await _today(client, user)

    response = await _choose(
        client, user, today["decision"]["id"], "public_support",
    )
    assert response.status_code == 200

    user_id = user.id
    relation_id = relation.id
    db_session.expire_all()
    refreshed_user = await db_session.get(type(user), user_id)
    refreshed_relation = await db_session.get(ResidentRelation, relation_id)
    assert refreshed_user.soul_coin_balance == before_user_balance
    assert (
        refreshed_relation.familiarity,
        refreshed_relation.affinity,
        refreshed_relation.interact_count,
    ) == before_relation
    assert await redis.get(challenge_key) == before_challenge


async def test_result_is_hidden_until_due_then_settles_once_and_view_is_idempotent(
    client, db_session, monkeypatch,
) -> None:
    from app.models.living_loop_day import LivingLoopDay
    from app.models.product_event import ProductEvent

    _enable(monkeypatch, delay_seconds=3600)
    user, _ = await create_user(db_session, "result")
    today = await _today(client, user)
    decision_id = today["decision"]["id"]
    chosen = await _choose(client, user, decision_id, "collect_evidence")
    assert chosen.status_code == 200
    assert "完整审计证据" not in chosen.text

    before_due = await _today(client, user)
    assert before_due["decision"]["state"] == "chosen"
    assert before_due["decision"]["delayed_result"] is None
    early_view = await client.post(
        f"/living-loop/decisions/{decision_id}/result-viewed",
        headers=auth_headers(user),
    )
    assert early_view.status_code == 409
    assert "完整审计证据" not in early_view.text

    row = await db_session.get(LivingLoopDay, decision_id)
    row.result_available_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    settled_once = await _today(client, user)
    settled_twice = await _today(client, user)
    assert settled_once["decision"]["state"] == "result_ready"
    assert settled_once["decision"]["delayed_result"] == settled_twice["decision"]["delayed_result"]
    assert "完整审计证据" in str(settled_once["decision"]["delayed_result"])
    assert await _count(
        db_session,
        ProductEvent,
        ProductEvent.event_name == "living_loop_result_settled",
        ProductEvent.user_id == user.id,
    ) == 1

    first_view = await client.post(
        f"/living-loop/decisions/{decision_id}/result-viewed",
        headers=auth_headers(user),
    )
    second_view = await client.post(
        f"/living-loop/decisions/{decision_id}/result-viewed",
        headers=auth_headers(user),
    )
    assert first_view.status_code == second_view.status_code == 200
    assert first_view.json() == second_view.json()
    assert first_view.json()["decision"]["state"] == "result_viewed"
    assert await _count(
        db_session,
        ProductEvent,
        ProductEvent.event_name == "living_loop_result_first_viewed",
        ProductEvent.user_id == user.id,
    ) == 1


def _authoritative_event_id(event_name: str, decision_id: str) -> str:
    return str(uuid5(
        NAMESPACE_URL,
        f"simverse-world:{event_name}:{decision_id}",
    ))


async def _preclaim_authoritative_event_id(
    db,
    *,
    user_id: str,
    event_id: str,
) -> None:
    from app.models.product_event import ProductEvent

    now = datetime.now(UTC)
    db.add(ProductEvent(
        event_id=event_id,
        user_id=user_id,
        session_id=None,
        event_name="living_loop_today_viewed",
        properties_json={"surface_version": 1, "entry_point": "direct"},
        occurred_at=now,
        client_occurred_at=None,
        created_at=now,
    ))
    await db.commit()


async def test_settlement_rolls_back_if_authoritative_event_id_is_preclaimed(
    client, db_session, monkeypatch,
) -> None:
    from app.models.living_loop_day import LivingLoopDay

    _enable(monkeypatch, delay_seconds=3600)
    user, _ = await create_user(db_session, "settled-event-collision")
    today = await _today(client, user)
    decision_id = today["decision"]["id"]
    assert (await _choose(
        client, user, decision_id, "public_support",
    )).status_code == 200
    row = await db_session.get(LivingLoopDay, decision_id)
    row.result_available_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    await _preclaim_authoritative_event_id(
        db_session,
        user_id=user.id,
        event_id=_authoritative_event_id(
            "living_loop_result_settled",
            decision_id,
        ),
    )

    response = await client.get(
        "/living-loop/today",
        headers=auth_headers(user),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "authoritative_event_conflict"
    await db_session.rollback()
    db_session.expire_all()
    persisted = await db_session.get(LivingLoopDay, decision_id)
    assert persisted.state == "chosen"
    assert persisted.result_settled_at is None


async def test_result_view_rolls_back_if_authoritative_event_id_is_preclaimed(
    client, db_session, monkeypatch,
) -> None:
    from app.models.living_loop_day import LivingLoopDay

    _enable(monkeypatch, delay_seconds=3600)
    user, _ = await create_user(db_session, "viewed-event-collision")
    today = await _today(client, user)
    decision_id = today["decision"]["id"]
    assert (await _choose(
        client, user, decision_id, "private_mediation",
    )).status_code == 200
    row = await db_session.get(LivingLoopDay, decision_id)
    row.result_available_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    assert (await _today(client, user))["decision"]["state"] == "result_ready"
    await _preclaim_authoritative_event_id(
        db_session,
        user_id=user.id,
        event_id=_authoritative_event_id(
            "living_loop_result_first_viewed",
            decision_id,
        ),
    )

    response = await client.post(
        f"/living-loop/decisions/{decision_id}/result-viewed",
        headers=auth_headers(user),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "authoritative_event_conflict"
    await db_session.rollback()
    db_session.expire_all()
    persisted = await db_session.get(LivingLoopDay, decision_id)
    assert persisted.state == "result_ready"
    assert persisted.result_viewed_at is None


async def test_notification_and_digest_sql_failures_leave_core_decision_available(
    client, db_session, monkeypatch,
) -> None:
    _enable(monkeypatch)
    user, _ = await create_user(db_session, "fail-open")
    await db_session.execute(text("DROP TABLE notifications"))
    await db_session.execute(text("DROP TABLE digests"))
    await db_session.commit()

    response = await client.get("/living-loop/today", headers=auth_headers(user))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"]["scenario_key"] == "harbor_wage_dispute_v1"
    assert body["since_you_left"] == []
    assert body["city_pulse"]["is_fallback"] is True
    assert body["city_pulse"]["title"]
    assert body["city_pulse"]["summary"]


async def test_today_reads_at_most_two_notifications_without_marking_them_read(
    client, db_session, monkeypatch,
) -> None:
    _enable(monkeypatch)
    user, _ = await create_user(db_session, "aggregates")
    now = datetime.now(UTC)
    notifications = [
        Notification(
            user_id=user.id,
            kind="system",
            title=f"通知 {index}",
            body=f"正文 {index}",
            created_at=now + timedelta(seconds=index),
        )
        for index in range(3)
    ]
    db_session.add_all(notifications)
    db_session.add(Digest(
        scope="village",
        date=date.today(),
        user_id="",
        title="今日城市日报",
        content_md="港口和广场都有新变化，这是一段足够长且无需调用模型生成的既有日报正文。",
        stats_json={},
    ))
    await db_session.commit()

    body = await _today(client, user)

    notification_items = [
        item for item in body["since_you_left"] if item["kind"] == "notification"
    ]
    assert [item["title"] for item in notification_items] == ["通知 2", "通知 1"]
    assert body["city_pulse"]["is_fallback"] is False
    for notification in notifications:
        await db_session.refresh(notification)
        assert notification.read_at is None
