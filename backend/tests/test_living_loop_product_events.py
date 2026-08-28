"""Privacy-bounded first-party Product Event ledger contracts."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from sqlalchemy import func, select

from app.config import settings

from tests.test_living_loop_support import auth_headers, create_user, event_payload

pytestmark = pytest.mark.anyio


CLIENT_EVENTS = {
    "living_loop_today_viewed": {
        "surface_version": 1,
        "entry_point": "root",
    },
    "living_loop_decision_viewed": {
        "surface_version": 1,
        "decision_id": str(uuid4()),
        "scenario_key": "harbor_wage_dispute_v1",
        "scenario_version": 1,
        "decision_state": "pending",
    },
    "living_loop_choice_previewed": {
        "surface_version": 1,
        "decision_id": str(uuid4()),
        "scenario_key": "harbor_wage_dispute_v1",
        "scenario_version": 1,
        "choice_key": "public_support",
    },
    "living_loop_immediate_result_viewed": {
        "surface_version": 1,
        "decision_id": str(uuid4()),
        "scenario_key": "harbor_wage_dispute_v1",
        "scenario_version": 1,
        "choice_key": "public_support",
    },
    "living_loop_delayed_result_viewed": {
        "surface_version": 1,
        "decision_id": str(uuid4()),
        "scenario_key": "harbor_wage_dispute_v1",
        "scenario_version": 1,
        "choice_key": "public_support",
    },
    "living_loop_enter_town_clicked": {
        "surface_version": 1,
        "source": "header",
    },
    "living_loop_city_pulse_opened": {
        "surface_version": 1,
        "source": "card",
        "target": "capsules",
    },
}
SERVER_EVENTS = (
    "living_loop_choice_confirmed",
    "living_loop_result_settled",
    "living_loop_result_first_viewed",
)


def _choice_properties(choice_key: str) -> dict:
    return {
        "surface_version": 1,
        "decision_id": str(uuid4()),
        "scenario_key": "harbor_wage_dispute_v1",
        "scenario_version": 1,
        "choice_key": choice_key,
    }


def _enable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "living_loop_p0_enabled", True)


async def _count(db, *criteria) -> int:
    from app.models.product_event import ProductEvent

    statement = select(func.count()).select_from(ProductEvent)
    if criteria:
        statement = statement.where(*criteria)
    return int((await db.execute(statement)).scalar() or 0)


@pytest.mark.parametrize(("event_name", "properties"), CLIENT_EVENTS.items())
async def test_each_client_event_is_allowlisted(
    client, db_session, monkeypatch, event_name, properties,
) -> None:
    _enable(monkeypatch)
    user, _ = await create_user(db_session, f"event-{event_name}")
    payload = event_payload(
        str(uuid4()),
        event_name,
        properties=properties,
        session_id=str(uuid4()),
    )

    response = await client.post(
        "/product-events/batch", headers=auth_headers(user), json=payload,
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"accepted": 1, "duplicates": 0}


@pytest.mark.parametrize("event_name", SERVER_EVENTS)
async def test_client_cannot_submit_server_authoritative_events(
    client, db_session, monkeypatch, event_name,
) -> None:
    _enable(monkeypatch)
    user, _ = await create_user(db_session, f"server-event-{event_name}")

    response = await client.post(
        "/product-events/batch",
        headers=auth_headers(user),
        json=event_payload(str(uuid4()), event_name),
    )

    assert response.status_code == 422
    assert await _count(db_session) == 0


async def test_auth_precedes_body_validation_and_errors_never_echo_secrets(
    client, db_session, monkeypatch,
) -> None:
    _enable(monkeypatch)
    user, _ = await create_user(db_session, "event-validation-privacy")
    secret = "Bearer top-secret-must-not-echo"
    malformed = {
        "events": [{
            "event_id": str(uuid4()),
            "session_id": None,
            "event_name": "living_loop_today_viewed",
            "properties": {
                "surface_version": 1,
                "entry_point": "direct",
                "token": secret,
            },
        }],
    }

    unauthenticated = await client.post(
        "/product-events/batch",
        json=malformed,
    )
    authenticated = await client.post(
        "/product-events/batch",
        headers=auth_headers(user),
        json=malformed,
    )

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 422
    assert secret not in unauthenticated.text
    assert secret not in authenticated.text
    assert await _count(db_session) == 0


@pytest.mark.parametrize(
    "properties",
    [
        {"free_text": "please retain my private conversation"},
        {"email": "private@example.test"},
        {"token": "Bearer secret"},
        {"choice_key": "mint_free_coins"},
        {"scenario_version": "one"},
    ],
)
async def test_properties_are_strictly_allowlisted_and_typed(
    client, db_session, monkeypatch, properties,
) -> None:
    _enable(monkeypatch)
    user, _ = await create_user(db_session, f"bad-property-{uuid4().hex}")

    response = await client.post(
        "/product-events/batch",
        headers=auth_headers(user),
        json=event_payload(
            str(uuid4()),
            "living_loop_choice_previewed",
            properties={
                "surface_version": 1,
                "decision_id": str(uuid4()),
                "scenario_key": "harbor_wage_dispute_v1",
                "scenario_version": 1,
                "choice_key": "public_support",
                **properties,
            },
        ),
    )

    assert response.status_code == 422
    assert await _count(db_session) == 0


async def test_batch_is_bounded_to_twenty_and_rejects_atomically(
    client, db_session, monkeypatch,
) -> None:
    _enable(monkeypatch)
    user, _ = await create_user(db_session, "batch")
    too_many = {
        "events": [
            {
                "event_id": str(uuid4()),
                "session_id": str(uuid4()),
                "event_name": "living_loop_today_viewed",
                "properties": {"surface_version": 1, "entry_point": "direct"},
            }
            for _ in range(21)
        ],
    }
    mixed = {
        "events": [
            {
                "event_id": str(uuid4()),
                "session_id": str(uuid4()),
                "event_name": "living_loop_today_viewed",
                "properties": {"surface_version": 1, "entry_point": "direct"},
            },
            {
                "event_id": str(uuid4()),
                "session_id": str(uuid4()),
                "event_name": "living_loop_choice_confirmed",
                "properties": {},
            },
        ],
    }

    over_limit = await client.post(
        "/product-events/batch", headers=auth_headers(user), json=too_many,
    )
    empty_batch = await client.post(
        "/product-events/batch", headers=auth_headers(user), json={"events": []},
    )
    invalid_batch = await client.post(
        "/product-events/batch", headers=auth_headers(user), json=mixed,
    )

    assert over_limit.status_code == 422
    assert empty_batch.status_code == 422
    assert invalid_batch.status_code == 422
    assert await _count(db_session) == 0


async def test_request_body_limit_rejects_before_json_validation(
    client, db_session, monkeypatch,
) -> None:
    from app.routers.product_events import PRODUCT_EVENTS_MAX_BODY_BYTES

    _enable(monkeypatch)
    user, _ = await create_user(db_session, "body-limit")
    oversized = b'{"events":[],"padding":"' + (
        b"x" * PRODUCT_EVENTS_MAX_BODY_BYTES
    ) + b'"}'

    response = await client.post(
        "/product-events/batch",
        headers={**auth_headers(user), "Content-Type": "application/json"},
        content=oversized,
    )

    assert response.status_code == 413
    assert await _count(db_session) == 0


async def test_identical_event_id_is_idempotent_but_conflicting_reuse_is_409(
    client, db_session, monkeypatch,
) -> None:
    from app.models.product_event import ProductEvent

    _enable(monkeypatch)
    user, _ = await create_user(db_session, "event-idempotency")
    event_id = str(uuid4())
    original = event_payload(
        event_id,
        "living_loop_choice_previewed",
        properties=_choice_properties("public_support"),
        session_id=str(uuid4()),
    )

    first = await client.post(
        "/product-events/batch", headers=auth_headers(user), json=original,
    )
    replay = await client.post(
        "/product-events/batch", headers=auth_headers(user), json=original,
    )
    conflict = await client.post(
        "/product-events/batch",
        headers=auth_headers(user),
        json=event_payload(
            event_id,
            "living_loop_choice_previewed",
            properties={
                **original["events"][0]["properties"],
                "choice_key": "collect_evidence",
            },
            session_id=original["events"][0]["session_id"],
        ),
    )

    assert first.status_code == replay.status_code == 200
    assert first.json() == {"accepted": 1, "duplicates": 0}
    assert replay.json() == {"accepted": 0, "duplicates": 1}
    assert conflict.status_code == 409
    assert await _count(db_session, ProductEvent.event_id == event_id) == 1


async def test_event_user_is_always_derived_from_authentication(
    client, db_session, monkeypatch,
) -> None:
    from app.models.product_event import ProductEvent

    _enable(monkeypatch)
    user, _ = await create_user(db_session, "derived-user")
    attacker_user_id = str(uuid4())
    payload = event_payload(str(uuid4()))
    payload["user_id"] = attacker_user_id

    response = await client.post(
        "/product-events/batch", headers=auth_headers(user), json=payload,
    )

    assert response.status_code == 422
    assert await _count(db_session, ProductEvent.user_id == attacker_user_id) == 0


async def test_client_event_ids_must_use_uuid4_namespace(
    client, db_session, monkeypatch,
) -> None:
    """UUID5 is reserved for stable server-authoritative event identities."""
    _enable(monkeypatch)
    user, _ = await create_user(db_session, "client-uuid-version")
    reserved = str(uuid5(NAMESPACE_URL, "simverse-world:reserved-client-id"))

    response = await client.post(
        "/product-events/batch",
        headers=auth_headers(user),
        json=event_payload(reserved),
    )

    assert response.status_code == 422
    assert await _count(db_session) == 0


async def test_product_event_endpoint_has_a_finite_per_ip_rate_limit(
    client, db_session, monkeypatch,
) -> None:
    from app.routers.product_events import PRODUCT_EVENTS_RATE_LIMIT_PER_MINUTE

    _enable(monkeypatch)
    user, _ = await create_user(db_session, "rate-limit")
    assert PRODUCT_EVENTS_RATE_LIMIT_PER_MINUTE == 30

    responses = []
    for _ in range(PRODUCT_EVENTS_RATE_LIMIT_PER_MINUTE + 1):
        responses.append(await client.post(
            "/product-events/batch",
            headers={
                **auth_headers(user),
                "CF-Connecting-IP": "203.0.113.77",
            },
            json=event_payload(str(uuid4())),
        ))

    assert all(response.status_code == 200 for response in responses[:-1])
    assert responses[-1].status_code == 429
