from __future__ import annotations

import json
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest

from app.lab.runtime_ref import server as runtime_server
from app.lab.protocol import ControlCommand
from app.lab.runtime_ref.service_auth import (
    ServiceTokenIssuer,
    canonical_request_digest,
)
from app.lab.runtime_ref.server import create_app, create_entrypoint_app
from app.lab.sandbox.base import HttpAgentAdapter


ISSUER = "simverse-gateway"
AUDIENCE = "lab-runtime"
CURRENT_KID = "runtime-current"
CURRENT_KEY = "runtime-current-secret-at-least-32-bytes"
NEXT_KID = "runtime-next"
NEXT_KEY = "runtime-next-secret-at-least-32-bytes"


@pytest.fixture(autouse=True)
def configured_test_egress(monkeypatch):
    monkeypatch.setenv("LAB_EGRESS_ENABLED", "true")
    monkeypatch.setenv("LAB_EGRESS_SEARCH_ENDPOINT", "http://search.test")


def _service_auth():
    return {
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "keys": {CURRENT_KID: CURRENT_KEY, NEXT_KID: NEXT_KEY},
    }


def _app(path, *, completer_factory=None):
    kwargs = {}
    if completer_factory is not None:
        kwargs["completer_factory"] = completer_factory
    return create_app(
        protocol_version=2,
        runtime_store_path=str(path),
        service_auth=_service_auth(),
        **kwargs,
    )


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://runtime.test"
    )


def _create_body(suffix: str = "one") -> dict:
    return {
        "schema_version": 2,
        "command_id": f"create-{suffix}",
        "run_id": f"run-{suffix}",
        "client_run_id": f"client-{suffix}",
        "epoch": 7,
        "scopes": ["web_search"],
        "budget_usd": 0.5,
        "egress_allowlist": [],
    }


def _token(
    *,
    run_id: str,
    session_id: str,
    epoch: int,
    action: str,
    jti: str,
    kid: str = CURRENT_KID,
    key: str = CURRENT_KEY,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    expires_in: int = 300,
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": issuer,
            "aud": audience,
            "run_id": run_id,
            "session_id": session_id,
            "epoch": epoch,
            "actions": [action],
            "jti": jti,
            "nbf": now - 1,
            "exp": now + expires_in,
        },
        key,
        algorithm="HS256",
        headers={"kid": kid},
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_token(body: dict, **overrides) -> str:
    values = {
        "run_id": body["run_id"],
        "session_id": body["client_run_id"],
        "epoch": body["epoch"],
        "action": "session.create",
        "jti": f"jti-{body['command_id']}",
    }
    values.update(overrides)
    return _token(**values)


def test_v2_app_requires_durable_store_and_service_auth(tmp_path):
    with pytest.raises(ValueError, match="runtime_store_path"):
        create_app(protocol_version=2, service_auth=_service_auth())
    with pytest.raises(ValueError, match="service_auth"):
        create_app(protocol_version=2, runtime_store_path=str(tmp_path / "runtime.db"))
    with pytest.raises(ValueError, match="durable file"):
        create_app(
            protocol_version=2,
            runtime_store_path=":memory:",
            service_auth=_service_auth(),
        )
    with pytest.raises(ValueError, match="unsupported"):
        create_app(protocol_version=3)


def test_standalone_entrypoint_is_explicit_and_v2_fails_closed(tmp_path):
    assert "/runs" not in {
        route.path for route in runtime_server.app.routes if hasattr(route, "path")
    }
    with pytest.raises(ValueError, match="explicitly"):
        create_entrypoint_app({})
    with pytest.raises(ValueError, match="requires store path"):
        create_entrypoint_app({"LAB_RUNTIME_PROTOCOL_VERSION": "2"})
    with pytest.raises(ValueError, match="current and next"):
        create_entrypoint_app(
            {
                "LAB_RUNTIME_PROTOCOL_VERSION": "2",
                "LAB_RUNTIME_STORE_PATH": str(tmp_path / "runtime.db"),
                "LAB_RUNTIME_AUTH_ISSUER": ISSUER,
                "LAB_RUNTIME_AUTH_AUDIENCE": AUDIENCE,
                "LAB_RUNTIME_AUTH_KEYS_JSON": '{"only":"single-key-at-least-32-bytes-long"}',
            }
        )

    v1 = create_entrypoint_app({"LAB_RUNTIME_PROTOCOL_VERSION": "1"})
    assert v1.version == "1.0"

    v2 = create_entrypoint_app(
        {
            "LAB_RUNTIME_PROTOCOL_VERSION": "2",
            "LAB_RUNTIME_STORE_PATH": str(tmp_path / "runtime.db"),
            "LAB_RUNTIME_AUTH_ISSUER": ISSUER,
            "LAB_RUNTIME_AUTH_AUDIENCE": AUDIENCE,
            "LAB_RUNTIME_AUTH_KEYS_JSON": (
                '{"runtime-current":"runtime-current-secret-at-least-32-bytes",'
                '"runtime-next":"runtime-next-secret-at-least-32-bytes"}'
            ),
        }
    )
    assert v2.version == "2.0"
    assert "/runs/{sid}/events" in {
        route.path for route in v2.routes if hasattr(route, "path")
    }


@pytest.mark.anyio
async def test_create_is_fail_closed_and_accepts_current_and_next_keys(tmp_path):
    app = _app(tmp_path / "runtime.db")
    body = _create_body()
    async with _client(app) as client:
        livez = await client.get("/livez")
        assert livez.status_code == 200
        assert livez.json() == {
            "alive": True,
            "service": "lab-runtime",
            "protocol_version": 2,
            "runtime_shard_id": "reference-0",
        }

        missing = await client.post("/runs", json=body)
        assert missing.status_code == 401

        denied_tokens = (
            (_create_token(body, key="wrong-key-at-least-32-bytes-long"), 401),
            (
                _create_token(
                    body, kid="unknown-kid",
                    key="unknown-key-at-least-32-bytes-long",
                ),
                401,
            ),
            (_create_token(body, issuer="other-issuer"), 401),
            (_create_token(body, audience="lab-executor"), 401),
            (_create_token(body, expires_in=-10), 401),
            (_create_token(body, action="events.read"), 403),
            (_create_token(body, epoch=body["epoch"] + 1), 403),
            (_create_token(body, session_id="other-client"), 403),
        )
        for token, expected_status in denied_tokens:
            denied = await client.post("/runs", json=body, headers=_auth(token))
            assert denied.status_code == expected_status, denied.text
            assert denied.status_code != 404

        current = await client.post(
            "/runs", json=body, headers=_auth(_create_token(body))
        )
        assert current.status_code == 201, current.text
        assert current.json()["session_id"]
        assert current.json()["receipt_id"]
        assert current.json()["request_digest"] == canonical_request_digest(body)

        next_body = _create_body("next")
        following = await client.post(
            "/runs",
            json=next_body,
            headers=_auth(
                _create_token(next_body, kid=NEXT_KID, key=NEXT_KEY)
            ),
        )
        assert following.status_code == 201, following.text

        extra = {**_create_body("strict"), "ignored": True}
        strict = await client.post(
            "/runs", json=extra, headers=_auth(_create_token(extra))
        )
        assert strict.status_code == 422


@pytest.mark.anyio
async def test_create_exact_retry_survives_app_restart_and_rejects_cross_binding(tmp_path):
    path = tmp_path / "runtime.db"
    body = _create_body("restart")
    token = _create_token(body, jti="restart-jti")

    async with _client(_app(path)) as first_client:
        first = await first_client.post(
            "/runs", json=body, headers=_auth(token)
        )
    assert first.status_code == 201, first.text

    async with _client(_app(path)) as restarted_client:
        retry = await restarted_client.post(
            "/runs", json=body, headers=_auth(token)
        )
        assert retry.status_code == 201, retry.text
        assert retry.json() == first.json()

        expired_retry = await restarted_client.post(
            "/runs",
            json=body,
            headers=_auth(_create_token(body, jti="restart-jti", expires_in=-10)),
        )
        assert expired_retry.status_code == 401

        changed = deepcopy(body)
        changed["budget_usd"] = 0.75
        replay = await restarted_client.post(
            "/runs", json=changed, headers=_auth(token)
        )
        assert replay.status_code == 403
        assert "not found" not in replay.text.lower()

        other_jti = _create_token(body, jti="different-jti")
        command_reuse = await restarted_client.post(
            "/runs", json=body, headers=_auth(other_jti)
        )
        assert command_reuse.status_code == 403


@pytest.mark.anyio
async def test_run_routes_authenticate_and_bind_before_session_lookup(tmp_path):
    app = _app(tmp_path / "runtime.db")
    create_body = _create_body("routes")
    async with _client(app) as client:
        created = await client.post(
            "/runs",
            json=create_body,
            headers=_auth(_create_token(create_body)),
        )
        assert created.status_code == 201, created.text
        sid = created.json()["session_id"]
        run_id = create_body["run_id"]
        epoch = create_body["epoch"]

        event_token = _token(
            run_id=run_id, session_id=sid, epoch=epoch,
            action="events.read", jti="events-jti",
        )
        events = await client.get(
            f"/runs/{sid}/events", headers=_auth(event_token)
        )
        assert events.status_code == 200, events.text
        stream = events.json()
        assert stream["done"] is False
        assert stream["has_more"] is False
        assert stream["acked_through"] == 0
        assert stream["latest_cursor"] == 1
        assert [event["event_kind"] for event in stream["events"]] == [
            "session_started"
        ]

        unauthenticated_bad_cursor = await client.get(
            f"/runs/{sid}/events", params={"after": "not-an-integer"}
        )
        assert unauthenticated_bad_cursor.status_code == 401
        authenticated_bad_cursor = await client.get(
            f"/runs/{sid}/events",
            params={"after": "not-an-integer"},
            headers=_auth(event_token),
        )
        assert authenticated_bad_cursor.status_code == 422

        missing_auth = await client.get(f"/runs/{sid}/events")
        assert missing_auth.status_code == 401

        wrong_action = await client.get(
            f"/runs/{sid}/events",
            headers=_auth(
                _token(
                    run_id=run_id, session_id=sid, epoch=epoch,
                    action="artifacts.read", jti="wrong-action-jti",
                )
            ),
        )
        assert wrong_action.status_code == 403

        wrong_path = await client.get(
            "/runs/session-does-not-exist/events", headers=_auth(event_token)
        )
        assert wrong_path.status_code == 403
        assert "not found" not in wrong_path.text.lower()

        expired_unknown = await client.get(
            "/runs/unknown/events",
            headers=_auth(
                _token(
                    run_id="unknown-run", session_id="unknown", epoch=epoch,
                    action="events.read", jti="expired-unknown", expires_in=-10,
                )
            ),
        )
        assert expired_unknown.status_code == 401
        assert "not found" not in expired_unknown.text.lower()

        valid_unknown = await client.get(
            "/runs/unknown/events",
            headers=_auth(
                _token(
                    run_id="unknown-run", session_id="unknown", epoch=epoch,
                    action="events.read", jti="valid-unknown",
                )
            ),
        )
        assert valid_unknown.status_code == 404

        wrong_epoch = await client.get(
            f"/runs/{sid}/events",
            headers=_auth(
                _token(
                    run_id=run_id, session_id=sid, epoch=epoch + 1,
                    action="events.read", jti="wrong-epoch",
                )
            ),
        )
        assert wrong_epoch.status_code == 403

        artifact_token = _token(
            run_id=run_id, session_id=sid, epoch=epoch,
            action="artifacts.read", jti="artifacts-jti",
        )
        artifacts = await client.get(
            f"/runs/{sid}/artifacts", headers=_auth(artifact_token)
        )
        assert artifacts.status_code == 409
        assert "pending" in artifacts.text.lower()


@pytest.mark.anyio
async def test_goal_and_result_loop_preserves_auth_before_lookup(tmp_path):
    replies = iter((
        {
            "plan": "ask the Broker",
            "tool": "web.search",
            "query": "auth sentinel",
            "conclusion": "",
        },
        {
            "plan": "finish from the Broker result",
            "tool": None,
            "query": "",
            "conclusion": "broker-backed final",
        },
    ))
    calls = 0

    def completer_factory():
        async def complete(_messages):
            nonlocal calls
            calls += 1
            return json.dumps(next(replies)), 7

        return complete

    app = _app(
        tmp_path / "runtime.db", completer_factory=completer_factory
    )
    create_body = _create_body("scaffold")
    async with _client(app) as client:
        created = await client.post(
            "/runs",
            json=create_body,
            headers=_auth(_create_token(create_body)),
        )
        sid = created.json()["session_id"]
        run_id = create_body["run_id"]
        epoch = create_body["epoch"]

        goal_body = {
            "schema_version": 2,
            "command_id": "goal-scaffold",
            "run_id": run_id,
            "session_id": sid,
            "epoch": epoch,
            "brief": "do not invoke the model yet",
            "scopes": ["web_search"],
        }
        goal_token = _token(
            run_id=run_id, session_id=sid, epoch=epoch,
            action="goal.submit", jti="goal-jti",
        )
        goal = await client.post(
            f"/runs/{sid}/goal", json=goal_body, headers=_auth(goal_token)
        )
        assert goal.status_code == 200, goal.text
        assert goal.json()["state"] == "intent_pending"
        assert calls == 1

        missing_goal = await client.post(f"/runs/{sid}/goal", json=goal_body)
        assert missing_goal.status_code == 401
        wrong_goal_path = await client.post(
            "/runs/other-session/goal", json=goal_body, headers=_auth(goal_token)
        )
        assert wrong_goal_path.status_code == 403

        events_token = _token(
            run_id=run_id, session_id=sid, epoch=epoch,
            action="events.read", jti="goal-events-jti",
        )
        events = await client.get(
            f"/runs/{sid}/events", headers=_auth(events_token)
        )
        intent = next(
            event for event in events.json()["events"]
            if event["event_kind"] == "tool_intent"
        )
        payload = {"sentinel": "BROKER-SENTINEL"}
        result_body = {
            "schema_version": 2,
            "command_id": "result-scaffold",
            "run_id": run_id,
            "session_id": sid,
            "turn_id": intent["turn_id"],
            "intent_id": intent["intent_id"],
            "action_id": "action-1",
            "outcome": "succeeded",
            "payload": payload,
            "result_digest": canonical_request_digest(payload),
            "epoch": epoch,
        }
        result_token = _token(
            run_id=run_id, session_id=sid, epoch=epoch,
            action="tool_result.submit", jti="result-jti",
        )
        result = await client.post(
            f"/runs/{sid}/results", json=result_body,
            headers=_auth(result_token),
        )
        assert result.status_code == 200, result.text
        assert result.json()["state"] == "runtime_acked"
        assert calls == 2

        wrong_result_epoch = deepcopy(result_body)
        wrong_result_epoch["epoch"] = epoch + 1
        denied = await client.post(
            f"/runs/{sid}/results", json=wrong_result_epoch,
            headers=_auth(result_token),
        )
        assert denied.status_code == 403


@pytest.mark.anyio
async def test_control_surfaces_require_runtime_control_before_lookup(tmp_path):
    app = _app(tmp_path / "runtime.db")
    body = _create_body("control")
    async with _client(app) as client:
        created = await client.post(
            "/runs", json=body, headers=_auth(_create_token(body))
        )
        sid = created.json()["session_id"]
        token = _token(
            run_id=body["run_id"], session_id=sid, epoch=body["epoch"],
            action="runtime.control", jti="control-jti",
        )

        for action in ("stop", "cancel", "terminate", "kill"):
            missing = await client.post(f"/runs/{sid}/{action}")
            assert missing.status_code == 401
        stop = await client.post(f"/runs/{sid}/stop", headers=_auth(token))
        assert stop.status_code == 501
        malformed = await client.post(
            f"/runs/{sid}/cancel", content=b'{', headers=_auth(token)
        )
        assert malformed.status_code == 422

        health_missing = await client.get(f"/runs/{sid}/health")
        assert health_missing.status_code == 401
        health = await client.get(
            f"/runs/{sid}/health", headers=_auth(token)
        )
        assert health.status_code == 200
        assert health.json() == {
            "alive": True,
            "cancelled": False,
            "state": "created",
            "epoch": 7,
            "runtime_shard_id": "reference-0",
        }


@pytest.mark.anyio
async def test_runtime_control_is_durable_idempotent_and_cross_bound(tmp_path):
    path = tmp_path / "runtime.db"
    body = _create_body("durable-control")
    app = _app(path)
    async with _client(app) as client:
        created = await client.post(
            "/runs", json=body, headers=_auth(_create_token(body))
        )
        assert created.status_code == 201, created.text
        sid = created.json()["session_id"]

        control = {
            "schema_version": 2,
            "command_id": "runtime-control-command",
            "request_id": "gateway-control-request",
            "run_id": body["run_id"],
            "session_id": sid,
            "target_kind": "runtime",
            "target_id": sid,
            "action": "cancel",
            "epoch": body["epoch"] + 1,
            "deadline_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        }
        token = _token(
            run_id=body["run_id"],
            session_id=sid,
            epoch=control["epoch"],
            action="runtime.control",
            jti="runtime-control-jti",
        )
        first = await client.post(
            f"/runs/{sid}/cancel", json=control, headers=_auth(token)
        )
        assert first.status_code == 200, first.text
        receipt = first.json()
        assert receipt["status"] == "confirmed_stopped"
        assert receipt["runtime_state"] == "cancelled"
        assert receipt["request_id"] == control["request_id"]
        assert receipt["epoch"] == control["epoch"]

        retry = await client.post(
            f"/runs/{sid}/cancel", json=control, headers=_auth(token)
        )
        assert retry.status_code == 200
        assert retry.json() == receipt

        changed = {**control, "request_id": "different-request"}
        replay = await client.post(
            f"/runs/{sid}/cancel", json=changed, headers=_auth(token)
        )
        assert replay.status_code == 403

        stale = {**control, "command_id": "stale-control", "epoch": body["epoch"] - 1}
        stale_token = _token(
            run_id=body["run_id"],
            session_id=sid,
            epoch=stale["epoch"],
            action="runtime.control",
            jti="stale-control-jti",
        )
        denied = await client.post(
            f"/runs/{sid}/cancel", json=stale, headers=_auth(stale_token)
        )
        assert denied.status_code == 403

    async with _client(_app(path)) as restarted:
        durable_retry = await restarted.post(
            f"/runs/{sid}/cancel", json=control, headers=_auth(token)
        )
        assert durable_retry.status_code == 200
        assert durable_retry.json() == receipt


@pytest.mark.anyio
async def test_http_adapter_validates_runtime_control_receipt(tmp_path, monkeypatch):
    app = _app(tmp_path / "runtime.db")
    start = _create_body("adapter-control")
    adapter = HttpAgentAdapter(
        base_url="http://runtime.test",
        service_token_issuer=ServiceTokenIssuer(
            {
                "issuer": ISSUER,
                "audience": AUDIENCE,
                "current_kid": CURRENT_KID,
                "current_key": CURRENT_KEY,
                "token_ttl_seconds": 300,
            }
        ),
    )
    async with _client(app) as client:
        created = await client.post(
            "/runs", json=start, headers=_auth(_create_token(start))
        )
        sid = created.json()["session_id"]
        monkeypatch.setattr("app.http.get_client", lambda: client)
        receipt = await adapter.control_runtime_v2(
            ControlCommand(
                command_id="adapter-control-command",
                request_id="adapter-control-request",
                run_id=start["run_id"],
                session_id=sid,
                target_kind="runtime",
                target_id=sid,
                action="terminate",
                epoch=start["epoch"] + 1,
                deadline_at=datetime.now(UTC) + timedelta(seconds=30),
            )
        )

    assert receipt["status"] == "confirmed_stopped"
    assert receipt["runtime_state"] == "cancelled"
    assert receipt["action"] == "terminate"


@pytest.mark.anyio
async def test_body_routes_authenticate_before_reading_or_validating_json(tmp_path):
    app = _app(tmp_path / "runtime.db")
    create_body = _create_body("body-order")
    create_token = _create_token(create_body)
    malformed = b'{"schema_version":2'
    oversized = b"x" * (256 * 1024 + 1)

    async with _client(app) as client:
        missing = await client.post("/runs", content=malformed)
        assert missing.status_code == 401
        wrong_action = await client.post(
            "/runs",
            content=malformed,
            headers=_auth(_create_token(create_body, action="events.read")),
        )
        assert wrong_action.status_code == 403
        invalid = await client.post(
            "/runs", content=malformed, headers=_auth(create_token)
        )
        assert invalid.status_code == 422
        too_large = await client.post(
            "/runs", content=oversized, headers=_auth(create_token)
        )
        assert too_large.status_code == 413
        unauthenticated_large = await client.post("/runs", content=oversized)
        assert unauthenticated_large.status_code == 401

        created = await client.post(
            "/runs", json=create_body, headers=_auth(create_token)
        )
        sid = created.json()["session_id"]
        common = {
            "run_id": create_body["run_id"],
            "session_id": sid,
            "epoch": create_body["epoch"],
        }
        route_tokens = (
            ("goal", "goal.submit"),
            ("results", "tool_result.submit"),
            ("approve", "runtime.control"),
        )
        for route, action in route_tokens:
            token = _token(
                **common, action=action, jti=f"malformed-{route}"
            )
            no_auth = await client.post(f"/runs/{sid}/{route}", content=malformed)
            assert no_auth.status_code == 401
            wrong_path = await client.post(
                f"/runs/other-session/{route}",
                content=malformed,
                headers=_auth(token),
            )
            assert wrong_path.status_code == 403
            valid_auth = await client.post(
                f"/runs/{sid}/{route}", content=malformed, headers=_auth(token)
            )
            assert valid_auth.status_code == 422

        string_epoch = deepcopy(create_body)
        string_epoch["command_id"] = "create-string-epoch"
        string_epoch["epoch"] = "7"
        strict = await client.post(
            "/runs", json=string_epoch, headers=_auth(create_token)
        )
        assert strict.status_code == 422

        depth_session = "depth-session"
        depth_token = _token(
            run_id=create_body["run_id"],
            session_id=depth_session,
            epoch=create_body["epoch"],
            action="tool_result.submit",
            jti="deep-json",
        )
        nested: object = "leaf"
        for _ in range(40):
            nested = {"child": nested}
        deep_payload = {"nested": nested}
        deep_result = {
            "schema_version": 2,
            "command_id": "deep-json-result",
            "run_id": create_body["run_id"],
            "session_id": depth_session,
            "turn_id": "deep-turn",
            "intent_id": "deep-intent",
            "action_id": "deep-action",
            "outcome": "succeeded",
            "payload": deep_payload,
            "result_digest": canonical_request_digest(deep_payload),
            "epoch": create_body["epoch"],
        }
        depth_rejected = await client.post(
            f"/runs/{depth_session}/results",
            json=deep_result,
            headers=_auth(depth_token),
        )
        assert depth_rejected.status_code == 422
        assert depth_rejected.json()["detail"] == "invalid_request_body"

        recursive_json = (
            b'{"payload":' + b"[" * 1500 + b"0" + b"]" * 1500 + b"}"
        )
        recursion_rejected = await client.post(
            f"/runs/{depth_session}/results",
            content=recursive_json,
            headers=_auth(depth_token),
        )
        assert recursion_rejected.status_code == 422
        assert recursion_rejected.json()["detail"] == "invalid_request_body"
