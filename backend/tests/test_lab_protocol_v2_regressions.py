"""Approved-v10 protocol-v2 regression contracts (AC05, AC07-AC09, AC14).

These are behavior tests for the release blockers that the protocol-v1 suite
cannot expose.  The expected-red baseline predates the v2 state/API surfaces;
imports and feature construction therefore stay inside tests so collection
remains useful while the implementation is being built.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from copy import deepcopy
from datetime import UTC, datetime

import httpx
import jwt
import pytest
from sqlalchemy import func, select

from app.lab import protocol, queue, supervision
from app.lab.protocol import RunEventEnvelope
from app.lab.runtime_ref.server import create_app
from app.models.lab_event import LabRunEvent
from app.models.lab_run import LabRun


ISSUER = "simverse-gateway"
AUDIENCE = "lab-runtime"
KID = "runtime-current"
KEY = "runtime-current-test-secret-at-least-32-bytes"


@pytest.fixture(autouse=True)
def configured_test_egress(monkeypatch):
    monkeypatch.setenv("LAB_EGRESS_ENABLED", "true")
    monkeypatch.setenv("LAB_EGRESS_SEARCH_ENDPOINT", "http://search.test")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _token(
    *,
    run_id: str,
    session_id: str,
    epoch: int,
    action: str,
    jti: str | None = None,
    audience: str = AUDIENCE,
    expires_in: int = 300,
    key: str = KEY,
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": audience,
            "run_id": run_id,
            "session_id": session_id,
            "epoch": epoch,
            "actions": [action],
            "jti": jti or str(uuid.uuid4()),
            "nbf": now - 1,
            "exp": now + expires_in,
        },
        key,
        algorithm="HS256",
        headers={"kid": KID},
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class ScriptedCompleter:
    """One intent, then a conclusion derived from the actual Broker result."""

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def __call__(self, messages: list[dict]) -> tuple[str, int]:
        self.calls.append(deepcopy(messages))
        if len(self.calls) == 1:
            return _canonical(
                {
                    "plan": "query the brokered source",
                    "tool": "web.search",
                    "query": "approved-v10 sentinel",
                    "conclusion": "",
                }
            ), 11
        transcript = _canonical(messages)
        return _canonical(
            {
                "plan": "use the real broker result",
                "tool": None,
                "query": "",
                "conclusion": f"final derived from {transcript}",
            }
        ), 13


def _v2_app(tmp_path, completer: ScriptedCompleter):
    """Build the public runtime HTTP surface with an isolated durable store."""
    try:
        return create_app(
            completer_factory=lambda: completer,
            max_steps=3,
            protocol_version=2,
            runtime_store_path=str(tmp_path / "runtime-v2.sqlite3"),
            service_auth={
                "issuer": ISSUER,
                "audience": AUDIENCE,
                "keys": {
                    KID: KEY,
                    "runtime-next": "runtime-next-test-secret-at-least-32-bytes",
                },
            },
        )
    except TypeError as exc:  # expected-red on the 77b64c2 baseline
        raise AssertionError(
            "runtime_ref.create_app must expose protocol_version, durable "
            "runtime_store_path, and per-audience service_auth inputs"
        ) from exc


async def _open_paused_run(client: httpx.AsyncClient, *, run_id: str, epoch: int = 7):
    client_run_id = f"client-{run_id}-{epoch}"
    create_body = {
        "schema_version": 2,
        "command_id": f"create-{run_id}",
        "run_id": run_id,
        "client_run_id": client_run_id,
        "epoch": epoch,
        "scopes": ["web_search"],
        "budget_usd": 0.5,
        "egress_allowlist": [],
    }
    create_token = _token(
        run_id=run_id,
        session_id=client_run_id,
        epoch=epoch,
        action="session.create",
    )
    created = await client.post("/runs", json=create_body, headers=_auth(create_token))
    assert created.status_code in {200, 201}, created.text
    sid = created.json()["session_id"]

    goal_body = {
        "schema_version": 2,
        "command_id": f"goal-{run_id}",
        "run_id": run_id,
        "session_id": sid,
        "epoch": epoch,
        "brief": "produce a sentinel-backed report",
        "scopes": ["web_search"],
    }
    goal_token = _token(
        run_id=run_id, session_id=sid, epoch=epoch, action="goal.submit"
    )
    goal = await client.post(
        f"/runs/{sid}/goal", json=goal_body, headers=_auth(goal_token)
    )
    assert goal.status_code in {200, 202}, goal.text
    return sid, epoch


async def _events(client: httpx.AsyncClient, run_id: str, sid: str, epoch: int):
    token = _token(
        run_id=run_id, session_id=sid, epoch=epoch, action="events.read"
    )
    response = await client.get(
        f"/runs/{sid}/events", params={"after": 0}, headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    return response.json()


def _result_body(
    *, run_id: str, sid: str, epoch: int, turn_id: str, intent_id: str,
    outcome: str, payload: dict, command_id: str = "result-1",
    action_id: str = "broker-action-1",
) -> dict:
    return {
        "schema_version": 2,
        "command_id": command_id,
        "run_id": run_id,
        "session_id": sid,
        "turn_id": turn_id,
        "intent_id": intent_id,
        "action_id": action_id,
        "outcome": outcome,
        "payload": payload,
        "result_digest": _digest(payload),
        "epoch": epoch,
    }


@pytest.mark.anyio
async def test_protocol_version_is_creation_time_state_not_a_mutable_label(db_session):
    run = LabRun(
        id="v2-immutable", task_id="task-v2", researcher_slug="sage",
        adapter="simverse_ref", status="queued", protocol_version=2,
    )
    db_session.add(run)
    await db_session.commit()
    run_id = run.id

    with pytest.raises(Exception) as rejected:
        run.protocol_version = 1
        await db_session.commit()
    assert "protocol" in str(rejected.value).lower()
    await db_session.rollback()
    db_session.expire_all()
    assert (await db_session.get(LabRun, run_id)).protocol_version == 2


@pytest.mark.anyio
async def test_v1_v2_queues_are_physically_split_and_never_cross_claim():
    with pytest.raises(TypeError):
        await queue.enqueue_run("implicit-version-is-forbidden")

    await queue.enqueue_run("run-v1", protocol_version=1)
    await queue.enqueue_run("run-v2", protocol_version=2)

    assert await queue.dequeue_run(protocol_version=1, timeout=1) == "run-v1"
    # An empty v1 queue must not fall through to the still-pending v2 queue.
    assert await queue.dequeue_run(protocol_version=1, timeout=0.01) is None
    assert await queue.dequeue_run(protocol_version=2, timeout=1) == "run-v2"

    await queue.ack_run("run-v1", protocol_version=1)
    assert await queue.list_processing(protocol_version=1) == []
    assert await queue.list_processing(protocol_version=2) == ["run-v2"]

    await queue.requeue_run("run-v2", protocol_version=2)
    assert await queue.dequeue_run(protocol_version=1, timeout=0.01) is None
    assert await queue.dequeue_run(protocol_version=2, timeout=1) == "run-v2"


@pytest.mark.anyio
async def test_runtime_pauses_on_intent_without_fake_observation_final_or_artifact(tmp_path):
    completer = ScriptedCompleter()
    app = _v2_app(tmp_path, completer)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://runtime.test"
    ) as client:
        run_id = "pause-at-intent"
        sid, epoch = await _open_paused_run(client, run_id=run_id)
        stream = await _events(client, run_id, sid, epoch)

        intents = [e for e in stream["events"] if e["event_kind"] == "tool_intent"]
        assert len(intents) == 1
        assert stream["done"] is False
        assert not any(
            e["event_kind"] in {"tool_result", "observation", "final"}
            for e in stream["events"]
        )
        assert len(completer.calls) == 1

        artifact_token = _token(
            run_id=run_id, session_id=sid, epoch=epoch, action="artifacts.read"
        )
        blocked = await client.get(
            f"/runs/{sid}/artifacts", headers=_auth(artifact_token)
        )
        assert blocked.status_code == 409
        assert "pending" in blocked.text.lower()


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", ["succeeded", "denied", "failed"])
async def test_real_broker_outcome_resumes_the_same_runtime_turn(tmp_path, outcome):
    completer = ScriptedCompleter()
    app = _v2_app(tmp_path, completer)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://runtime.test"
    ) as client:
        run_id = f"resume-{outcome}"
        sid, epoch = await _open_paused_run(client, run_id=run_id)
        before = await _events(client, run_id, sid, epoch)
        intent = next(e for e in before["events"] if e["event_kind"] == "tool_intent")
        payload = {"sentinel": f"BROKER-{outcome.upper()}", "status": outcome}
        body = _result_body(
            run_id=run_id, sid=sid, epoch=epoch,
            turn_id=intent["turn_id"], intent_id=intent["intent_id"],
            outcome=outcome, payload=payload,
        )
        token = _token(
            run_id=run_id, session_id=sid, epoch=epoch,
            action="tool_result.submit", jti=f"jti-{run_id}",
        )
        response = await client.post(
            f"/runs/{sid}/results", json=body, headers=_auth(token)
        )
        assert response.status_code in {200, 202}, response.text

        after = await _events(client, run_id, sid, epoch)
        result_event = next(
            e for e in after["events"] if e["event_kind"] == "tool_result"
        )
        assert result_event["turn_id"] == intent["turn_id"]
        assert result_event["intent_id"] == intent["intent_id"]
        assert result_event["outcome"] == outcome
        assert result_event["payload"] == payload
        assert len(completer.calls) == 2
        assert payload["sentinel"] in _canonical(completer.calls[1])
        assert outcome in _canonical(completer.calls[1])


@pytest.mark.anyio
async def test_broker_sentinel_reaches_final_artifact_with_result_provenance(tmp_path):
    completer = ScriptedCompleter()
    app = _v2_app(tmp_path, completer)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://runtime.test"
    ) as client:
        run_id = "sentinel-provenance"
        sid, epoch = await _open_paused_run(client, run_id=run_id)
        intent = next(
            e for e in (await _events(client, run_id, sid, epoch))["events"]
            if e["event_kind"] == "tool_intent"
        )
        payload = {"sentinel": "BROKER-SENTINEL-9F41", "records": [1, 2, 3]}
        body = _result_body(
            run_id=run_id, sid=sid, epoch=epoch,
            turn_id=intent["turn_id"], intent_id=intent["intent_id"],
            outcome="succeeded", payload=payload,
            command_id="sentinel-result", action_id="sentinel-action",
        )
        token = _token(
            run_id=run_id, session_id=sid, epoch=epoch,
            action="tool_result.submit", jti="sentinel-jti",
        )
        result = await client.post(
            f"/runs/{sid}/results", json=body, headers=_auth(token)
        )
        assert result.status_code in {200, 202}, result.text

        artifact_token = _token(
            run_id=run_id, session_id=sid, epoch=epoch, action="artifacts.read"
        )
        artifacts_response = await client.get(
            f"/runs/{sid}/artifacts", headers=_auth(artifact_token)
        )
        assert artifacts_response.status_code == 200, artifacts_response.text
        artifacts = artifacts_response.json()["artifacts"]
        assert len(artifacts) == 1
        artifact = artifacts[0]
        assert artifact["provider_artifact_id"]
        assert artifact["producer_action_id"] == body["action_id"]
        assert artifact["declared_byte_size"] > 0
        assert len(artifact["expected_sha256"]) == 64
        assert artifact["upload_state"] == "pending"
        assert "text_md" not in artifact


@pytest.mark.anyio
async def test_scoped_auth_exact_retry_is_idempotent_but_cross_binding_replay_is_denied(tmp_path):
    completer = ScriptedCompleter()
    app = _v2_app(tmp_path, completer)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://runtime.test"
    ) as client:
        run_id = "auth-binding"
        sid, epoch = await _open_paused_run(client, run_id=run_id)
        intent = next(
            e for e in (await _events(client, run_id, sid, epoch))["events"]
            if e["event_kind"] == "tool_intent"
        )
        body = _result_body(
            run_id=run_id, sid=sid, epoch=epoch,
            turn_id=intent["turn_id"], intent_id=intent["intent_id"],
            outcome="succeeded", payload={"sentinel": "AUTH-SENTINEL"},
        )
        jti = "single-use-binding-jti"
        token = _token(
            run_id=run_id, session_id=sid, epoch=epoch,
            action="tool_result.submit", jti=jti,
        )
        first = await client.post(
            f"/runs/{sid}/results", json=body, headers=_auth(token)
        )
        retry = await client.post(
            f"/runs/{sid}/results", json=body, headers=_auth(token)
        )
        assert first.status_code in {200, 202}, first.text
        assert retry.status_code in {200, 202}, retry.text
        assert retry.json() == first.json()
        assert retry.json()["receipt_id"]
        assert retry.json()["request_digest"] == _digest(body)
        assert len(completer.calls) == 2  # goal + one result resume; retry did no effect

        mutations: list[tuple[str, str, dict, str]] = []
        for field, value in (
            ("command_id", "other-command"),
            ("run_id", "other-run"),
            ("session_id", "other-session"),
            ("epoch", epoch + 1),
            ("action_id", "other-action"),
        ):
            changed = deepcopy(body)
            changed[field] = value
            mutations.append((field, sid, changed, token))
        changed_payload = deepcopy(body)
        changed_payload["payload"] = {"sentinel": "DIFFERENT"}
        changed_payload["result_digest"] = _digest(changed_payload["payload"])
        mutations.append(("request_digest", sid, changed_payload, token))
        mutations.append((
            "path_session", "session-that-does-not-exist", body, token,
        ))
        mutations.append((
            "audience", sid, body,
            _token(run_id=run_id, session_id=sid, epoch=epoch,
                   action="tool_result.submit", jti=jti, audience="lab-executor"),
        ))
        mutations.append((
            "action", sid, body,
            _token(run_id=run_id, session_id=sid, epoch=epoch,
                   action="runtime.control", jti=jti),
        ))

        for label, path_sid, changed, replay_token in mutations:
            denied = await client.post(
                f"/runs/{path_sid}/results", json=changed,
                headers=_auth(replay_token),
            )
            assert denied.status_code in {401, 403}, (label, denied.text)
            assert denied.status_code != 404
            assert "not found" not in denied.text.lower()

        expired = _token(
            run_id=run_id, session_id=sid, epoch=epoch,
            action="tool_result.submit", jti=jti, expires_in=-10,
        )
        expired_retry = await client.post(
            f"/runs/{sid}/results", json=body, headers=_auth(expired)
        )
        assert expired_retry.status_code == 401
        assert len(completer.calls) == 2


def _event_builder(run_id: str, cursor: int):
    def build(seq: int) -> RunEventEnvelope:
        return RunEventEnvelope(
            event_id=str(uuid.uuid4()), tenant_id="tenant-v2", run_id=run_id,
            task_id="task-v2", seq=seq, type="plan.updated", actor="runtime",
            fencing_epoch=0, policy_version="lab-policy-v2",
            occurred_at=datetime.now(UTC),
            payload={"cursor": cursor, "summary": f"event-{cursor}"},
        )
    return build


@pytest.mark.anyio
async def test_committed_replay_and_backpressure_preserve_every_event(db_session, monkeypatch):
    monkeypatch.setattr(protocol, "MAX_UNACKED_EVENTS", 128)
    manifest = protocol.HandshakeManifest(
        protocol_version=protocol.PROTOCOL_VERSION,
        runtime="v2-fake", runtime_version="2",
        capabilities=["broker_mediation"],
    )
    session = await supervision.open_session(
        db_session, run_id="flow-control-v2", manifest=manifest
    )
    for cursor in range(1, 129):
        await supervision.ingest_provider_event(
            db_session, session, provider_cursor=cursor,
            envelope_builder=_event_builder("flow-control-v2", cursor),
        )
    with pytest.raises(supervision.Backpressure):
        await supervision.ingest_provider_event(
            db_session, session, provider_cursor=129,
            envelope_builder=_event_builder("flow-control-v2", 129),
        )
    count = (await db_session.execute(
        select(func.count()).select_from(LabRunEvent)
        .where(LabRunEvent.run_id == "flow-control-v2")
    )).scalar_one()
    assert count == 128
    assert session.provider_cursor_acked == 0  # durable rows exist before ACK

    await supervision.ack_through(db_session, session, provider_cursor=128)
    await supervision.ingest_provider_event(
        db_session, session, provider_cursor=129,
        envelope_builder=_event_builder("flow-control-v2", 129),
    )
    await supervision.ack_through(db_session, session, provider_cursor=129)
    assert session.provider_cursor_acked == 129
    assert session.unacked_events == 0
    assert supervision.replay_window(session) == 130

    replay = await supervision.ingest_provider_event(
        db_session, session, provider_cursor=129,
        envelope_builder=_event_builder("flow-control-v2", 129),
    )
    assert replay is None
    count = (await db_session.execute(
        select(func.count()).select_from(LabRunEvent)
        .where(LabRunEvent.run_id == "flow-control-v2")
    )).scalar_one()
    assert count == 129
