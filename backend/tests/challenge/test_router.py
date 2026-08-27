from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError
from sqlalchemy import event

from app.config import Settings, settings
from app.main import app

pytestmark = pytest.mark.anyio

PUBLIC_ORIGIN = "https://simverse.world"


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
