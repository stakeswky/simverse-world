from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.challenge.fixture import build_initial_world
from app.challenge.models import (
    ApprovalRecord,
    ApproveRequest,
    AuditEvent,
    ChallengeEmployer,
    ChallengeEvent,
    ChallengeMetrics,
    ChallengeProjection,
    ChallengeRelationship,
    ChallengeResident,
    ChallengeSession,
    ChallengeState,
    ChallengeWorld,
    CommitRequest,
    EmployerClaim,
    EvidenceItem,
    EvidenceSnapshot,
    ExecutionReceipt,
    FoodCreditChange,
    ForecastResult,
    InvestigateRequest,
    InterventionPreview,
    MetricRange,
    NoActionOutcome,
    OutcomeMetrics,
    PreviewRequest,
    RejectedAlternative,
    ResetRequest,
    ResidentCashChange,
    SessionResult,
    TickSnapshot,
    VerificationResult,
    VerifyRequest,
    WorldDiff,
)

NOW = datetime(2042, 6, 12, 8, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def _forecast_payload() -> dict[str, object]:
    return {
        "seeds": [7, 11, 19],
        "high_food_risk_residents": {"min": 0, "max": 1},
        "social_tension": {"min": 32, "max": 38},
        "strike_risk_pct": {"min": 15, "max": 22},
        "stabilized_residents": {"min": 5, "max": 6},
    }


def _diff_payload() -> dict[str, object]:
    return {
        "scenario_id": "harbor-wage-crisis-v1",
        "session_generation": "generation-01",
        "preview_id": "preview-01",
        "based_on_world_version": 7,
        "budget_before_sc": 300,
        "budget_after_sc": 0,
        "resident_cash_changes": [
            {
                "resident_id": f"harbor-resident-{index:02d}",
                "before_sc": 10,
                "delta_sc": 30,
                "after_sc": 40,
            }
            for index in range(1, 7)
        ],
        "food_credit_changes": [
            {
                "resident_id": f"harbor-resident-{index:02d}",
                "before_sc": 0,
                "delta_sc": 20,
                "after_sc": 20,
            }
            for index in range(1, 7)
        ],
        "employer_claims_created": [
            {"employer_id": "harbor-employer-a", "amount_sc": 90, "status": "PENDING"},
            {"employer_id": "harbor-employer-b", "amount_sc": 90, "status": "PENDING"},
        ],
        "events_created": [
            {
                "event_id": "harbor-wage-bridge-approved",
                "event_type": "INTERVENTION",
                "region_id": "harbor-district",
                "title": "Harbor wage bridge approved",
                "description": "A bounded wage and food-credit bridge was approved.",
                "occurs_at": NOW,
            }
        ],
        "explicitly_unchanged": ["harbor_open", "relationships"],
    }


def _preview_payload() -> dict[str, object]:
    return {
        "preview_id": "preview-01",
        "crisis_id": "harbor-wage-crisis",
        "based_on_world_version": 7,
        "intervention_id": "harbor-wage-bridge",
        "total_cost_sc": 300,
        "remaining_budget_sc": 0,
        "diff": _diff_payload(),
        "diff_hash": HASH_A,
        "forecast": _forecast_payload(),
        "rejected_alternatives": [
            {
                "alternative_id": "full-bailout",
                "title": "Full employer bailout",
                "total_cost_sc": 360,
                "rejected_reason": "BUDGET_EXCEEDED",
                "violated_invariants": ["budget_cap"],
            }
        ],
        "created_at": NOW,
    }


def _receipt_payload() -> dict[str, object]:
    return {
        "receipt_id": "receipt-01",
        "scenario_id": "harbor-wage-crisis-v1",
        "session_generation": "generation-01",
        "preview_id": "preview-01",
        "approval_fingerprint": "approval-fingerprint-01",
        "approved_diff_hash": HASH_A,
        "world_before_version": 7,
        "world_after_version": 8,
        "world_before_hash": HASH_A,
        "world_after_hash": HASH_B,
        "budget_before_sc": 300,
        "budget_delta_sc": -300,
        "budget_after_sc": 0,
        "affected_residents": [f"harbor-resident-{index:02d}" for index in range(1, 7)],
        "created_events": ["harbor-wage-bridge-approved"],
        "verified_invariants": ["budget_nonnegative", "harbor_open"],
    }


def _tick_payload(index: int) -> dict[str, object]:
    return {
        "tick_index": index,
        "elapsed_hours": index * 6,
        "world_time": NOW + timedelta(hours=index * 6),
        "metrics": {
            "high_food_risk_residents": 0,
            "social_tension": 38 - index,
            "strike_risk_pct": 22 - index,
            "stabilized_residents": 6,
        },
        "external_event_ids": [],
    }


def _verification_payload() -> dict[str, object]:
    return {
        "receipt_id": "receipt-01",
        "advance_hours": 72,
        "baseline_snapshot": _tick_payload(0),
        "tick_snapshots": [_tick_payload(index) for index in range(1, 13)],
        "forecast": _forecast_payload(),
        "actual": {
            "high_food_risk_residents": 0,
            "social_tension": 26,
            "strike_risk_pct": 10,
            "stabilized_residents": 6,
        },
        "no_action": {
            "high_food_risk_residents": 4,
            "social_tension": 83,
            "strike_risk_pct": 91,
            "stabilized_residents": 0,
            "strike_event_triggered": True,
        },
        "notable_deviation": "Actual tension improved beyond the forecast range.",
    }


def _session_payload() -> dict[str, object]:
    return {
        "session_generation": "generation-01",
        "scenario_id": "harbor-wage-crisis-v1",
        "fixture_version": 1,
        "state": "VERIFIED",
        "created_at": NOW,
        "idle_expires_at": NOW + timedelta(minutes=15),
        "absolute_expires_at": NOW + timedelta(hours=2),
        "csrf_token": "csrf-01",
        "initial_world_hash": HASH_A,
        "world": build_initial_world(),
        "evidence": {
            "evidence_id": "evidence-01",
            "based_on_world_version": 7,
            "crisis_id": "harbor-wage-crisis",
            "priority_score": 92,
            "region_id": "harbor",
            "affected_resident_ids": [
                f"harbor-resident-{index:02d}" for index in range(1, 7)
            ],
            "evidence": [
                {
                    "evidence_type": "economic",
                    "source_id": "delayed-harbor-payroll",
                    "title": "Delayed payroll",
                    "detail": "Six residents are unpaid.",
                    "untrusted": False,
                }
            ],
            "enforced_constraints": ["budget_cap", "no_employer_bailout"],
        },
        "preview": _preview_payload(),
        "active_approval_id": "approval-01",
        "approval_fingerprint": "approval-fingerprint-01",
        "approval_expires_at": NOW + timedelta(minutes=5),
        "receipt": _receipt_payload(),
        "verification": _verification_payload(),
        "audit_events": [
            {
                "event_id": "audit-01",
                "action": "investigate",
                "state_before": "INITIAL",
                "state_after": "EVIDENCE_READY",
                "reason_code": None,
                "world_version_before": 7,
                "world_version_after": 7,
                "occurred_at": NOW,
            }
        ],
    }


def _projection_payload() -> dict[str, object]:
    session = ChallengeSession.model_validate(_session_payload())
    return {
        "session_generation": session.session_generation,
        "state": session.state,
        "scenario_id": session.scenario_id,
        "fixture_version": session.fixture_version,
        "world_version": session.world.world_version,
        "world_hash": HASH_B,
        "world_time": session.world.world_time,
        "budget_sc": session.world.budget_sc,
        "tool_surface": ["simverse_verify_outcome"],
        "expires_at": session.idle_expires_at,
        "csrf_token": session.csrf_token,
        "world": session.world,
        "evidence": session.evidence,
        "preview": session.preview,
        "approval_fingerprint": session.approval_fingerprint,
        "approval_expires_at": session.approval_expires_at,
        "receipt": session.receipt,
        "verification": session.verification,
    }


def _valid_model_payloads() -> list[tuple[type, dict[str, object]]]:
    world = build_initial_world()
    return [
        (ChallengeResident, world.residents[0].model_dump()),
        (ChallengeEmployer, world.employers[0].model_dump()),
        (ChallengeRelationship, world.relationships[0].model_dump()),
        (ChallengeEvent, world.events[0].model_dump()),
        (ChallengeMetrics, world.metrics.model_dump()),
        (ChallengeWorld, world.model_dump()),
        (EvidenceItem, {"evidence_type": "economic", "source_id": "source-01", "title": "Title", "detail": "Detail", "untrusted": False}),
        (EvidenceSnapshot, _session_payload()["evidence"]),
        (ResidentCashChange, _diff_payload()["resident_cash_changes"][0]),
        (FoodCreditChange, _diff_payload()["food_credit_changes"][0]),
        (EmployerClaim, _diff_payload()["employer_claims_created"][0]),
        (WorldDiff, _diff_payload()),
        (MetricRange, {"min": 0, "max": 1}),
        (ForecastResult, _forecast_payload()),
        (RejectedAlternative, _preview_payload()["rejected_alternatives"][0]),
        (InterventionPreview, _preview_payload()),
        (ApprovalRecord, {"approval_id": "approval-01", "session_generation": "generation-01", "preview_id": "preview-01", "diff_hash": HASH_A, "world_version": 7, "status": "APPROVED_ONCE", "created_at": NOW, "expires_at": NOW + timedelta(minutes=5)}),
        (ExecutionReceipt, _receipt_payload()),
        (OutcomeMetrics, _verification_payload()["actual"]),
        (NoActionOutcome, _verification_payload()["no_action"]),
        (TickSnapshot, _tick_payload(1)),
        (VerificationResult, _verification_payload()),
        (AuditEvent, _session_payload()["audit_events"][0]),
        (ChallengeSession, _session_payload()),
        (InvestigateRequest, {"budget_cap_sc": 300}),
        (PreviewRequest, {"crisis_id": "harbor-wage-crisis", "budget_cap_sc": 300}),
        (ApproveRequest, {"preview_id": "preview-01", "expected_world_version": 7, "diff_hash": HASH_A}),
        (CommitRequest, {"preview_id": "preview-01", "expected_world_version": 7, "diff_hash": HASH_A}),
        (VerifyRequest, {"receipt_id": "receipt-01", "advance_hours": 72}),
        (ResetRequest, {"expected_generation": "generation-01"}),
        (ChallengeProjection, _projection_payload()),
        (SessionResult, {"session_id": "session-01", "projection": _projection_payload(), "approval_id": "approval-01"}),
    ]


@pytest.mark.parametrize(("model", "payload"), _valid_model_payloads())
def test_each_model_accepts_valid_input_and_rejects_extra_fields(
    model: type, payload: dict[str, object]
) -> None:
    assert model.model_validate(payload)

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        model.model_validate({**payload, "unexpected": True})


def test_challenge_state_rejects_unknown_values() -> None:
    assert ChallengeState("INITIAL") is ChallengeState.INITIAL
    with pytest.raises(ValueError):
        ChallengeState("UNKNOWN")


@pytest.mark.parametrize("model", [InterventionPreview, ApprovalRecord, ExecutionReceipt])
def test_hash_fields_reject_noncanonical_values(model: type) -> None:
    payload = next(payload for candidate, payload in _valid_model_payloads() if candidate is model)
    hash_field = {
        InterventionPreview: "diff_hash",
        ApprovalRecord: "diff_hash",
        ExecutionReceipt: "approved_diff_hash",
    }[model]

    with pytest.raises(ValidationError, match="String should match pattern"):
        model.model_validate({**payload, hash_field: "not-a-hash"})


@pytest.mark.parametrize(
    ("model", "payload", "field"),
    [
        (InvestigateRequest, {"budget_cap_sc": 300}, "budget_cap_sc"),
        (PreviewRequest, {"crisis_id": "harbor-wage-crisis", "budget_cap_sc": 300}, "budget_cap_sc"),
        (ApproveRequest, {"preview_id": "preview-01", "expected_world_version": 7, "diff_hash": HASH_A}, "expected_world_version"),
        (CommitRequest, {"preview_id": "preview-01", "expected_world_version": 7, "diff_hash": HASH_A}, "expected_world_version"),
        (VerifyRequest, {"receipt_id": "receipt-01", "advance_hours": 72}, "advance_hours"),
    ],
)
def test_requests_reject_string_to_integer_coercion(
    model: type, payload: dict[str, object], field: str
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**payload, field: str(payload[field])})


@pytest.mark.parametrize("budget", [0, 301])
def test_investigate_budget_cap_is_bounded(budget: int) -> None:
    with pytest.raises(ValidationError):
        InvestigateRequest(budget_cap_sc=budget)


def test_metric_range_rejects_inverted_bounds() -> None:
    with pytest.raises(ValidationError, match="min must not exceed max"):
        MetricRange(min=2, max=1)


def test_verification_requires_t0_baseline_and_twelve_six_hour_ticks() -> None:
    result = VerificationResult.model_validate(_verification_payload())
    assert result.baseline_snapshot.elapsed_hours == 0
    assert [tick.elapsed_hours for tick in result.tick_snapshots] == list(range(6, 73, 6))

    too_short = _verification_payload()
    too_short["tick_snapshots"] = too_short["tick_snapshots"][:-1]
    with pytest.raises(ValidationError, match="exactly twelve"):
        VerificationResult.model_validate(too_short)

    wrong_baseline = _verification_payload()
    wrong_baseline["baseline_snapshot"] = _tick_payload(1)
    with pytest.raises(ValidationError, match=r"T\+0"):
        VerificationResult.model_validate(wrong_baseline)


def test_list_models_sort_stable_ids_and_reject_duplicates() -> None:
    payload = _diff_payload()
    payload["resident_cash_changes"] = list(reversed(payload["resident_cash_changes"]))
    diff = WorldDiff.model_validate(payload)
    assert [change.resident_id for change in diff.resident_cash_changes] == sorted(
        change.resident_id for change in diff.resident_cash_changes
    )

    duplicated = _diff_payload()
    duplicated["employer_claims_created"] = [
        duplicated["employer_claims_created"][0],
        duplicated["employer_claims_created"][0],
    ]
    with pytest.raises(ValidationError, match="duplicate employer_id"):
        WorldDiff.model_validate(duplicated)


def test_projection_excludes_server_only_session_and_approval_fields() -> None:
    dumped = ChallengeProjection.model_validate(_projection_payload()).model_dump()

    assert "initial_world_hash" not in dumped
    assert "active_approval_id" not in dumped
    assert "approval_id" not in dumped
    assert SessionResult.model_fields.keys() == {"session_id", "projection", "approval_id"}
