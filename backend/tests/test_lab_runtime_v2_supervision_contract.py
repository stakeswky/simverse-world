from __future__ import annotations

import time
import traceback

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.lab.protocol import (
    RuntimeV2Handshake,
    RuntimeV2SupervisionHandshake,
    ToolResultCommand,
    content_digest,
    runtime_v2_supervision_handshake,
)
from app.lab.runtime_ref.service_auth import (
    ServiceAuthorizationError,
    ServiceBinding,
    ServiceTokenIssuer,
    ServiceTokenValidator,
)
from app.lab.sandbox.base import (
    HttpAgentAdapter,
    RunSpec,
    RuntimeV2NonRetryableError,
    RuntimeV2RetryableError,
)


CURRENT_KEY = "runtime-current-test-secret-at-least-32-bytes"
NEXT_KEY = "runtime-next-test-secret-at-least-32-bytes"
RUNTIME_BODY_SECRET = "RUNTIME-BODY-SECRET-MUST-NOT-LEAK"


def _adapter() -> HttpAgentAdapter:
    adapter = HttpAgentAdapter(
        base_url="http://runtime.test",
        service_token_issuer=ServiceTokenIssuer({
            "issuer": "simverse-gateway",
            "audience": "lab-runtime",
            "current_kid": "runtime-current",
            "current_key": CURRENT_KEY,
            "token_ttl_seconds": 300,
        }),
    )
    adapter.prepare_protocol_v2(
        spec=RunSpec(
            run_id="run-1",
            task_id="task-1",
            researcher_slug="sage",
            brief="strict runtime contract",
            scopes=["web_search"],
            budget_usd=1.0,
        ),
        epoch=7,
        client_run_id="client-run-1",
    )
    return adapter


class _ArtifactClient:
    def __init__(self, payload: dict):
        self.payload = payload

    async def get(self, url, **kwargs):
        return httpx.Response(
            200,
            json=self.payload,
            request=httpx.Request("GET", url),
        )


class _ResponseClient:
    def __init__(self, payload: dict):
        self.payload = payload

    async def get(self, url, **kwargs):
        return httpx.Response(
            200,
            json=self.payload,
            request=httpx.Request("GET", url),
        )

    async def post(self, url, **kwargs):
        return httpx.Response(
            200,
            json=self.payload,
            request=httpx.Request("POST", url),
        )


def _artifact(**overrides) -> dict:
    value = {
        "schema_version": 1,
        "provider_artifact_id": "artifact-1",
        "kind": "text",
        "title": "verified report",
        "content_type": "text/markdown",
        "original_filename": None,
        "declared_byte_size": None,
        "expected_sha256": None,
        "required": True,
        "producer_action_id": None,
        "upload_state": "pending",
        "upload_receipt": None,
    }
    value.update(overrides)
    return value


def _manifest(**overrides) -> RuntimeV2Handshake:
    value = {
        "schema_version": 2,
        "protocol_version": 2,
        "provider_name": "runtime-ref",
        "durability_class": "session_affine",
        "reattach_capability": "client_run_id",
        "effect_mode": "broker_only",
        "capabilities": [
            "backpressure",
            "broker_mediation",
            "cursor_replay",
            "events_ack",
            "idempotent_create",
            "reattach",
            "result_receipts",
            "scoped_auth",
        ],
    }
    value.update(overrides)
    return RuntimeV2Handshake.model_validate(value)


def test_supervision_handshake_binds_wire_schemas_limits_and_capabilities():
    proof = runtime_v2_supervision_handshake(_manifest())
    parsed = RuntimeV2SupervisionHandshake.model_validate(
        proof.model_dump(mode="json")
    )
    assert parsed.protocol_schema_hash == proof.protocol_schema_hash

    for mutation in (
        {"protocol_schema_hash": "0" * 64},
        {
            "schema_hashes": {
                **proof.schema_hashes.model_dump(),
                "runtime_event": "0" * 64,
            }
        },
        {
            "limits": {
                **proof.limits.model_dump(),
                "max_unacked_events": proof.limits.max_unacked_events + 1,
            }
        },
    ):
        body = proof.model_dump(mode="json")
        body.update(mutation)
        with pytest.raises(ValidationError):
            RuntimeV2SupervisionHandshake.model_validate(body)

    missing_ack = _manifest(capabilities=[
        capability
        for capability in _manifest().capabilities
        if capability != "events_ack"
    ])
    with pytest.raises(ValidationError, match="events_ack"):
        runtime_v2_supervision_handshake(missing_ack)


def test_gateway_service_token_issuer_reuses_jti_only_for_exact_command_retry():
    issuer = ServiceTokenIssuer({
        "issuer": "simverse-gateway",
        "audience": "lab-runtime",
        "current_kid": "runtime-current",
        "current_key": CURRENT_KEY,
        "token_ttl_seconds": 300,
    })
    now = int(time.time())
    binding = {
        "run_id": "run-1",
        "session_id": "session-1",
        "epoch": 7,
    }
    first = issuer.issue(
        **binding,
        action="tool_result.submit",
        command_id="result-1",
        issued_at=now,
    )
    retry = issuer.issue(
        **binding,
        action="tool_result.submit",
        command_id="result-1",
        issued_at=now,
    )
    different = issuer.issue(
        **binding,
        action="events.ack",
        command_id="result-1",
        issued_at=now,
    )
    assert first == retry
    assert different != first

    validator = ServiceTokenValidator({
        "issuer": "simverse-gateway",
        "audience": "lab-runtime",
        "keys": {
            "runtime-current": CURRENT_KEY,
            "runtime-next": NEXT_KEY,
        },
    })
    claims = validator.validate(
        first,
        required_action="tool_result.submit",
        expected_binding=ServiceBinding(**binding),
    )
    assert claims.jti.startswith("cmd-")

    rotated = ServiceTokenIssuer({
        "issuer": "simverse-gateway",
        "audience": "lab-runtime",
        "current_kid": "runtime-next",
        "current_key": NEXT_KEY,
        "token_ttl_seconds": 300,
    }).issue(
        **binding,
        action="tool_result.submit",
        command_id="result-1",
        issued_at=now,
    )
    rotated_claims = validator.validate(
        rotated,
        required_action="tool_result.submit",
        expected_binding=ServiceBinding(**binding),
    )
    assert rotated != first
    assert rotated_claims.jti == claims.jti

    with pytest.raises(ServiceAuthorizationError):
        validator.validate(first, required_action="events.ack")


def test_runtime_v2_gateway_auth_defaults_never_reuse_static_secrets():
    fields = Settings.model_fields
    assert fields["lab_runtime_auth_issuer"].default == ""
    assert fields["lab_runtime_auth_current_key"].default == ""
    assert fields["lab_runtime_auth_next_key"].default == ""
    assert fields["lab_runtime_auth_audience"].default == "lab-runtime"
    assert fields["lab_simverse_ref_api_key"].default == ""


@pytest.mark.anyio
async def test_runtime_v2_artifact_decoder_accepts_exact_nullable_wire_fields(
    monkeypatch,
):
    import app.http

    payload = {
        "artifacts": [
            _artifact(),
            _artifact(
                provider_artifact_id="artifact-2",
                kind="link",
                title="primary source",
                content_type="text/html",
                required=False,
            ),
        ]
    }
    monkeypatch.setattr(app.http, "get_client", lambda: _ArtifactClient(payload))

    artifacts = await _adapter().collect_artifacts_v2(
        provider_session_id="provider-session-1"
    )

    assert [(item.kind, item.title) for item in artifacts] == [
        ("text", "verified report"),
        ("link", "primary source"),
    ]
    assert artifacts[0].original_filename is None
    assert artifacts[0].declared_byte_size is None
    assert artifacts[0].expected_sha256 is None
    assert artifacts[0].producer_action_id is None
    assert artifacts[1].required is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"artifacts": "not-a-list"},
        {"artifacts": []},
        {"artifacts": [_artifact()], "unexpected": True},
        {"artifacts": ["not-an-object"]},
        {"artifacts": [{key: value for key, value in _artifact().items() if key != "title"}]},
        {"artifacts": [{**_artifact(), "unexpected": True}]},
        {"artifacts": [_artifact(provider_artifact_id=None)]},
        {"artifacts": [_artifact(kind=7)]},
        {"artifacts": [_artifact(kind="executable")]},
        {"artifacts": [_artifact(title=None)]},
        {"artifacts": [_artifact(title="")]},
        {"artifacts": [_artifact(content_type=7)]},
        {"artifacts": [_artifact(original_filename=[])]},
        {"artifacts": [_artifact(declared_byte_size="12")]},
        {"artifacts": [_artifact(expected_sha256="not-a-digest")]},
        {"artifacts": [_artifact(upload_receipt={"unexpected": True})]},
    ],
)
async def test_runtime_v2_artifact_decoder_rejects_malformed_items(
    monkeypatch, payload
):
    import app.http

    monkeypatch.setattr(app.http, "get_client", lambda: _ArtifactClient(payload))

    with pytest.raises(RuntimeV2NonRetryableError, match="artifact") as raised:
        await _adapter().collect_artifacts_v2(
            provider_session_id="provider-session-1"
        )

    assert raised.value.retryable is False
    assert raised.value.status_code is None


@pytest.mark.parametrize(
    "case",
    ["oversized", "malformed_json", "non_object", "too_deep"],
)
def test_runtime_v2_response_decoder_contract_failures_are_nonretryable(case):
    request = httpx.Request("GET", "http://runtime.test/handshake")
    max_bytes = 1024
    if case == "oversized":
        response = httpx.Response(
            200,
            content=(f'{{"value":"{RUNTIME_BODY_SECRET}"}}').encode(),
            request=request,
        )
        max_bytes = 1
    elif case == "malformed_json":
        response = httpx.Response(
            200,
            content=(f'{{"value":"{RUNTIME_BODY_SECRET}').encode(),
            request=request,
        )
    elif case == "non_object":
        response = httpx.Response(200, json=[], request=request)
    else:
        value: object = "leaf"
        for _ in range(40):
            value = [value]
        response = httpx.Response(200, json={"value": value}, request=request)

    with pytest.raises(RuntimeV2NonRetryableError) as raised:
        HttpAgentAdapter._response_object(
            response,
            max_bytes=max_bytes,
            operation="handshake",
        )

    assert raised.value.retryable is False
    assert raised.value.status_code is None
    rendered = "".join(traceback.format_exception(raised.value))
    assert RUNTIME_BODY_SECRET not in rendered


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {
            "events": [{"payload": {"secret": RUNTIME_BODY_SECRET}}],
            "done": False,
            "has_more": False,
            "latest_cursor": 1,
            "acked_through": 0,
        },
        {
            "events": [],
            "done": False,
            "has_more": False,
            "latest_cursor": 0,
            "acked_through": 1,
        },
    ],
)
async def test_runtime_v2_invalid_event_schema_or_watermark_is_nonretryable(
    monkeypatch, payload
):
    import app.http

    monkeypatch.setattr(app.http, "get_client", lambda: _ResponseClient(payload))

    with pytest.raises(RuntimeV2NonRetryableError) as raised:
        await _adapter().read_runtime_events(
            provider_session_id="provider-session-1",
            after=0,
            limit=1,
            max_bytes=1024,
        )

    assert raised.value.retryable is False
    assert raised.value.operation == "events.read"
    rendered = "".join(traceback.format_exception(raised.value))
    assert RUNTIME_BODY_SECRET not in rendered


@pytest.mark.anyio
async def test_runtime_v2_invalid_result_receipt_is_nonretryable(monkeypatch):
    import app.http

    payload = {"sentinel": "broker-result"}
    command = ToolResultCommand(
        command_id="result-command-1",
        run_id="run-1",
        session_id="provider-session-1",
        turn_id="turn-1",
        intent_id="intent-1",
        action_id="action-1",
        outcome="succeeded",
        payload=payload,
        result_digest=content_digest(payload),
        epoch=7,
    )
    bad_receipt = {
        "receipt_id": "receipt-1",
        "request_digest": "0" * 64,
        "session_id": command.session_id,
        "turn_id": command.turn_id,
        "intent_id": command.intent_id,
        "action_id": command.action_id,
        "state": "runtime_acked",
    }
    monkeypatch.setattr(
        app.http,
        "get_client",
        lambda: _ResponseClient(bad_receipt),
    )

    with pytest.raises(RuntimeV2NonRetryableError) as raised:
        await _adapter().send_runtime_result(command)

    assert raised.value.retryable is False
    assert raised.value.operation == "tool_result.submit"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status_code", "error_type", "retryable"),
    [
        (400, RuntimeV2NonRetryableError, False),
        (401, RuntimeV2NonRetryableError, False),
        (403, RuntimeV2NonRetryableError, False),
        (404, RuntimeV2NonRetryableError, False),
        (409, RuntimeV2NonRetryableError, False),
        (422, RuntimeV2NonRetryableError, False),
        (408, RuntimeV2RetryableError, True),
        (429, RuntimeV2RetryableError, True),
        (500, RuntimeV2RetryableError, True),
        (503, RuntimeV2RetryableError, True),
    ],
)
async def test_runtime_v2_http_status_classification_is_explicit(
    status_code, error_type, retryable
):
    request = httpx.Request("GET", "http://runtime.test/handshake")

    async def send():
        return httpx.Response(status_code, request=request)

    with pytest.raises(error_type) as raised:
        await _adapter()._request_v2(send, operation="handshake")

    assert raised.value.retryable is retryable
    assert raised.value.status_code == status_code


@pytest.mark.anyio
async def test_runtime_v2_transport_failure_is_retryable():
    request = httpx.Request("GET", "http://runtime.test/handshake")

    async def send():
        raise httpx.ConnectError("runtime unavailable", request=request)

    with pytest.raises(RuntimeV2RetryableError) as raised:
        await _adapter()._request_v2(send, operation="handshake")

    assert raised.value.retryable is True
    assert raised.value.status_code is None
