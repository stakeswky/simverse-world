"""Runtime-local protocol-v2 result-loop and replay contracts."""
from __future__ import annotations

import sqlite3
from copy import deepcopy
from datetime import UTC, datetime

import httpx
import pytest

from app.lab.protocol import (
    MAX_COMMAND_BYTES,
    MAX_EVENT_BYTES,
    MAX_UNACKED_BYTES,
    RuntimeEvent,
    ToolResultCommand,
)
from app.lab.runtime_ref.service_auth import (
    RequestSchemaError,
    canonical_json_bytes,
)
from app.lab.runtime_ref.server import create_app
from app.lab.runtime_ref.store import (
    RuntimeStore,
    RuntimeStoreBackpressure,
    RuntimeStoreConflict,
    STORE_VERSION,
)
from tests.test_lab_protocol_v2_regressions import (
    AUDIENCE,
    ISSUER,
    KEY,
    KID,
    ScriptedCompleter,
    _auth,
    _digest,
    _events,
    _open_paused_run,
    _result_body,
    _token,
)


@pytest.fixture(autouse=True)
def configured_test_egress(monkeypatch):
    monkeypatch.setenv("LAB_EGRESS_ENABLED", "true")
    monkeypatch.setenv("LAB_EGRESS_SEARCH_ENDPOINT", "http://search.test")


def _app(path, completer):
    return create_app(
        completer_factory=lambda: completer,
        max_steps=3,
        protocol_version=2,
        runtime_store_path=str(path),
        service_auth={
            "issuer": ISSUER,
            "audience": AUDIENCE,
            "keys": {
                KID: KEY,
                "runtime-next": "runtime-next-test-secret-at-least-32-bytes",
            },
        },
    )


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://runtime.test",
    )


@pytest.mark.anyio
async def test_runtime_store_migrates_phase2_durable_volume(tmp_path):
    path = tmp_path / "runtime-v1.sqlite3"
    db = sqlite3.connect(path)
    try:
        db.executescript(
            """
            PRAGMA user_version = 1;
            CREATE TABLE runtime_sessions (
                session_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                client_run_id TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                scopes_json TEXT NOT NULL,
                budget_usd REAL NOT NULL,
                egress_allowlist_json TEXT NOT NULL,
                state TEXT NOT NULL,
                checkpoint_json TEXT,
                next_event_cursor INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (client_run_id, epoch),
                UNIQUE (run_id, epoch)
            );
            CREATE TABLE runtime_events (
                session_id TEXT NOT NULL,
                cursor INTEGER NOT NULL,
                event_id TEXT NOT NULL UNIQUE,
                event_kind TEXT NOT NULL,
                turn_id TEXT,
                intent_id TEXT,
                outcome TEXT,
                payload_json TEXT NOT NULL,
                event_digest TEXT NOT NULL,
                dedupe_key TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, cursor),
                UNIQUE (session_id, dedupe_key)
            );
            CREATE TABLE runtime_intents (
                session_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                intent_id TEXT NOT NULL,
                tool TEXT NOT NULL,
                args_json TEXT NOT NULL,
                state TEXT NOT NULL,
                result_digest TEXT,
                result_outcome TEXT,
                result_payload_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, intent_id),
                UNIQUE (session_id, turn_id)
            );
            INSERT INTO runtime_sessions (
                session_id, run_id, client_run_id, epoch, scopes_json,
                budget_usd, egress_allowlist_json, state, checkpoint_json,
                next_event_cursor
            ) VALUES (
                'phase2-session', 'phase2-run', 'phase2-client', 7,
                '["web_search"]', 0.5, '[]', 'created', NULL, 1
            );
            INSERT INTO runtime_events (
                session_id, cursor, event_id, event_kind, turn_id, intent_id,
                outcome, payload_json, event_digest, dedupe_key, created_at
            ) VALUES (
                'phase2-session', 1, 'phase2-event', 'think', 'phase2-turn',
                NULL, NULL, '{"legacy":"payload"}',
                'phase2-event-digest', 'phase2-event-dedupe',
                '2026-07-21 01:02:03'
            );
            UPDATE runtime_sessions
            SET next_event_cursor = 2
            WHERE session_id = 'phase2-session';
            """
        )
        db.commit()
    finally:
        db.close()

    store = RuntimeStore(path)
    restored = await store.get_session("phase2-session")
    assert restored is not None
    assert restored.acked_event_cursor == 0
    assert restored.next_event_cursor == 2
    check = sqlite3.connect(path)
    try:
        assert check.execute("PRAGMA user_version").fetchone()[0] == STORE_VERSION
        event_columns = {
            row[1] for row in check.execute("PRAGMA table_info(runtime_events)")
        }
        assert {"tool_name", "tool_args_json", "tool_args_digest", "event_bytes"} <= event_columns
        artifact_columns = {
            row[1] for row in check.execute("PRAGMA table_info(runtime_artifacts)")
        }
        assert {
            "content_type",
            "declared_byte_size",
            "expected_sha256",
            "upload_state",
            "upload_receipt_json",
        } <= artifact_columns
        migrated_bytes = check.execute(
            "SELECT event_bytes FROM runtime_events "
            "WHERE session_id = 'phase2-session' AND cursor = 1"
        ).fetchone()[0]
        expected_envelope = RuntimeEvent(
            event_id="phase2-event",
            run_id="phase2-run",
            session_id="phase2-session",
            cursor=1,
            epoch=7,
            event_kind="think",
            turn_id="phase2-turn",
            payload={"legacy": "payload"},
            occurred_at=datetime(2026, 7, 21, 1, 2, 3, tzinfo=UTC),
        ).model_dump(mode="json")
        assert migrated_bytes == len(
            canonical_json_bytes(expected_envelope, max_bytes=MAX_EVENT_BYTES)
        )
        assert migrated_bytes < MAX_EVENT_BYTES
    finally:
        check.close()


@pytest.mark.anyio
async def test_runtime_store_backpressure_waits_for_explicit_ack(tmp_path):
    store = RuntimeStore(tmp_path / "runtime-window.sqlite3")
    session = await store.create_or_get_session(
        run_id="store-window",
        client_run_id="client-store-window",
        epoch=7,
        scopes=[],
    )
    events = []
    for cursor in range(1, 129):
        events.append(await store.append_event(
            session.session_id,
            event_kind="think",
            payload={"cursor": cursor},
            dedupe_key=f"store-window:{cursor}",
        ))
    replay = await store.append_event(
        session.session_id,
        event_kind="think",
        payload={"cursor": 128},
        dedupe_key="store-window:128",
    )
    assert replay == events[-1]
    with pytest.raises(RuntimeStoreBackpressure, match="count"):
        await store.append_event(
            session.session_id,
            event_kind="think",
            payload={"cursor": 129},
            dedupe_key="store-window:129",
        )

    acked = await store.acknowledge_events(session.session_id, cursor=128)
    assert acked.acked_event_cursor == 128
    appended = await store.append_event(
        session.session_id,
        event_kind="think",
        payload={"cursor": 129},
        dedupe_key="store-window:129",
    )
    assert appended.cursor == 129
    with pytest.raises(RuntimeStoreConflict, match="regressed"):
        await store.acknowledge_events(session.session_id, cursor=127)


async def _open_fixed_goal(client, *, run_id: str, epoch: int = 7):
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
        jti=f"create-fixed-{run_id}",
    )
    created = await client.post(
        "/runs", json=create_body, headers=_auth(create_token)
    )
    assert created.status_code == 201, created.text
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
        run_id=run_id,
        session_id=sid,
        epoch=epoch,
        action="goal.submit",
        jti=f"goal-fixed-{run_id}",
    )
    goal = await client.post(
        f"/runs/{sid}/goal", json=goal_body, headers=_auth(goal_token)
    )
    assert goal.status_code == 200, goal.text
    return sid, epoch, goal_body, goal_token, goal


@pytest.mark.anyio
async def test_handshake_is_authenticated_and_hashes_the_frozen_protocol(tmp_path):
    app = _app(tmp_path / "runtime.sqlite3", ScriptedCompleter())
    token = _token(
        run_id="handshake-run",
        session_id="client-handshake-run-7",
        epoch=7,
        action="runtime.handshake",
        jti="handshake-jti",
    )
    async with _client(app) as client:
        assert (await client.get("/handshake")).status_code == 401
        response = await client.get("/handshake", headers=_auth(token))

    assert response.status_code == 200, response.text
    proof = response.json()
    assert proof["manifest"]["provider_name"] == "simverse_ref"
    assert proof["manifest"]["effect_mode"] == "broker_only"
    assert "broker_mediation" in proof["manifest"]["capabilities"]
    assert len(proof["protocol_schema_hash"]) == 64
    assert set(proof["schema_hashes"]) == {
        "runtime_event",
        "tool_result_command",
    }
    assert proof["limits"]["max_unacked_events"] == 128


@pytest.mark.anyio
async def test_goal_receipt_and_paused_turn_survive_runtime_restart(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    completer = ScriptedCompleter()
    run_id = "goal-restart"

    async with _client(_app(path, completer)) as client:
        sid, epoch, goal_body, goal_token, first = await _open_fixed_goal(
            client, run_id=run_id
        )
        initial = await _events(client, run_id, sid, epoch)
        intent = next(
            event for event in initial["events"]
            if event["event_kind"] == "tool_intent"
        )

    async with _client(_app(path, completer)) as restarted:
        retry = await restarted.post(
            f"/runs/{sid}/goal",
            json=goal_body,
            headers=_auth(goal_token),
        )
        replayed = await _events(restarted, run_id, sid, epoch)

    assert retry.status_code == 200, retry.text
    assert retry.json() == first.json()
    assert len(completer.calls) == 1
    assert [event["turn_id"] for event in replayed["events"] if event["intent_id"]] == [
        intent["turn_id"]
    ]


@pytest.mark.anyio
async def test_events_are_full_runtime_envelopes_and_ack_is_explicit(tmp_path):
    completer = ScriptedCompleter()
    app = _app(tmp_path / "runtime.sqlite3", completer)
    run_id = "event-ack"
    async with _client(app) as client:
        sid, epoch = await _open_paused_run(client, run_id=run_id)
        stream = await _events(client, run_id, sid, epoch)
        parsed = [RuntimeEvent.model_validate(event) for event in stream["events"]]
        assert [event.cursor for event in parsed] == list(range(1, len(parsed) + 1))
        last_cursor = parsed[-1].cursor

        body = {
            "schema_version": 2,
            "command_id": "ack-events-1",
            "run_id": run_id,
            "session_id": sid,
            "epoch": epoch,
            "cursor": last_cursor,
        }
        token = _token(
            run_id=run_id,
            session_id=sid,
            epoch=epoch,
            action="events.ack",
            jti="ack-events-jti",
        )
        first = await client.post(
            f"/runs/{sid}/events/ack", json=body, headers=_auth(token)
        )
        retry = await client.post(
            f"/runs/{sid}/events/ack", json=body, headers=_auth(token)
        )
        assert first.status_code == 200, first.text
        assert retry.json() == first.json()
        assert first.json()["acked_through"] == last_cursor

        beyond = {**body, "command_id": "ack-events-beyond", "cursor": last_cursor + 1}
        beyond_token = _token(
            run_id=run_id,
            session_id=sid,
            epoch=epoch,
            action="events.ack",
            jti="ack-events-beyond-jti",
        )
        refused = await client.post(
            f"/runs/{sid}/events/ack", json=beyond, headers=_auth(beyond_token)
        )
        assert refused.status_code == 409


@pytest.mark.anyio
async def test_event_poll_obeys_gateway_remaining_window_without_implicit_ack(tmp_path):
    completer = ScriptedCompleter()
    app = _app(tmp_path / "runtime.sqlite3", completer)
    run_id = "event-window"
    async with _client(app) as client:
        sid, epoch = await _open_paused_run(client, run_id=run_id)
        token = _token(
            run_id=run_id,
            session_id=sid,
            epoch=epoch,
            action="events.read",
            jti="event-window-jti",
        )
        one = await client.get(
            f"/runs/{sid}/events",
            params={"after": 0, "limit": 1},
            headers=_auth(token),
        )
        assert one.status_code == 200, one.text
        assert len(one.json()["events"]) == 1
        assert one.json()["has_more"] is True
        assert one.json()["acked_through"] == 0

        no_room = await client.get(
            f"/runs/{sid}/events",
            params={"after": 0, "max_bytes": 1},
            headers=_auth(token),
        )
        assert no_room.status_code == 200, no_room.text
        assert no_room.json()["events"] == []
        assert no_room.json()["has_more"] is True
        assert no_room.json()["acked_through"] == 0

        latest = no_room.json()["latest_cursor"]
        for params in (
            {"after": latest + 1},
            {"limit": 129},
            {"max_bytes": 4 * 1024 * 1024 + 1},
            [("limit", "1"), ("limit", "2")],
        ):
            refused = await client.get(
                f"/runs/{sid}/events", params=params, headers=_auth(token)
            )
            assert refused.status_code == 422, (params, refused.text)

        unauthenticated = await client.get(
            f"/runs/{sid}/events", params={"limit": 129}
        )
        assert unauthenticated.status_code == 401


@pytest.mark.anyio
async def test_result_payload_uses_protocol_command_size_cap(tmp_path):
    calls: list[list[dict]] = []

    async def completer(messages):
        calls.append(messages)
        if len(calls) == 1:
            return (
                '{"plan":"query","tool":"web.search",'
                '"query":"command cap","conclusion":""}',
                11,
            )
        return (
            '{"plan":"finish","tool":null,"query":"",'
            '"conclusion":"maximum command accepted"}',
            13,
        )

    app = _app(tmp_path / "runtime.sqlite3", completer)
    run_id = "result-command-cap"
    async with _client(app) as client:
        sid, epoch = await _open_paused_run(client, run_id=run_id)
        intent = next(
            event
            for event in (await _events(client, run_id, sid, epoch))["events"]
            if event["event_kind"] == "tool_intent"
        )

        oversized_payload = {"blob": "x" * MAX_COMMAND_BYTES}
        oversized_body = _result_body(
            run_id=run_id,
            sid=sid,
            epoch=epoch,
            turn_id=intent["turn_id"],
            intent_id=intent["intent_id"],
            outcome="succeeded",
            payload=oversized_payload,
            command_id="result-over-command-cap",
            action_id="result-over-command-cap-action",
        )
        oversized_token = _token(
            run_id=run_id,
            session_id=sid,
            epoch=epoch,
            action="tool_result.submit",
            jti="result-over-command-cap-jti",
        )
        first_rejected = await client.post(
            f"/runs/{sid}/results",
            json=oversized_body,
            headers=_auth(oversized_token),
        )
        retry_rejected = await client.post(
            f"/runs/{sid}/results",
            json=oversized_body,
            headers=_auth(oversized_token),
        )
        assert first_rejected.status_code == 413
        assert retry_rejected.status_code == 413
        assert first_rejected.json()["detail"] == "request_body_too_large"
        assert retry_rejected.json() == first_rejected.json()
        assert len(calls) == 1

        def command_with_blob(size: int) -> dict:
            return _result_body(
                run_id=run_id,
                sid=sid,
                epoch=epoch,
                turn_id=intent["turn_id"],
                intent_id=intent["intent_id"],
                outcome="succeeded",
                payload={"blob": "!" * size},
                command_id="c" * 200,
                action_id="a" * 200,
            )

        fixed_bytes = len(
            canonical_json_bytes(
                command_with_blob(0), max_bytes=MAX_COMMAND_BYTES
            )
        )
        max_blob_bytes = MAX_COMMAND_BYTES - fixed_bytes
        valid_body = command_with_blob(max_blob_bytes)
        encoded_valid = canonical_json_bytes(valid_body, max_bytes=MAX_COMMAND_BYTES)
        assert 64 * 1024 < len(encoded_valid) <= MAX_COMMAND_BYTES
        assert MAX_COMMAND_BYTES - len(encoded_valid) <= 1
        with pytest.raises(RequestSchemaError):
            canonical_json_bytes(
                command_with_blob(max_blob_bytes + 1),
                max_bytes=MAX_COMMAND_BYTES,
            )
        ToolResultCommand.model_validate(valid_body, strict=True)
        valid_token = _token(
            run_id=run_id,
            session_id=sid,
            epoch=epoch,
            action="tool_result.submit",
            jti="result-under-command-cap-jti",
        )
        accepted = await client.post(
            f"/runs/{sid}/results",
            content=encoded_valid,
            headers={
                **_auth(valid_token),
                "Content-Type": "application/json",
            },
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["state"] == "runtime_acked"
        assert len(calls) == 2
        assert len(calls[-1][-1]["content"].encode("utf-8")) > max_blob_bytes
        runtime_store = app.state.runtime_store
        completed_session = await runtime_store.get_session(sid)
        checkpoint_bytes = canonical_json_bytes(
            completed_session.checkpoint, max_bytes=MAX_UNACKED_BYTES
        )
        assert MAX_COMMAND_BYTES < len(checkpoint_bytes) <= MAX_UNACKED_BYTES
        stream = await _events(client, run_id, sid, epoch)
        result_event = next(
            event
            for event in stream["events"]
            if event["event_kind"] == "tool_result"
        )
        assert result_event["payload"] == valid_body["payload"]
        artifact = (await runtime_store.list_artifacts(sid))[0]
        assert artifact.meta["broker_result_digest"] == valid_body["result_digest"]
        assert artifact.meta["broker_result_provenance"] == {
            "command_id": valid_body["command_id"],
            "intent_id": valid_body["intent_id"],
            "action_id": valid_body["action_id"],
        }


@pytest.mark.anyio
async def test_result_binding_redaction_and_receipt_survive_restart(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    completer = ScriptedCompleter()
    run_id = "result-restart"
    app = _app(path, completer)
    async with _client(app) as client:
        sid, epoch = await _open_paused_run(client, run_id=run_id)
        intent = next(
            event for event in (await _events(client, run_id, sid, epoch))["events"]
            if event["event_kind"] == "tool_intent"
        )
        payload = {
            "sentinel": "BROKER-RESTART-1",
            "api_key": "sk-1234567890abcdefghijklmnop",
        }
        body = _result_body(
            run_id=run_id,
            sid=sid,
            epoch=epoch,
            turn_id=intent["turn_id"],
            intent_id=intent["intent_id"],
            outcome="succeeded",
            payload=payload,
            command_id="result-restart-command",
            action_id="result-restart-action",
        )
        token = _token(
            run_id=run_id,
            session_id=sid,
            epoch=epoch,
            action="tool_result.submit",
            jti="result-restart-jti",
        )
        first = await client.post(
            f"/runs/{sid}/results", json=body, headers=_auth(token)
        )
        assert first.status_code == 200, first.text
        assert first.json()["state"] == "runtime_acked"

    async with _client(_app(path, completer)) as restarted:
        retry = await restarted.post(
            f"/runs/{sid}/results", json=body, headers=_auth(token)
        )
        assert retry.status_code == 200, retry.text
        assert retry.json() == first.json()
        stream = await _events(restarted, run_id, sid, epoch)

    assert len(completer.calls) == 2
    serialized = str(stream)
    assert payload["sentinel"] in serialized
    assert payload["api_key"] not in serialized
    assert "[REDACTED]" in serialized


@pytest.mark.anyio
async def test_result_effect_recovers_when_receipt_commit_fails(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    completer = ScriptedCompleter()
    run_id = "result-receipt-recovery"
    app = _app(path, completer)
    async with _client(app) as client:
        sid, epoch = await _open_paused_run(client, run_id=run_id)
        intent = next(
            event for event in (await _events(client, run_id, sid, epoch))["events"]
            if event["event_kind"] == "tool_intent"
        )
        body = _result_body(
            run_id=run_id,
            sid=sid,
            epoch=epoch,
            turn_id=intent["turn_id"],
            intent_id=intent["intent_id"],
            outcome="succeeded",
            payload={"sentinel": "RECEIPT-RECOVERY"},
            command_id="receipt-recovery-result",
            action_id="receipt-recovery-action",
        )
        token = _token(
            run_id=run_id,
            session_id=sid,
            epoch=epoch,
            action="tool_result.submit",
            jti="receipt-recovery-jti",
        )
        original_complete = app.state.runtime_store.complete_command
        failed_once = False

        async def fail_result_receipt_once(binding, *, response):
            nonlocal failed_once
            if binding.action == "tool_result.submit" and not failed_once:
                failed_once = True
                raise RuntimeError("injected receipt commit failure")
            return await original_complete(binding, response=response)

        app.state.runtime_store.complete_command = fail_result_receipt_once
        with pytest.raises(RuntimeError, match="injected receipt"):
            await client.post(
                f"/runs/{sid}/results", json=body, headers=_auth(token)
            )

    async with _client(_app(path, completer)) as restarted:
        recovered = await restarted.post(
            f"/runs/{sid}/results", json=body, headers=_auth(token)
        )
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["state"] == "runtime_acked"
        stream = await _events(restarted, run_id, sid, epoch)

    assert len(completer.calls) == 2
    assert sum(
        event["event_kind"] == "tool_result" for event in stream["events"]
    ) == 1
    assert sum(event["event_kind"] == "final" for event in stream["events"]) == 1


@pytest.mark.anyio
async def test_result_receipt_retry_does_not_consume_the_next_intent(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    calls: list[list[dict]] = []

    async def completer(messages):
        calls.append(deepcopy(messages))
        if len(calls) == 1:
            return (
                '{"plan":"first","tool":"web.search",'
                '"query":"first query","conclusion":""}',
                11,
            )
        if len(calls) == 2:
            return (
                '{"plan":"second","tool":"web.search",'
                '"query":"second query","conclusion":""}',
                13,
            )
        raise AssertionError("result receipt retry repeated the model call")

    run_id = "next-intent-receipt-recovery"
    app = _app(path, completer)
    async with _client(app) as client:
        sid, epoch = await _open_paused_run(client, run_id=run_id)
        first_intent = next(
            event
            for event in (await _events(client, run_id, sid, epoch))["events"]
            if event["event_kind"] == "tool_intent"
        )
        body = _result_body(
            run_id=run_id,
            sid=sid,
            epoch=epoch,
            turn_id=first_intent["turn_id"],
            intent_id=first_intent["intent_id"],
            outcome="succeeded",
            payload={"sentinel": "FIRST-RESULT"},
            command_id="first-result-command",
            action_id="first-result-action",
        )
        token = _token(
            run_id=run_id,
            session_id=sid,
            epoch=epoch,
            action="tool_result.submit",
            jti="first-result-jti",
        )
        original_complete = app.state.runtime_store.complete_command
        failed_once = False

        async def fail_result_receipt_once(binding, *, response):
            nonlocal failed_once
            if binding.action == "tool_result.submit" and not failed_once:
                failed_once = True
                raise RuntimeError("injected next-intent receipt failure")
            return await original_complete(binding, response=response)

        app.state.runtime_store.complete_command = fail_result_receipt_once
        with pytest.raises(RuntimeError, match="next-intent receipt"):
            await client.post(
                f"/runs/{sid}/results", json=body, headers=_auth(token)
            )
        paused = await app.state.runtime_store.get_session(sid)
        assert paused.state == "intent_pending"
        assert paused.checkpoint["last_result_command_id"] == body["command_id"]
        assert paused.checkpoint["active_intent_id"] != body["intent_id"]

    restarted_app = _app(path, completer)
    async with _client(restarted_app) as restarted:
        recovered = await restarted.post(
            f"/runs/{sid}/results", json=body, headers=_auth(token)
        )
        exact_retry = await restarted.post(
            f"/runs/{sid}/results", json=body, headers=_auth(token)
        )
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["runtime_state"] == "intent_pending"
        assert exact_retry.json() == recovered.json()
        stream = await _events(restarted, run_id, sid, epoch)

    intents = [
        event for event in stream["events"] if event["event_kind"] == "tool_intent"
    ]
    results = [
        event for event in stream["events"] if event["event_kind"] == "tool_result"
    ]
    assert len(calls) == 2
    assert len(intents) == 2
    assert len(results) == 1
    assert results[0]["intent_id"] == first_intent["intent_id"]
    runtime_store = restarted_app.state.runtime_store
    applied = await runtime_store.get_intent(sid, first_intent["intent_id"])
    pending = await runtime_store.get_intent(sid, intents[-1]["intent_id"])
    assert applied.state == "applied"
    assert pending.state == "pending"
    final_session = await runtime_store.get_session(sid)
    assert final_session.checkpoint["active_intent_id"] == pending.intent_id


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", ["denied", "failed"])
async def test_non_success_result_is_terminal_without_success_artifact(
    tmp_path, outcome
):
    calls: list[list[dict]] = []

    async def completer(messages):
        calls.append(deepcopy(messages))
        if len(calls) == 1:
            return (
                '{"plan":"query","tool":"web.search",'
                '"query":"deny-fail sentinel","conclusion":""}',
                11,
            )
        return (
            '{"plan":"explain terminal result","tool":null,"query":"",'
            f'"conclusion":"broker outcome was {outcome}"}}',
            13,
        )

    path = tmp_path / f"runtime-{outcome}.sqlite3"
    app = _app(path, completer)
    run_id = f"terminal-{outcome}-result"
    async with _client(app) as client:
        sid, epoch = await _open_paused_run(client, run_id=run_id)
        intent = next(
            event
            for event in (await _events(client, run_id, sid, epoch))["events"]
            if event["event_kind"] == "tool_intent"
        )
        payload = {
            "sentinel": f"BROKER-{outcome.upper()}-SENTINEL",
            "reason": f"broker {outcome}",
        }
        body = _result_body(
            run_id=run_id,
            sid=sid,
            epoch=epoch,
            turn_id=intent["turn_id"],
            intent_id=intent["intent_id"],
            outcome=outcome,
            payload=payload,
            command_id=f"terminal-{outcome}-command",
            action_id=f"terminal-{outcome}-action",
        )
        token = _token(
            run_id=run_id,
            session_id=sid,
            epoch=epoch,
            action="tool_result.submit",
            jti=f"terminal-{outcome}-jti",
        )
        first = await client.post(
            f"/runs/{sid}/results", json=body, headers=_auth(token)
        )
        retry = await client.post(
            f"/runs/{sid}/results", json=body, headers=_auth(token)
        )
        assert first.status_code == 200, first.text
        assert retry.json() == first.json()
        assert first.json()["runtime_state"] == "failed"

        stream = await _events(client, run_id, sid, epoch)
        result_event = next(
            event
            for event in stream["events"]
            if event["event_kind"] == "tool_result"
        )
        assert result_event["turn_id"] == intent["turn_id"]
        assert result_event["intent_id"] == intent["intent_id"]
        assert result_event["outcome"] == outcome
        assert result_event["payload"] == payload
        assert _digest(result_event["payload"]) == body["result_digest"]
        assert any(event["event_kind"] == "final" for event in stream["events"])
        assert all(
            event["event_kind"] != "observation" for event in stream["events"]
        )

        artifact_token = _token(
            run_id=run_id,
            session_id=sid,
            epoch=epoch,
            action="artifacts.read",
            jti=f"terminal-{outcome}-artifact-jti",
        )
        artifacts = await client.get(
            f"/runs/{sid}/artifacts", headers=_auth(artifact_token)
        )
        assert artifacts.status_code == 409

    assert len(calls) == 2
    resume_message = calls[-1][-1]["content"]
    assert f"outcome={outcome}" in resume_message
    assert payload["sentinel"] in resume_message
    assert "outcome=succeeded" not in resume_message
    runtime_store = app.state.runtime_store
    session = await runtime_store.get_session(sid)
    stored_intent = await runtime_store.get_intent(sid, intent["intent_id"])
    assert session.state == "failed"
    assert session.checkpoint["phase"] == "failed"
    assert stored_intent.state == "applied"
    assert stored_intent.result_outcome == outcome
    assert stored_intent.result_digest == body["result_digest"]
    assert stored_intent.result_payload == payload
    assert await runtime_store.list_artifacts(sid) == []


@pytest.mark.anyio
async def test_result_rejects_wrong_turn_and_second_action_binding(tmp_path):
    completer = ScriptedCompleter()
    app = _app(tmp_path / "runtime.sqlite3", completer)
    run_id = "result-binding"
    async with _client(app) as client:
        sid, epoch = await _open_paused_run(client, run_id=run_id)
        intent = next(
            event for event in (await _events(client, run_id, sid, epoch))["events"]
            if event["event_kind"] == "tool_intent"
        )
        body = _result_body(
            run_id=run_id,
            sid=sid,
            epoch=epoch,
            turn_id=intent["turn_id"],
            intent_id=intent["intent_id"],
            outcome="succeeded",
            payload={"sentinel": "BOUND"},
        )

        wrong_turn = {**body, "command_id": "wrong-turn", "turn_id": "other-turn"}
        wrong_token = _token(
            run_id=run_id,
            session_id=sid,
            epoch=epoch,
            action="tool_result.submit",
            jti="wrong-turn-jti",
        )
        refused = await client.post(
            f"/runs/{sid}/results", json=wrong_turn, headers=_auth(wrong_token)
        )
        assert refused.status_code == 409
        assert len(completer.calls) == 1

        token = _token(
            run_id=run_id,
            session_id=sid,
            epoch=epoch,
            action="tool_result.submit",
            jti="bound-result-jti",
        )
        accepted = await client.post(
            f"/runs/{sid}/results", json=body, headers=_auth(token)
        )
        assert accepted.status_code == 200, accepted.text

        changed = deepcopy(body)
        changed["command_id"] = "second-result-command"
        changed["action_id"] = "second-result-action"
        second_token = _token(
            run_id=run_id,
            session_id=sid,
            epoch=epoch,
            action="tool_result.submit",
            jti="second-result-jti",
        )
        duplicate = await client.post(
            f"/runs/{sid}/results", json=changed, headers=_auth(second_token)
        )
        assert duplicate.status_code == 409
        assert len(completer.calls) == 2
