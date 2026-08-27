from __future__ import annotations

import ast
import inspect
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import Response

from app.challenge import models
from app.challenge.canonical import diff_hash, world_hash
from app.challenge.engine import (
    ACTUAL_SEED,
    FORECAST_SEEDS,
    TICK_COUNT,
    TICK_HOURS,
    VERIFICATION_HOURS,
    build_external_event_stream,
    build_intervention_preview,
    commit_world,
    investigate_world,
    simulate_world,
    verify_intervention,
)
from app.challenge.errors import (
    ERROR_STATUS_BY_CODE,
    ChallengeDomainError,
    ChallengeErrorCode,
)
from app.challenge.fixture import build_initial_world
from app.challenge.models import ChallengeState
from app.challenge.repository import ChallengeRepository
from app.challenge.service import FINAL_TOOL_SURFACE, ChallengeService
from app.config import settings
from app.main import app
from app.routers import challenge as challenge_router

pytestmark = pytest.mark.anyio

PUBLIC_ORIGIN = "https://simverse.world"
LOCKED_WORLD_HASH = "sha256:d095c7b5c759a58e6d07f5b6a6c4c2687016ce2b64295cfaad2490010ca5cb10"
BASELINE_SOURCE = (
    "# source_sha=de98dc4b47c67cd30ff2c3809493489577a3e4cf "
    "run=32968059066 job=98175015320"
)
WORKTREE_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = WORKTREE_ROOT / "backend"
BASELINE_PATH = WORKTREE_ROOT / "docs/webmcp-challenge/BACKEND_BASELINE_FAILURES.txt"

EXPECTED_MODEL_FIELDS = {
    "ChallengeResident": ("resident_id", "name", "cash_sc", "unpaid_wage_sc", "food_risk", "food_credit_sc", "stabilized"),
    "ChallengeEmployer": ("employer_id", "name", "overdue_payroll_sc", "repayment_claim_sc", "escrow_status"),
    "ChallengeRelationship": ("relationship_id", "source_id", "target_id", "direct_score", "tension"),
    "ChallengeEvent": ("event_id", "event_type", "region_id", "title", "description", "occurs_at"),
    "ChallengeMetrics": ("unpaid_residents", "high_food_risk_residents", "social_tension", "strike_risk_pct", "stabilized_residents"),
    "ChallengeWorld": ("scenario_id", "fixture_version", "world_version", "world_time", "budget_sc", "harbor_open", "residents", "employers", "relationships", "events", "metrics"),
    "EvidenceItem": ("evidence_type", "source_id", "title", "detail", "untrusted"),
    "EvidenceSnapshot": ("evidence_id", "based_on_world_version", "crisis_id", "priority_score", "region_id", "affected_resident_ids", "evidence", "enforced_constraints"),
    "ResidentCashChange": ("resident_id", "before_sc", "delta_sc", "after_sc"),
    "FoodCreditChange": ("resident_id", "before_sc", "delta_sc", "after_sc"),
    "EmployerClaim": ("employer_id", "amount_sc", "status"),
    "WorldDiff": ("scenario_id", "session_generation", "preview_id", "based_on_world_version", "budget_before_sc", "budget_after_sc", "resident_cash_changes", "food_credit_changes", "employer_claims_created", "events_created", "explicitly_unchanged"),
    "MetricRange": ("min", "max"),
    "ForecastResult": ("seeds", "high_food_risk_residents", "social_tension", "strike_risk_pct", "stabilized_residents"),
    "RejectedAlternative": ("alternative_id", "title", "total_cost_sc", "rejected_reason", "violated_invariants"),
    "InterventionPreview": ("preview_id", "crisis_id", "based_on_world_version", "intervention_id", "total_cost_sc", "remaining_budget_sc", "diff", "diff_hash", "forecast", "rejected_alternatives", "created_at"),
    "ApprovalRecord": ("approval_id", "session_generation", "preview_id", "diff_hash", "world_version", "status", "created_at", "expires_at"),
    "ExecutionReceipt": ("receipt_id", "scenario_id", "session_generation", "preview_id", "approval_fingerprint", "approved_diff_hash", "world_before_version", "world_after_version", "world_before_hash", "world_after_hash", "budget_before_sc", "budget_delta_sc", "budget_after_sc", "affected_residents", "created_events", "verified_invariants"),
    "OutcomeMetrics": ("high_food_risk_residents", "social_tension", "strike_risk_pct", "stabilized_residents"),
    "NoActionOutcome": ("high_food_risk_residents", "social_tension", "strike_risk_pct", "stabilized_residents", "strike_event_triggered"),
    "TickSnapshot": ("tick_index", "elapsed_hours", "world_time", "metrics", "external_event_ids"),
    "VerificationResult": ("receipt_id", "advance_hours", "baseline_snapshot", "tick_snapshots", "forecast", "actual", "no_action", "notable_deviation"),
    "AuditEvent": ("event_id", "action", "state_before", "state_after", "reason_code", "world_version_before", "world_version_after", "occurred_at"),
    "ChallengeSession": ("session_generation", "scenario_id", "fixture_version", "state", "created_at", "idle_expires_at", "absolute_expires_at", "csrf_token", "initial_world_hash", "world", "evidence", "preview", "active_approval_id", "approval_fingerprint", "approval_expires_at", "receipt", "verification", "audit_events"),
    "InvestigateRequest": ("budget_cap_sc",),
    "PreviewRequest": ("crisis_id", "budget_cap_sc"),
    "ApproveRequest": ("preview_id", "expected_world_version", "diff_hash"),
    "CommitRequest": ("preview_id", "expected_world_version", "diff_hash"),
    "VerifyRequest": ("receipt_id", "advance_hours"),
    "ResetRequest": ("expected_generation",),
    "ChallengeProjection": ("session_generation", "state", "scenario_id", "fixture_version", "world_version", "world_hash", "world_time", "budget_sc", "tool_surface", "expires_at", "csrf_token", "world", "evidence", "preview", "approval_fingerprint", "approval_expires_at", "receipt", "verification"),
    "SessionResult": ("session_id", "projection", "approval_id"),
}


def test_models_requests_and_server_only_projection_are_exact() -> None:
    public_models = {
        name: value
        for name, value in vars(models).items()
        if inspect.isclass(value)
        and value.__module__ == models.__name__
        and hasattr(value, "model_fields")
        and not name.startswith("_")
    }
    assert set(public_models) == set(EXPECTED_MODEL_FIELDS)
    assert {
        name: tuple(model.model_fields) for name, model in public_models.items()
    } == EXPECTED_MODEL_FIELDS
    assert all(model.model_config.get("extra") == "forbid" for model in public_models.values())
    for request_name in (
        "InvestigateRequest",
        "PreviewRequest",
        "ApproveRequest",
        "CommitRequest",
        "VerifyRequest",
        "ResetRequest",
    ):
        assert public_models[request_name].model_config.get("strict") is True
        assert public_models[request_name].model_json_schema()["additionalProperties"] is False
    investigate_schema = models.InvestigateRequest.model_json_schema()["properties"]
    assert investigate_schema["budget_cap_sc"] == {
        "maximum": 300,
        "minimum": 1,
        "title": "Budget Cap Sc",
        "type": "integer",
    }
    assert models.PreviewRequest.model_json_schema()["properties"] == {
        "crisis_id": {
            "const": "harbor-wage-crisis",
            "title": "Crisis Id",
            "type": "string",
        },
        "budget_cap_sc": {
            "const": 300,
            "title": "Budget Cap Sc",
            "type": "integer",
        },
    }
    assert models.VerifyRequest.model_json_schema()["properties"]["advance_hours"] == {
        "const": 72,
        "title": "Advance Hours",
        "type": "integer",
    }
    hash_fields = {
        "InterventionPreview": ("diff_hash",),
        "ApprovalRecord": ("diff_hash",),
        "ExecutionReceipt": (
            "approved_diff_hash",
            "world_before_hash",
            "world_after_hash",
        ),
        "ChallengeSession": ("initial_world_hash",),
        "ApproveRequest": ("diff_hash",),
        "CommitRequest": ("diff_hash",),
        "ChallengeProjection": ("world_hash",),
    }
    for model_name, field_names in hash_fields.items():
        properties = public_models[model_name].model_json_schema()["properties"]
        for field_name in field_names:
            assert properties[field_name]["pattern"] == "^sha256:[0-9a-f]{64}$"
    projection_fields = set(models.ChallengeProjection.model_fields)
    assert {"initial_world_hash", "active_approval_id", "approval_id"}.isdisjoint(
        projection_fields
    )


def test_states_errors_statuses_and_payload_are_exact() -> None:
    assert tuple(ChallengeState) == (
        ChallengeState.INITIAL,
        ChallengeState.EVIDENCE_READY,
        ChallengeState.PREVIEW_READY,
        ChallengeState.APPROVED_ONCE,
        ChallengeState.COMMITTED,
        ChallengeState.VERIFIED,
        ChallengeState.FAILED,
        ChallengeState.EXPIRED,
    )
    expected_statuses = {
        "INVALID_INPUT": 422,
        "CHALLENGE_SESSION_NOT_READY": 409,
        "CHALLENGE_SESSION_EXPIRED": 410,
        "INVALID_STATE_TRANSITION": 409,
        "NO_ACTIONABLE_CRISIS": 409,
        "EVIDENCE_STALE": 412,
        "BUDGET_EXCEEDED": 422,
        "POLICY_VIOLATION": 422,
        "PREVIEW_NOT_FOUND": 404,
        "PREVIEW_STALE": 412,
        "APPROVAL_REQUIRED": 403,
        "APPROVAL_MISMATCH": 403,
        "APPROVAL_EXPIRED": 410,
        "APPROVAL_REVOKED": 403,
        "APPROVAL_REPLAYED": 409,
        "STALE_WORLD_VERSION": 412,
        "STALE_TOOL_SURFACE": 409,
        "OUTCOME_ALREADY_VERIFIED": 409,
        "OUTCOME_INCOMPLETE": 500,
        "RESET_HASH_MISMATCH": 500,
        "CHALLENGE_INTERNAL_ERROR": 500,
    }
    assert {code.value: ERROR_STATUS_BY_CODE[code] for code in ChallengeErrorCode} == expected_statuses
    assert tuple(inspect.signature(ChallengeDomainError.__init__).parameters) == (
        "self",
        "code",
        "status",
        "message",
        "retryable",
        "current_state",
        "next_action",
    )
    error = ChallengeDomainError(
        ChallengeErrorCode.OUTCOME_INCOMPLETE,
        status=500,
        message="fixed public message",
        retryable=False,
        current_state=ChallengeState.FAILED,
        next_action="reset",
    )
    assert error.to_payload() == {
        "error": {
            "code": "OUTCOME_INCOMPLETE",
            "message": "fixed public message",
            "retryable": False,
            "current_state": "FAILED",
            "next_action": "reset",
        }
    }


def test_hash_seed_timeline_and_tool_surface_contract() -> None:
    baseline = build_initial_world()
    assert world_hash(baseline) == LOCKED_WORLD_HASH
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", world_hash(baseline))
    assert (FORECAST_SEEDS, ACTUAL_SEED) == ((101, 102, 103, 104, 105), 211)
    assert (VERIFICATION_HOURS, TICK_HOURS, TICK_COUNT) == (72, 6, 12)
    evidence = investigate_world(baseline, budget_cap_sc=300, evidence_id="contract-evidence")
    preview = build_intervention_preview(
        baseline,
        evidence,
        session_generation="contract-generation",
        preview_id="contract-preview",
        created_at=datetime(2042, 6, 12, 8, 5, tzinfo=UTC),
    )
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", diff_hash(preview.diff))
    committed, receipt = commit_world(baseline, preview.diff, "appr-A1B2")
    verified, result = verify_intervention(
        committed,
        build_initial_world(),
        LOCKED_WORLD_HASH,
        preview,
        receipt,
    )
    assert (committed.world_version, verified.world_version) == (8, 9)
    assert result.baseline_snapshot.elapsed_hours == 0
    assert [tick.elapsed_hours for tick in result.tick_snapshots] == list(range(6, 73, 6))
    assert result.actual.model_dump() == {
        "high_food_risk_residents": 1,
        "social_tension": 54,
        "strike_risk_pct": 38,
        "stabilized_residents": 5,
    }
    assert result.no_action.model_dump() == {
        "high_food_risk_residents": 3,
        "social_tension": 81,
        "strike_risk_pct": 100,
        "stabilized_residents": 0,
        "strike_event_triggered": True,
    }
    stream = build_external_event_stream(ACTUAL_SEED)
    actual = simulate_world(
        committed,
        seed=ACTUAL_SEED,
        intervention_applied=True,
        external_events=stream,
    )
    control = simulate_world(
        baseline,
        seed=ACTUAL_SEED,
        intervention_applied=False,
        external_events=stream,
    )
    assert [tick.external_event_ids for tick in actual.tick_snapshots] == [
        tick.external_event_ids for tick in control.tick_snapshots
    ]
    assert FINAL_TOOL_SURFACE == {
        ChallengeState.INITIAL: ("simverse_investigate_crisis",),
        ChallengeState.EVIDENCE_READY: ("simverse_investigate_crisis", "simverse_preview_intervention"),
        ChallengeState.PREVIEW_READY: ("simverse_preview_intervention",),
        ChallengeState.APPROVED_ONCE: ("simverse_commit_approved",),
        ChallengeState.COMMITTED: ("simverse_verify_outcome",),
        ChallengeState.VERIFIED: ("simverse_reset_town",),
        ChallengeState.FAILED: ("simverse_reset_town",),
        ChallengeState.EXPIRED: ("simverse_reset_town",),
    }


def test_router_api_signatures_routes_and_cookie_contract(monkeypatch) -> None:
    expected_routes = {
        ("POST", "/challenge/session"): (
            "create_session",
            ("request", "response"),
            None,
        ),
        ("GET", "/challenge/session"): ("get_session", ("request",), None),
        ("POST", "/challenge/investigate"): (
            "investigate",
            ("body", "request"),
            models.InvestigateRequest,
        ),
        ("POST", "/challenge/preview"): (
            "preview",
            ("body", "request", "response"),
            models.PreviewRequest,
        ),
        ("POST", "/challenge/approve"): (
            "approve",
            ("body", "request", "response"),
            models.ApproveRequest,
        ),
        ("POST", "/challenge/revoke"): (
            "revoke",
            ("request", "response"),
            None,
        ),
        ("POST", "/challenge/commit"): (
            "commit",
            ("body", "request", "response"),
            models.CommitRequest,
        ),
        ("POST", "/challenge/verify"): (
            "verify",
            ("body", "request"),
            models.VerifyRequest,
        ),
        ("POST", "/challenge/reset"): (
            "reset_session",
            ("body", "request", "response"),
            models.ResetRequest,
        ),
    }
    actual_routes = {
        (method, route.path): route
        for route in challenge_router.router.routes
        for method in route.methods or set()
    }
    assert set(actual_routes) == set(expected_routes)
    for route_key, (endpoint_name, parameters, body_model) in expected_routes.items():
        route = actual_routes[route_key]
        assert route.endpoint.__name__ == endpoint_name
        assert tuple(inspect.signature(route.endpoint).parameters) == parameters
        assert route.response_model is models.ChallengeProjection
        assert (
            route.body_field.field_info.annotation if route.body_field else None
        ) is body_model
    expected_service_api = {
        "create_or_resume": ("self", "session_id"),
        "get_session": ("self", "session_id"),
        "get_mutation_session": ("self", "session_id"),
        "investigate": ("self", "session_id", "request"),
        "preview": ("self", "session_id", "request"),
        "approve": ("self", "session_id", "request"),
        "revoke": ("self", "session_id"),
        "commit": ("self", "session_id", "approval_id", "request"),
        "verify": ("self", "session_id", "request"),
        "reset": ("self", "session_id", "request"),
    }
    for method_name, parameters in expected_service_api.items():
        assert tuple(
            inspect.signature(getattr(ChallengeService, method_name)).parameters
        ) == parameters
    expected_repository_api = {
        "create_session": ("self", "session_id", "session"),
        "load_session": ("self", "session_id"),
        "save_session": ("self", "session_id", "session"),
        "load_approval": ("self", "approval_id"),
        "save_approval": ("self", "approval"),
        "delete_approval": ("self", "approval_id"),
        "mutate_session": ("self", "session_id", "mutator"),
        "mutate_session_and_approval": (
            "self",
            "session_id",
            "approval_id",
            "mutator",
        ),
        "mutate_session_with_active_approval": ("self", "session_id", "mutator"),
        "replace_session": (
            "self",
            "old_session_id",
            "expected_generation",
            "new_session_id",
            "new_session",
        ),
    }
    for method_name, parameters in expected_repository_api.items():
        assert tuple(
            inspect.signature(getattr(ChallengeRepository, method_name)).parameters
        ) == parameters
    assert challenge_router.SESSION_COOKIE == "sv_challenge_session"
    assert challenge_router.APPROVAL_COOKIE == "sv_challenge_approval"
    assert challenge_router.CSRF_HEADER == "X-CSRF-Token"
    assert challenge_router.PROTECTED_MUTATION_PATHS == (
        "/investigate", "/preview", "/approve", "/revoke", "/commit", "/verify", "/reset"
    )
    monkeypatch.setattr(settings, "challenge_cookie_secure", True)
    response = Response()
    challenge_router.set_session_cookie(response, "session-secret")
    challenge_router.set_approval_cookie(response, "approval-secret")
    cookies = "\n".join(response.headers.getlist("set-cookie"))
    assert "sv_challenge_session=session-secret" in cookies
    assert "HttpOnly" in cookies and "Path=/challenge" in cookies
    assert "SameSite=lax" in cookies and "Secure" in cookies
    assert "sv_challenge_approval=approval-secret" in cookies
    assert "Max-Age=90" in cookies and "Path=/challenge/commit" in cookies
    assert "SameSite=strict" in cookies


def test_challenge_import_closure_is_allowlisted() -> None:
    target_files = sorted((BACKEND_ROOT / "app/challenge").rglob("*.py")) + [
        BACKEND_ROOT / "app/routers/challenge.py",
    ]
    allowed_app_modules = ("app.challenge", "app.config", "app.redis_client")
    allowed_external_roots = set(sys.stdlib_module_names) | {
        "fastapi",
        "pydantic",
        "pydantic_settings",
        "redis",
    }
    forbidden_fragments = (
        "app.database",
        "app.models",
        "app.agent",
        "app.llm",
        "app.services",
        "economy",
        "relation",
        "world_revision",
        "proposal",
        "lab",
    )
    imports: list[tuple[Path, str]] = []
    for path in target_files:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend((path, alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append((path, node.module))
    for path, module in imports:
        assert not any(fragment in module for fragment in forbidden_fragments), (
            path,
            module,
        )
        if module.startswith("app."):
            assert module.startswith(allowed_app_modules), (path, module)
        else:
            assert module.split(".", 1)[0] in allowed_external_roots, (path, module)


async def test_all_nine_routes_never_call_production_state(
    client,
    monkeypatch,
) -> None:
    from app import database
    from app.services import (
        auth_service,
        economy_bootstrap_service,
        lab_task_service,
        proposal_service,
        relation_service,
        world_revision_service,
    )

    production_calls: list[str] = []

    async def forbidden(*args, **kwargs):
        production_calls.append("called")
        raise AssertionError("challenge route touched production state")

    for module, name in (
        (database, "get_db"),
        (auth_service, "get_current_user"),
        (economy_bootstrap_service, "preview"),
        (relation_service, "get_pair"),
        (world_revision_service, "current_revision_id"),
        (proposal_service, "create_proposal"),
        (lab_task_service, "create_task"),
    ):
        monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(settings, "challenge_allowed_origins", [PUBLIC_ORIGIN])

    created = await client.post("/challenge/session", headers={"Origin": PUBLIC_ORIGIN})
    assert created.status_code == 200
    assert (await client.get("/challenge/session")).status_code == 200
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
    approval_body = {
        "preview_id": preview["preview_id"],
        "expected_world_version": preview["based_on_world_version"],
        "diff_hash": preview["diff_hash"],
    }
    approved = await client.post("/challenge/approve", headers=headers, json=approval_body)
    assert approved.status_code == 200
    revoked = await client.post("/challenge/revoke", headers=headers)
    assert revoked.status_code == 200
    approved_again = await client.post(
        "/challenge/approve", headers=headers, json=approval_body
    )
    assert approved_again.status_code == 200
    committed = await client.post("/challenge/commit", headers=headers, json=approval_body)
    assert committed.status_code == 200
    receipt_id = committed.json()["receipt"]["receipt_id"]
    verified = await client.post(
        "/challenge/verify",
        headers=headers,
        json={"receipt_id": receipt_id, "advance_hours": 72},
    )
    assert verified.status_code == 200
    reset = await client.post(
        "/challenge/reset",
        headers=headers,
        json={"expected_generation": verified.json()["session_generation"]},
    )
    assert reset.status_code == 200
    assert production_calls == []


def test_authoritative_backend_failure_baseline_is_exact() -> None:
    lines = BASELINE_PATH.read_text().splitlines()
    assert lines[0] == BASELINE_SOURCE
    node_ids = lines[1:]
    assert len(node_ids) == 48
    assert node_ids == sorted(set(node_ids))
    assert all(node_id.startswith("tests/") and "::" in node_id for node_id in node_ids)
