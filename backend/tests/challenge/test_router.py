from __future__ import annotations

import inspect
import re

import pytest
from pydantic import ValidationError
from sqlalchemy import event

from app.challenge.repository import SESSION_PREFIX, ChallengeRepository
from app.config import Settings, settings
from app.main import app
from app.redis_client import get_redis

pytestmark = pytest.mark.anyio

PUBLIC_ORIGIN = "https://simverse.world"


async def _http_approved(client):
    created = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    assert created.status_code == 200
    headers = {
        "Origin": PUBLIC_ORIGIN,
        "X-CSRF-Token": created.json()["csrf_token"],
    }
    investigated = await client.post(
        "/challenge/investigate", headers=headers, json={"budget_cap_sc": 300}
    )
    assert investigated.status_code == 200
    previewed = await client.post(
        "/challenge/preview",
        headers=headers,
        json={"crisis_id": "harbor-wage-crisis", "budget_cap_sc": 300},
    )
    assert previewed.status_code == 200
    preview = previewed.json()["preview"]
    approved = await client.post(
        "/challenge/approve",
        headers=headers,
        json={
            "preview_id": preview["preview_id"],
            "expected_world_version": preview["based_on_world_version"],
            "diff_hash": preview["diff_hash"],
        },
    )
    assert approved.status_code == 200
    approval_cookie = next(
        value
        for value in approved.headers.get_list("set-cookie")
        if value.startswith("sv_challenge_approval=")
    )
    approval_id = approval_cookie.split(";", 1)[0].split("=", 1)[1]
    body = {
        "preview_id": preview["preview_id"],
        "expected_world_version": preview["based_on_world_version"],
        "diff_hash": preview["diff_hash"],
    }
    return headers, body, approval_id


@pytest.fixture
def public_challenge_origin(monkeypatch):
    monkeypatch.setattr(settings, "challenge_allowed_origins", [PUBLIC_ORIGIN])
    cors = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )
    original_origins = cors.kwargs["allow_origins"]
    cors.kwargs["allow_origins"] = [*original_origins, PUBLIC_ORIGIN]
    app.middleware_stack = None
    yield
    cors.kwargs["allow_origins"] = original_origins
    app.middleware_stack = None


def test_challenge_config_defaults_to_a_copy_of_cors_origins() -> None:
    configured = Settings(
        _env_file=None,
        debug=True,
        cors_origins=["https://one.example", "https://two.example"],
    )

    assert configured.challenge_allowed_origins == configured.cors_origins
    assert configured.challenge_allowed_origins is not configured.cors_origins
    assert configured.challenge_cookie_secure is None


def test_explicit_challenge_origins_must_be_a_cors_subset() -> None:
    configured = Settings(
        _env_file=None,
        debug=True,
        cors_origins=[PUBLIC_ORIGIN, "https://admin.simverse.world"],
        challenge_allowed_origins=[PUBLIC_ORIGIN],
    )
    assert configured.challenge_allowed_origins == [PUBLIC_ORIGIN]

    with pytest.raises(ValidationError, match="subset of CORS_ORIGINS"):
        Settings(
            _env_file=None,
            debug=True,
            cors_origins=[PUBLIC_ORIGIN],
            challenge_allowed_origins=["https://attacker.invalid"],
        )


async def test_public_cors_preflight_and_credentialed_session_post(
    client, public_challenge_origin
) -> None:
    preflight = await client.options(
        "/challenge/session",
        headers={
            "Origin": PUBLIC_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == PUBLIC_ORIGIN
    assert preflight.headers["access-control-allow-credentials"] == "true"

    created = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    assert created.status_code == 200
    assert created.headers["access-control-allow-origin"] == PUBLIC_ORIGIN
    assert created.json()["state"] == "INITIAL"


async def test_session_post_requires_exact_origin_and_rejects_any_body(
    client, public_challenge_origin
) -> None:
    missing = await client.post("/challenge/session")
    wrong = await client.post(
        "/challenge/session", headers={"Origin": "https://attacker.invalid"}
    )
    extra = await client.post(
        "/challenge/session",
        headers={"Origin": PUBLIC_ORIGIN},
        json={"unexpected": True},
    )

    for response in (missing, wrong, extra):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_INPUT"
        assert set(response.json()["error"]) == {
            "code", "message", "retryable", "current_state", "next_action"
        }


async def test_session_cookie_attributes_get_resume_and_no_authorization(
    client, public_challenge_origin
) -> None:
    created = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    assert created.status_code == 200
    cookie = created.headers["set-cookie"].lower()
    assert "sv_challenge_session=" in cookie
    assert "httponly" in cookie
    assert "path=/challenge" in cookie
    assert "samesite=lax" in cookie
    assert "secure" not in cookie
    generation = created.json()["session_generation"]

    resumed = await client.get("/challenge/session")
    assert resumed.status_code == 200
    assert resumed.json()["session_generation"] == generation
    assert "set-cookie" not in resumed.headers
    assert "authorization" not in created.request.headers


async def test_production_session_cookie_is_secure(
    client, public_challenge_origin, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "challenge_cookie_secure", None)
    response = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()


async def test_get_requires_session_cookie(client) -> None:
    response = await client.get("/challenge/session")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHALLENGE_SESSION_NOT_READY"


async def test_reset_requires_origin_cookie_and_constant_time_csrf(
    client, public_challenge_origin
) -> None:
    created = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    csrf = created.json()["csrf_token"]
    generation = created.json()["session_generation"]
    body = {"expected_generation": generation}

    missing_origin = await client.post(
        "/challenge/reset", headers={"X-CSRF-Token": csrf}, json=body
    )
    missing_csrf = await client.post(
        "/challenge/reset", headers={"Origin": PUBLIC_ORIGIN}, json=body
    )
    wrong_csrf = await client.post(
        "/challenge/reset",
        headers={"Origin": PUBLIC_ORIGIN, "X-CSRF-Token": "wrong"},
        json=body,
    )
    for response in (missing_origin, missing_csrf, wrong_csrf):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_INPUT"


async def test_investigate_requires_origin_cookie_and_constant_time_csrf(
    client, public_challenge_origin
) -> None:
    created = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    csrf = created.json()["csrf_token"]
    body = {"budget_cap_sc": 300}

    missing_origin = await client.post(
        "/challenge/investigate", headers={"X-CSRF-Token": csrf}, json=body
    )
    missing_csrf = await client.post(
        "/challenge/investigate", headers={"Origin": PUBLIC_ORIGIN}, json=body
    )
    wrong_csrf = await client.post(
        "/challenge/investigate",
        headers={"Origin": PUBLIC_ORIGIN, "X-CSRF-Token": "wrong"},
        json=body,
    )
    for response in (missing_origin, missing_csrf, wrong_csrf):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_INPUT"

    unchanged = await client.get("/challenge/session")
    assert unchanged.json()["state"] == "INITIAL"
    assert unchanged.json()["evidence"] is None


async def test_investigate_api_exposes_evidence_and_rejects_extra_fields(
    client, public_challenge_origin
) -> None:
    created = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    headers = {
        "Origin": PUBLIC_ORIGIN,
        "X-CSRF-Token": created.json()["csrf_token"],
    }
    before_hash = created.json()["world_hash"]

    investigated = await client.post(
        "/challenge/investigate", headers=headers, json={"budget_cap_sc": 300}
    )
    assert investigated.status_code == 200
    assert investigated.json()["state"] == "EVIDENCE_READY"
    assert investigated.json()["evidence"]["based_on_world_version"] == 7
    assert investigated.json()["world_hash"] == before_hash
    assert investigated.json()["world_version"] == 7
    assert investigated.json()["budget_sc"] == 300

    extra = await client.post(
        "/challenge/investigate",
        headers=headers,
        json={"budget_cap_sc": 300, "unexpected": True},
    )
    assert extra.status_code == 422
    assert extra.json()["error"]["code"] == "INVALID_INPUT"


async def test_preview_api_exposes_immutable_diff_and_rejects_wrong_schema(
    client, public_challenge_origin
) -> None:
    created = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    headers = {
        "Origin": PUBLIC_ORIGIN,
        "X-CSRF-Token": created.json()["csrf_token"],
    }
    before_hash = created.json()["world_hash"]
    investigated = await client.post(
        "/challenge/investigate", headers=headers, json={"budget_cap_sc": 300}
    )
    assert investigated.status_code == 200

    for invalid_body in (
        {"crisis_id": "wrong-crisis", "budget_cap_sc": 300},
        {"crisis_id": "harbor-wage-crisis", "budget_cap_sc": 299},
        {
            "crisis_id": "harbor-wage-crisis",
            "budget_cap_sc": 300,
            "unexpected": True,
        },
    ):
        rejected = await client.post(
            "/challenge/preview", headers=headers, json=invalid_body
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "INVALID_INPUT"

    client.cookies.set(
        "sv_challenge_approval", "untrusted-client-cookie", path="/challenge/commit"
    )
    previewed = await client.post(
        "/challenge/preview",
        headers=headers,
        json={"crisis_id": "harbor-wage-crisis", "budget_cap_sc": 300},
    )

    assert previewed.status_code == 200
    payload = previewed.json()
    assert payload["state"] == "PREVIEW_READY"
    assert payload["preview"]["based_on_world_version"] == 7
    assert payload["preview"]["total_cost_sc"] == 240
    assert payload["preview"]["remaining_budget_sc"] == 60
    assert payload["world_hash"] == before_hash
    assert payload["world_version"] == 7
    assert payload["budget_sc"] == 300
    set_cookie = previewed.headers.get_list("set-cookie")
    assert any(
        "sv_challenge_approval=" in value and "Max-Age=0" in value
        for value in set_cookie
    )


async def test_preview_requires_origin_cookie_and_constant_time_csrf(
    client, public_challenge_origin
) -> None:
    created = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    csrf = created.json()["csrf_token"]
    await client.post(
        "/challenge/investigate",
        headers={"Origin": PUBLIC_ORIGIN, "X-CSRF-Token": csrf},
        json={"budget_cap_sc": 300},
    )
    body = {"crisis_id": "harbor-wage-crisis", "budget_cap_sc": 300}

    missing_origin = await client.post(
        "/challenge/preview", headers={"X-CSRF-Token": csrf}, json=body
    )
    missing_csrf = await client.post(
        "/challenge/preview", headers={"Origin": PUBLIC_ORIGIN}, json=body
    )
    wrong_csrf = await client.post(
        "/challenge/preview",
        headers={"Origin": PUBLIC_ORIGIN, "X-CSRF-Token": "wrong"},
        json=body,
    )
    for response in (missing_origin, missing_csrf, wrong_csrf):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_INPUT"

    unchanged = await client.get("/challenge/session")
    assert unchanged.json()["state"] == "EVIDENCE_READY"
    assert unchanged.json()["preview"] is None


async def test_approve_cookie_is_secret_scoped_and_revoke_uses_server_pointer(
    client, public_challenge_origin
) -> None:
    created = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    headers = {
        "Origin": PUBLIC_ORIGIN,
        "X-CSRF-Token": created.json()["csrf_token"],
    }
    await client.post(
        "/challenge/investigate", headers=headers, json={"budget_cap_sc": 300}
    )
    previewed = await client.post(
        "/challenge/preview",
        headers=headers,
        json={"crisis_id": "harbor-wage-crisis", "budget_cap_sc": 300},
    )
    preview = previewed.json()["preview"]

    approved = await client.post(
        "/challenge/approve",
        headers=headers,
        json={
            "preview_id": preview["preview_id"],
            "expected_world_version": preview["based_on_world_version"],
            "diff_hash": preview["diff_hash"],
        },
    )

    assert approved.status_code == 200
    assert approved.json()["state"] == "APPROVED_ONCE"
    assert approved.json()["tool_surface"] == ["simverse_commit_approved"]
    assert re.fullmatch(
        r"appr-[0-9A-F]{4}", approved.json()["approval_fingerprint"]
    )
    cookie = next(
        value for value in approved.headers.get_list("set-cookie")
        if value.startswith("sv_challenge_approval=")
    )
    secret = cookie.split(";", 1)[0].split("=", 1)[1]
    lower_cookie = cookie.lower()
    assert len(secret) >= 43
    assert secret not in approved.text
    assert "httponly" in lower_cookie
    assert "max-age=90" in lower_cookie
    assert "path=/challenge/commit" in lower_cookie
    assert "samesite=strict" in lower_cookie
    assert "secure" not in lower_cookie

    revoked = await client.post("/challenge/revoke", headers=headers)

    assert revoked.status_code == 200
    assert revoked.json()["state"] == "PREVIEW_READY"
    assert revoked.json()["approval_fingerprint"] is None
    deleted = revoked.headers.get_list("set-cookie")
    assert any(
        "sv_challenge_approval=" in value and "Max-Age=0" in value
        for value in deleted
    )


async def test_approve_and_revoke_require_origin_cookie_and_csrf(
    client, public_challenge_origin
) -> None:
    created = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    csrf = created.json()["csrf_token"]
    headers = {"Origin": PUBLIC_ORIGIN, "X-CSRF-Token": csrf}
    await client.post(
        "/challenge/investigate", headers=headers, json={"budget_cap_sc": 300}
    )
    previewed = await client.post(
        "/challenge/preview",
        headers=headers,
        json={"crisis_id": "harbor-wage-crisis", "budget_cap_sc": 300},
    )
    preview = previewed.json()["preview"]
    body = {
        "preview_id": preview["preview_id"],
        "expected_world_version": 7,
        "diff_hash": preview["diff_hash"],
    }

    for path, request_body in (("/challenge/approve", body), ("/challenge/revoke", None)):
        missing_origin = await client.post(
            path,
            headers={"X-CSRF-Token": csrf},
            json=request_body,
        )
        missing_csrf = await client.post(
            path,
            headers={"Origin": PUBLIC_ORIGIN},
            json=request_body,
        )
        wrong_csrf = await client.post(
            path,
            headers={"Origin": PUBLIC_ORIGIN, "X-CSRF-Token": "wrong"},
            json=request_body,
        )
        for response in (missing_origin, missing_csrf, wrong_csrf):
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "INVALID_INPUT"

    unchanged = await client.get("/challenge/session")
    assert unchanged.json()["state"] == "PREVIEW_READY"


async def test_commit_uses_path_scoped_cookie_and_returns_atomic_receipt(
    client, public_challenge_origin
) -> None:
    headers, body, approval_id = await _http_approved(client)

    session_read = await client.get("/challenge/session")
    assert "sv_challenge_approval=" not in session_read.request.headers.get(
        "cookie", ""
    )
    committed = await client.post("/challenge/commit", headers=headers, json=body)

    assert committed.status_code == 200
    assert "sv_challenge_approval=" in committed.request.headers.get("cookie", "")
    payload = committed.json()
    assert payload["state"] == "COMMITTED"
    assert payload["world_version"] == 8
    assert payload["budget_sc"] == 60
    assert payload["receipt"]["world_before_version"] == 7
    assert payload["receipt"]["world_after_version"] == 8
    assert payload["receipt"]["approved_diff_hash"] == body["diff_hash"]
    assert approval_id not in committed.text
    assert any(
        "sv_challenge_approval=" in value and "Max-Age=0" in value
        for value in committed.headers.get_list("set-cookie")
    )


async def test_path_scoped_cookie_keeps_preview_and_reset_on_server_pointer(
    client, public_challenge_origin
) -> None:
    headers, _, _ = await _http_approved(client)

    previewed = await client.post(
        "/challenge/preview",
        headers=headers,
        json={"crisis_id": "harbor-wage-crisis", "budget_cap_sc": 300},
    )

    assert previewed.status_code == 200
    assert "sv_challenge_approval=" not in previewed.request.headers.get(
        "cookie", ""
    )
    assert previewed.json()["state"] == "PREVIEW_READY"
    preview = previewed.json()["preview"]
    approved_again = await client.post(
        "/challenge/approve",
        headers=headers,
        json={
            "preview_id": preview["preview_id"],
            "expected_world_version": preview["based_on_world_version"],
            "diff_hash": preview["diff_hash"],
        },
    )
    assert approved_again.status_code == 200

    reset = await client.post(
        "/challenge/reset",
        headers=headers,
        json={"expected_generation": approved_again.json()["session_generation"]},
    )

    assert reset.status_code == 200
    assert "sv_challenge_approval=" not in reset.request.headers.get("cookie", "")
    assert reset.json()["state"] == "INITIAL"


async def test_commit_without_approval_cookie(
    client, public_challenge_origin
) -> None:
    headers, body, _ = await _http_approved(client)
    client.cookies.delete("sv_challenge_approval", path="/challenge/commit")

    rejected = await client.post("/challenge/commit", headers=headers, json=body)

    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "APPROVAL_REQUIRED"
    assert "set-cookie" not in rejected.headers
    unchanged = await client.get("/challenge/session")
    assert unchanged.json()["state"] == "APPROVED_ONCE"
    assert unchanged.json()["world_version"] == 7
    assert unchanged.json()["receipt"] is None


async def test_commit_requires_session_cookie_before_reading_approval(
    client, public_challenge_origin
) -> None:
    headers, body, _ = await _http_approved(client)
    client.cookies.delete("sv_challenge_session", path="/challenge")

    rejected = await client.post("/challenge/commit", headers=headers, json=body)

    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "CHALLENGE_SESSION_NOT_READY"
    assert "set-cookie" not in rejected.headers


async def test_commit_rejects_approval_cookie_bound_to_another_session(
    client, public_challenge_origin
) -> None:
    _, _, first_approval_id = await _http_approved(client)
    client.cookies.delete("sv_challenge_session", path="/challenge")
    second_headers, second_body, _ = await _http_approved(client)
    client.cookies.set(
        "sv_challenge_approval", first_approval_id, path="/challenge/commit"
    )

    rejected = await client.post(
        "/challenge/commit", headers=second_headers, json=second_body
    )

    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "APPROVAL_MISMATCH"
    assert any(
        "sv_challenge_approval=" in value and "Max-Age=0" in value
        for value in rejected.headers.get_list("set-cookie")
    )
    unchanged = await client.get("/challenge/session")
    assert unchanged.json()["state"] == "APPROVED_ONCE"
    assert unchanged.json()["world_version"] == 7
    assert unchanged.json()["receipt"] is None


async def test_commit_rejects_wrong_cookie_and_deletes_it(
    client, public_challenge_origin
) -> None:
    headers, body, approval_id = await _http_approved(client)
    repository = ChallengeRepository()
    approval = await repository.load_approval(approval_id)
    assert approval is not None
    wrong_id = "wrong-approval-cookie"
    await repository.save_approval(
        approval.model_copy(update={"approval_id": wrong_id})
    )
    client.cookies.set(
        "sv_challenge_approval", wrong_id, path="/challenge/commit"
    )

    rejected = await client.post("/challenge/commit", headers=headers, json=body)

    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "APPROVAL_MISMATCH"
    assert any(
        "sv_challenge_approval=" in value and "Max-Age=0" in value
        for value in rejected.headers.get_list("set-cookie")
    )
    unchanged = await client.get("/challenge/session")
    assert unchanged.json()["state"] == "APPROVED_ONCE"
    assert unchanged.json()["world_version"] == 7


async def test_commit_auth_and_schema_failures_never_enter_commit_or_delete_cookie(
    client, public_challenge_origin, monkeypatch
) -> None:
    from app.routers import challenge as challenge_router

    headers, body, _ = await _http_approved(client)
    calls = 0

    async def forbidden_commit(self, session_id, approval_id, request):
        nonlocal calls
        calls += 1
        raise AssertionError("commit service must not run")

    monkeypatch.setattr(challenge_router.ChallengeService, "commit", forbidden_commit)
    requests = (
        ({"X-CSRF-Token": headers["X-CSRF-Token"]}, body),
        ({"Origin": "https://attacker.invalid", "X-CSRF-Token": headers["X-CSRF-Token"]}, body),
        ({"Origin": PUBLIC_ORIGIN}, body),
        ({"Origin": PUBLIC_ORIGIN, "X-CSRF-Token": "wrong"}, body),
        (headers, {**body, "approved": True}),
    )
    for request_headers, request_body in requests:
        rejected = await client.post(
            "/challenge/commit", headers=request_headers, json=request_body
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "INVALID_INPUT"
        assert "set-cookie" not in rejected.headers

    assert calls == 0
    unchanged = await client.get("/challenge/session")
    assert unchanged.json()["state"] == "APPROVED_ONCE"
    assert unchanged.json()["world_version"] == 7
    source = inspect.getsource(challenge_router.require_mutation_context)
    assert "secrets.compare_digest" in source


async def test_commit_rejects_approved_extra_field(
    client, public_challenge_origin, monkeypatch
) -> None:
    from app.routers import challenge as challenge_router

    headers, body, _ = await _http_approved(client)
    calls = 0

    async def forbidden_commit(self, session_id, approval_id, request):
        nonlocal calls
        calls += 1
        raise AssertionError("commit service must not run")

    monkeypatch.setattr(challenge_router.ChallengeService, "commit", forbidden_commit)

    rejected = await client.post(
        "/challenge/commit",
        headers=headers,
        json={**body, "approved": True},
    )

    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "INVALID_INPUT"
    assert calls == 0
    unchanged = await client.get("/challenge/session")
    assert unchanged.json()["state"] == "APPROVED_ONCE"
    assert unchanged.json()["world_version"] == 7
    assert unchanged.json()["receipt"] is None


async def test_mutation_without_csrf_is_rejected(
    client, public_challenge_origin, monkeypatch
) -> None:
    from app.routers import challenge as challenge_router

    _, body, _ = await _http_approved(client)
    calls = 0

    async def forbidden_commit(self, session_id, approval_id, request):
        nonlocal calls
        calls += 1
        raise AssertionError("commit service must not run")

    monkeypatch.setattr(challenge_router.ChallengeService, "commit", forbidden_commit)

    rejected = await client.post(
        "/challenge/commit",
        headers={"Origin": PUBLIC_ORIGIN},
        json=body,
    )

    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "INVALID_INPUT"
    assert calls == 0
    unchanged = await client.get("/challenge/session")
    assert unchanged.json()["state"] == "APPROVED_ONCE"
    assert unchanged.json()["world_version"] == 7


async def test_mutation_with_wrong_origin_is_rejected(
    client, public_challenge_origin, monkeypatch
) -> None:
    from app.routers import challenge as challenge_router

    headers, body, _ = await _http_approved(client)
    calls = 0

    async def forbidden_commit(self, session_id, approval_id, request):
        nonlocal calls
        calls += 1
        raise AssertionError("commit service must not run")

    monkeypatch.setattr(challenge_router.ChallengeService, "commit", forbidden_commit)

    rejected = await client.post(
        "/challenge/commit",
        headers={
            "Origin": "https://attacker.invalid",
            "X-CSRF-Token": headers["X-CSRF-Token"],
        },
        json=body,
    )

    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "INVALID_INPUT"
    assert calls == 0
    unchanged = await client.get("/challenge/session")
    assert unchanged.json()["state"] == "APPROVED_ONCE"
    assert unchanged.json()["world_version"] == 7


@pytest.mark.parametrize(
    ("status", "expected_status", "expected_code"),
    [
        ("EXPIRED", 410, "APPROVAL_EXPIRED"),
        ("REVOKED", 403, "APPROVAL_REVOKED"),
        ("INVALIDATED", 403, "APPROVAL_MISMATCH"),
        ("CONSUMED", 409, "APPROVAL_REPLAYED"),
    ],
)
async def test_terminal_commit_failure_deletes_approval_cookie(
    client,
    public_challenge_origin,
    status: str,
    expected_status: int,
    expected_code: str,
) -> None:
    headers, body, approval_id = await _http_approved(client)
    repository = ChallengeRepository()
    approval = await repository.load_approval(approval_id)
    assert approval is not None
    await repository.save_approval(approval.model_copy(update={"status": status}))

    rejected = await client.post("/challenge/commit", headers=headers, json=body)

    assert rejected.status_code == expected_status
    assert rejected.json()["error"]["code"] == expected_code
    assert any(
        "sv_challenge_approval=" in value and "Max-Age=0" in value
        for value in rejected.headers.get_list("set-cookie")
    )
    session_id = client.cookies.get("sv_challenge_session")
    unchanged = await repository.load_session(session_id)
    assert unchanged is not None
    assert unchanged.world.world_version == 7
    assert unchanged.receipt is None


async def test_consumed_approval_cannot_replay(
    client, public_challenge_origin
) -> None:
    headers, body, approval_id = await _http_approved(client)
    first = await client.post("/challenge/commit", headers=headers, json=body)
    assert first.status_code == 200
    client.cookies.set(
        "sv_challenge_approval", approval_id, path="/challenge/commit"
    )

    replayed = await client.post("/challenge/commit", headers=headers, json=body)

    assert replayed.status_code == 409
    assert replayed.json()["error"]["code"] == "APPROVAL_REPLAYED"
    assert any(
        "sv_challenge_approval=" in value and "Max-Age=0" in value
        for value in replayed.headers.get_list("set-cookie")
    )
    stored = await client.get("/challenge/session")
    assert stored.json()["state"] == "COMMITTED"
    assert stored.json()["world_version"] == 8
    assert stored.json()["budget_sc"] == 60
    assert len(stored.json()["receipt"]["created_events"]) == 1


async def test_reset_rotates_session_cookie_and_deletes_approval_cookie(
    client, public_challenge_origin
) -> None:
    created = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    old_generation = created.json()["session_generation"]
    old_session_id = client.cookies.get("sv_challenge_session")
    client.cookies.set(
        "sv_challenge_approval", "approval-old", path="/challenge/commit"
    )

    reset = await client.post(
        "/challenge/reset",
        headers={
            "Origin": PUBLIC_ORIGIN,
            "X-CSRF-Token": created.json()["csrf_token"],
        },
        json={"expected_generation": old_generation},
    )
    assert reset.status_code == 200
    assert reset.json()["state"] == "INITIAL"
    assert reset.json()["session_generation"] != old_generation
    assert client.cookies.get("sv_challenge_session") != old_session_id
    set_cookie = reset.headers.get_list("set-cookie")
    assert any("sv_challenge_approval=" in value and "Max-Age=0" in value for value in set_cookie)

    resumed = await client.get("/challenge/session")
    assert resumed.status_code == 200
    assert resumed.json()["session_generation"] == reset.json()["session_generation"]


async def test_reset_invalidates_old_approval(
    client, public_challenge_origin
) -> None:
    headers, body, approval_id = await _http_approved(client)
    approved = await client.get("/challenge/session")
    old_session_id = client.cookies.get("sv_challenge_session")
    assert old_session_id is not None

    reset = await client.post(
        "/challenge/reset",
        headers=headers,
        json={"expected_generation": approved.json()["session_generation"]},
    )
    assert reset.status_code == 200
    assert reset.json()["state"] == "INITIAL"
    client.cookies.set(
        "sv_challenge_approval",
        approval_id,
        path="/challenge/commit",
    )

    replayed = await client.post(
        "/challenge/commit",
        headers={
            "Origin": PUBLIC_ORIGIN,
            "X-CSRF-Token": reset.json()["csrf_token"],
        },
        json=body,
    )

    assert replayed.status_code == 403
    assert replayed.json()["error"]["code"] == "APPROVAL_REQUIRED"
    repository = ChallengeRepository()
    assert await repository.load_session(old_session_id) is None
    assert await repository.load_approval(approval_id) is None
    current = await client.get("/challenge/session")
    assert current.json()["state"] == "INITIAL"
    assert current.json()["world_version"] == 7
    assert current.json()["receipt"] is None


async def test_expired_session_rejects_old_receipt(
    client, public_challenge_origin
) -> None:
    headers, body, _ = await _http_approved(client)
    committed = await client.post(
        "/challenge/commit",
        headers=headers,
        json=body,
    )
    assert committed.status_code == 200
    old_receipt_id = committed.json()["receipt"]["receipt_id"]
    old_session_id = client.cookies.get("sv_challenge_session")
    assert old_session_id is not None
    await get_redis().delete(f"{SESSION_PREFIX}{old_session_id}")

    rejected = await client.get("/challenge/session")

    assert rejected.status_code == 410
    assert rejected.json()["error"]["code"] == "CHALLENGE_SESSION_EXPIRED"
    assert old_receipt_id not in rejected.text
    repository = ChallengeRepository()
    assert await repository.load_session(old_session_id) is None


async def test_production_town_id_is_rejected(
    client, public_challenge_origin, monkeypatch
) -> None:
    from app.routers import challenge as challenge_router

    created = await client.post(
        "/challenge/session",
        headers={"Origin": PUBLIC_ORIGIN},
    )
    calls = 0

    async def forbidden_investigate(self, session_id, request):
        nonlocal calls
        calls += 1
        raise AssertionError("investigate service must not run")

    monkeypatch.setattr(
        challenge_router.ChallengeService,
        "investigate",
        forbidden_investigate,
    )

    rejected = await client.post(
        "/challenge/investigate",
        headers={
            "Origin": PUBLIC_ORIGIN,
            "X-CSRF-Token": created.json()["csrf_token"],
        },
        json={"budget_cap_sc": 300, "town_id": "production-town"},
    )

    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "INVALID_INPUT"
    assert calls == 0
    unchanged = await client.get("/challenge/session")
    assert unchanged.json()["state"] == "INITIAL"
    assert unchanged.json()["scenario_id"] == "harbor-wage-crisis-v1"
    assert unchanged.json()["world_version"] == 7


async def test_reset_rejects_extra_body_and_returns_stable_domain_error(
    client, public_challenge_origin
) -> None:
    created = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    headers = {
        "Origin": PUBLIC_ORIGIN,
        "X-CSRF-Token": created.json()["csrf_token"],
    }
    extra = await client.post(
        "/challenge/reset",
        headers=headers,
        json={
            "expected_generation": created.json()["session_generation"],
            "unexpected": True,
        },
    )
    assert extra.status_code == 422
    assert extra.json()["error"]["code"] == "INVALID_INPUT"

    stale = await client.post(
        "/challenge/reset",
        headers=headers,
        json={"expected_generation": "stale-generation"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_TOOL_SURFACE"


async def test_unknown_router_error_is_redacted(
    client, public_challenge_origin, monkeypatch
) -> None:
    from app.routers import challenge as challenge_router

    async def explode(self, session_id):
        raise RuntimeError("secret-internal-trace")

    monkeypatch.setattr(challenge_router.ChallengeService, "create_or_resume", explode)
    response = await client.post(
        "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "CHALLENGE_INTERNAL_ERROR"
    assert "secret-internal-trace" not in response.text


async def test_challenge_requests_execute_no_database_statements(
    client, db_engine, public_challenge_origin
) -> None:
    statements: list[str] = []

    def record_statement(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db_engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        created = await client.post(
            "/challenge/session", headers={"Origin": PUBLIC_ORIGIN}
        )
        assert created.status_code == 200
        assert (await client.get("/challenge/session")).status_code == 200
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", record_statement)
    assert statements == []


def test_router_contract_constants_and_isolation() -> None:
    from app.routers import challenge as challenge_router

    assert challenge_router.SESSION_COOKIE == "sv_challenge_session"
    assert challenge_router.APPROVAL_COOKIE == "sv_challenge_approval"
    assert challenge_router.CSRF_HEADER == "X-CSRF-Token"
    assert challenge_router.PROTECTED_MUTATION_PATHS == (
        "/investigate", "/preview", "/approve", "/revoke", "/commit", "/verify", "/reset"
    )
    source = inspect.getsource(challenge_router)
    assert "Authorization" not in source
    assert "app.database" not in source
    assert "CORSMiddleware" not in source
