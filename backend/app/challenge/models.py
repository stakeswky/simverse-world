from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Callable, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

HashString = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
_ListItem = TypeVar("_ListItem")


def _stable_unique(
    values: list[_ListItem], key: Callable[[_ListItem], object], label: str
) -> list[_ListItem]:
    identifiers = [key(value) for value in values]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"duplicate {label}")
    return sorted(values, key=key)


class _ChallengeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ChallengeRequest(_ChallengeModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ChallengeState(StrEnum):
    INITIAL = "INITIAL"
    EVIDENCE_READY = "EVIDENCE_READY"
    PREVIEW_READY = "PREVIEW_READY"
    APPROVED_ONCE = "APPROVED_ONCE"
    COMMITTED = "COMMITTED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class ChallengeResident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resident_id: str
    name: str
    cash_sc: int
    unpaid_wage_sc: int
    food_risk: Literal["LOW", "MEDIUM", "HIGH"]
    food_credit_sc: int
    stabilized: bool


class ChallengeEmployer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employer_id: str
    name: str
    overdue_payroll_sc: int
    repayment_claim_sc: int
    escrow_status: Literal["NONE", "PENDING", "MET", "MISSED"]


class ChallengeRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_id: str
    source_id: str
    target_id: str
    direct_score: int
    tension: int


class ChallengeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    region_id: str
    title: str
    description: str
    occurs_at: datetime


class ChallengeMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unpaid_residents: int
    high_food_risk_residents: int
    social_tension: int
    strike_risk_pct: int
    stabilized_residents: int


class ChallengeWorld(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: Literal["harbor-wage-crisis-v1"]
    fixture_version: Literal[1]
    world_version: int
    world_time: datetime
    budget_sc: int
    harbor_open: bool
    residents: list[ChallengeResident]
    employers: list[ChallengeEmployer]
    relationships: list[ChallengeRelationship]
    events: list[ChallengeEvent]
    metrics: ChallengeMetrics

    @model_validator(mode="after")
    def stable_collections(self) -> "ChallengeWorld":
        self.residents = _stable_unique(
            self.residents, lambda value: value.resident_id, "resident_id"
        )
        self.employers = _stable_unique(
            self.employers, lambda value: value.employer_id, "employer_id"
        )
        self.relationships = _stable_unique(
            self.relationships, lambda value: value.relationship_id, "relationship_id"
        )
        self.events = _stable_unique(self.events, lambda value: value.event_id, "event_id")
        return self


class EvidenceItem(_ChallengeModel):
    evidence_type: Literal["economic", "resident", "relationship", "event", "map"]
    source_id: str
    title: str
    detail: str
    untrusted: bool


class EvidenceSnapshot(_ChallengeModel):
    evidence_id: str
    based_on_world_version: int
    crisis_id: Literal["harbor-wage-crisis"]
    priority_score: int
    region_id: Literal["harbor"]
    affected_resident_ids: list[str]
    evidence: list[EvidenceItem]
    enforced_constraints: list[str]

    @model_validator(mode="after")
    def stable_collections(self) -> "EvidenceSnapshot":
        self.affected_resident_ids = _stable_unique(
            self.affected_resident_ids, lambda value: value, "resident_id"
        )
        self.evidence = _stable_unique(
            self.evidence, lambda value: value.source_id, "evidence source_id"
        )
        self.enforced_constraints = _stable_unique(
            self.enforced_constraints, lambda value: value, "constraint"
        )
        return self


class ResidentCashChange(_ChallengeModel):
    resident_id: str
    before_sc: int
    delta_sc: int
    after_sc: int


class FoodCreditChange(_ChallengeModel):
    resident_id: str
    before_sc: int
    delta_sc: int
    after_sc: int


class EmployerClaim(_ChallengeModel):
    employer_id: str
    amount_sc: int
    status: Literal["PENDING"]


class WorldDiff(_ChallengeModel):
    scenario_id: Literal["harbor-wage-crisis-v1"]
    session_generation: str
    preview_id: str
    based_on_world_version: int
    budget_before_sc: int
    budget_after_sc: int
    resident_cash_changes: list[ResidentCashChange]
    food_credit_changes: list[FoodCreditChange]
    employer_claims_created: list[EmployerClaim]
    events_created: list[ChallengeEvent]
    explicitly_unchanged: list[str]

    @model_validator(mode="after")
    def stable_collections(self) -> "WorldDiff":
        self.resident_cash_changes = _stable_unique(
            self.resident_cash_changes, lambda value: value.resident_id, "resident_id"
        )
        self.food_credit_changes = _stable_unique(
            self.food_credit_changes, lambda value: value.resident_id, "resident_id"
        )
        self.employer_claims_created = _stable_unique(
            self.employer_claims_created, lambda value: value.employer_id, "employer_id"
        )
        self.events_created = _stable_unique(
            self.events_created, lambda value: value.event_id, "event_id"
        )
        self.explicitly_unchanged = _stable_unique(
            self.explicitly_unchanged, lambda value: value, "unchanged field"
        )
        return self


class MetricRange(_ChallengeModel):
    min: int
    max: int

    @model_validator(mode="after")
    def ordered_bounds(self) -> "MetricRange":
        if self.min > self.max:
            raise ValueError("min must not exceed max")
        return self


class ForecastResult(_ChallengeModel):
    seeds: list[int]
    high_food_risk_residents: MetricRange
    social_tension: MetricRange
    strike_risk_pct: MetricRange
    stabilized_residents: MetricRange

    @model_validator(mode="after")
    def stable_seeds(self) -> "ForecastResult":
        self.seeds = _stable_unique(self.seeds, lambda value: value, "seed")
        return self


class RejectedAlternative(_ChallengeModel):
    alternative_id: str
    title: str
    total_cost_sc: int | None
    rejected_reason: Literal["BUDGET_EXCEEDED", "POLICY_VIOLATION"]
    violated_invariants: list[str]

    @model_validator(mode="after")
    def stable_invariants(self) -> "RejectedAlternative":
        self.violated_invariants = _stable_unique(
            self.violated_invariants, lambda value: value, "violated invariant"
        )
        return self


class InterventionPreview(_ChallengeModel):
    preview_id: str
    crisis_id: Literal["harbor-wage-crisis"]
    based_on_world_version: int
    intervention_id: Literal["harbor-wage-bridge"]
    total_cost_sc: int
    remaining_budget_sc: int
    diff: WorldDiff
    diff_hash: HashString
    forecast: ForecastResult
    rejected_alternatives: list[RejectedAlternative]
    created_at: datetime

    @model_validator(mode="after")
    def stable_alternatives(self) -> "InterventionPreview":
        self.rejected_alternatives = _stable_unique(
            self.rejected_alternatives,
            lambda value: value.alternative_id,
            "alternative_id",
        )
        return self


class ApprovalRecord(_ChallengeModel):
    approval_id: str
    session_generation: str
    preview_id: str
    diff_hash: HashString
    world_version: int
    status: Literal[
        "APPROVED_ONCE", "CONSUMED", "REVOKED", "EXPIRED", "INVALIDATED"
    ]
    created_at: datetime
    expires_at: datetime


class ExecutionReceipt(_ChallengeModel):
    receipt_id: str
    scenario_id: Literal["harbor-wage-crisis-v1"]
    session_generation: str
    preview_id: str
    approval_fingerprint: str
    approved_diff_hash: HashString
    world_before_version: int
    world_after_version: int
    world_before_hash: HashString
    world_after_hash: HashString
    budget_before_sc: int
    budget_delta_sc: int
    budget_after_sc: int
    affected_residents: list[str]
    created_events: list[str]
    verified_invariants: list[str]

    @model_validator(mode="after")
    def stable_collections(self) -> "ExecutionReceipt":
        self.affected_residents = _stable_unique(
            self.affected_residents, lambda value: value, "affected resident"
        )
        self.created_events = _stable_unique(
            self.created_events, lambda value: value, "created event"
        )
        self.verified_invariants = _stable_unique(
            self.verified_invariants, lambda value: value, "verified invariant"
        )
        return self


class OutcomeMetrics(_ChallengeModel):
    high_food_risk_residents: int
    social_tension: int
    strike_risk_pct: int
    stabilized_residents: int


class NoActionOutcome(OutcomeMetrics):
    strike_event_triggered: bool


class TickSnapshot(_ChallengeModel):
    tick_index: int
    elapsed_hours: int
    world_time: datetime
    metrics: OutcomeMetrics
    external_event_ids: list[str]

    @model_validator(mode="after")
    def stable_external_events(self) -> "TickSnapshot":
        self.external_event_ids = _stable_unique(
            self.external_event_ids, lambda value: value, "external event_id"
        )
        return self


class VerificationResult(_ChallengeModel):
    receipt_id: str
    advance_hours: Literal[72]
    baseline_snapshot: TickSnapshot
    tick_snapshots: list[TickSnapshot]
    forecast: ForecastResult
    actual: OutcomeMetrics
    no_action: NoActionOutcome
    notable_deviation: str

    @model_validator(mode="after")
    def exact_tick_series(self) -> "VerificationResult":
        baseline = self.baseline_snapshot
        if baseline.tick_index != 0 or baseline.elapsed_hours != 0:
            raise ValueError("baseline snapshot must be T+0")
        self.tick_snapshots = _stable_unique(
            self.tick_snapshots, lambda value: value.tick_index, "tick_index"
        )
        if len(self.tick_snapshots) != 12:
            raise ValueError("tick snapshots must contain exactly twelve items")
        for expected_index, tick in enumerate(self.tick_snapshots, start=1):
            expected_hours = expected_index * 6
            if tick.tick_index != expected_index or tick.elapsed_hours != expected_hours:
                raise ValueError("tick snapshots must cover T+6 through T+72")
            if tick.world_time != baseline.world_time + timedelta(hours=expected_hours):
                raise ValueError("tick world_time must advance in six-hour steps")
        return self


class AuditEvent(_ChallengeModel):
    event_id: str
    action: str
    state_before: ChallengeState
    state_after: ChallengeState
    reason_code: str | None
    world_version_before: int
    world_version_after: int
    occurred_at: datetime


class ChallengeSession(_ChallengeModel):
    session_generation: str
    scenario_id: Literal["harbor-wage-crisis-v1"]
    fixture_version: Literal[1]
    state: ChallengeState
    created_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    csrf_token: str
    initial_world_hash: HashString
    world: ChallengeWorld
    evidence: EvidenceSnapshot | None
    preview: InterventionPreview | None
    active_approval_id: str | None
    approval_fingerprint: str | None
    approval_expires_at: datetime | None
    receipt: ExecutionReceipt | None
    verification: VerificationResult | None
    audit_events: list[AuditEvent]

    @model_validator(mode="after")
    def stable_audit_events(self) -> "ChallengeSession":
        self.audit_events = _stable_unique(
            self.audit_events, lambda value: value.event_id, "audit event_id"
        )
        return self


class InvestigateRequest(_ChallengeRequest):
    budget_cap_sc: int = Field(ge=1, le=300)


class PreviewRequest(_ChallengeRequest):
    crisis_id: Literal["harbor-wage-crisis"]
    budget_cap_sc: Literal[300]


class ApproveRequest(_ChallengeRequest):
    preview_id: str
    expected_world_version: int
    diff_hash: HashString


class CommitRequest(_ChallengeRequest):
    preview_id: str
    expected_world_version: int
    diff_hash: HashString


class VerifyRequest(_ChallengeRequest):
    receipt_id: str
    advance_hours: Literal[72]


class ResetRequest(_ChallengeRequest):
    expected_generation: str


class ChallengeProjection(_ChallengeModel):
    session_generation: str
    state: ChallengeState
    scenario_id: Literal["harbor-wage-crisis-v1"]
    fixture_version: Literal[1]
    world_version: int
    world_hash: HashString
    world_time: datetime
    budget_sc: int
    tool_surface: list[str]
    expires_at: datetime
    csrf_token: str
    world: ChallengeWorld
    evidence: EvidenceSnapshot | None
    preview: InterventionPreview | None
    approval_fingerprint: str | None
    approval_expires_at: datetime | None
    receipt: ExecutionReceipt | None
    verification: VerificationResult | None

    @model_validator(mode="after")
    def stable_tool_surface(self) -> "ChallengeProjection":
        self.tool_surface = _stable_unique(
            self.tool_surface, lambda value: value, "tool name"
        )
        return self


class SessionResult(_ChallengeModel):
    session_id: str
    projection: ChallengeProjection
    approval_id: str | None
