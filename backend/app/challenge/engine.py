import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.challenge.canonical import diff_hash, world_hash
from app.challenge.errors import (
    ERROR_STATUS_BY_CODE,
    ChallengeDomainError,
    ChallengeErrorCode,
)
from app.challenge.models import (
    ChallengeEvent,
    ChallengeMetrics,
    ChallengeState,
    ChallengeWorld,
    EmployerClaim,
    ExecutionReceipt,
    EvidenceItem,
    EvidenceSnapshot,
    FoodCreditChange,
    ForecastResult,
    HashString,
    InterventionPreview,
    MetricRange,
    NoActionOutcome,
    OutcomeMetrics,
    RejectedAlternative,
    ResidentCashChange,
    TickSnapshot,
    VerificationResult,
    WorldDiff,
)
from app.challenge.fixture import build_initial_world

FORECAST_SEEDS = (101, 102, 103, 104, 105)
ACTUAL_SEED = 211
VERIFICATION_HOURS = 72
TICK_HOURS = 6
TICK_COUNT = 12

ENFORCED_CONSTRAINTS = (
    "budget_lte_300_sc",
    "harbor_must_remain_open",
    "no_direct_preference_rewrite",
    "no_direct_relationship_rewrite",
    "challenge_town_isolated",
)

INTERVENTION_TOTAL_COST_SC = 240
MEDIATION_COST_SC = 20
EXPLICITLY_UNCHANGED = (
    "resident_personality",
    "resident_preferences",
    "resident_intentions",
    "direct_relationship_scores",
    "harbor_operating_status",
    "production_town_state",
)
PROHIBITED_EVENT_TYPES = {
    "FORCED_PREFERENCE_REWRITE",
    "DIRECT_RELATIONSHIP_REWRITE",
    "HARBOR_CLOSURE",
}


@dataclass(frozen=True)
class ExternalEventSlot:
    tick_index: int
    event_id: str
    escrow_miss: bool


@dataclass(frozen=True)
class SimulationRun:
    baseline_snapshot: TickSnapshot
    tick_snapshots: tuple[TickSnapshot, ...]
    final_metrics: OutcomeMetrics
    created_event_ids: tuple[str, ...]
    escrow_miss: bool


def _domain_error(
    code: ChallengeErrorCode,
    *,
    message: str,
    next_action: str | None,
) -> ChallengeDomainError:
    return ChallengeDomainError(
        code,
        status=ERROR_STATUS_BY_CODE[code],
        message=message,
        retryable=False,
        current_state=None,
        next_action=next_action,
    )


def _has_actionable_harbor_crisis(world: ChallengeWorld) -> bool:
    unpaid_residents = [
        resident for resident in world.residents if resident.unpaid_wage_sc > 0
    ]
    event_types = {event.event_type for event in world.events}
    return (
        world.scenario_id == "harbor-wage-crisis-v1"
        and world.harbor_open
        and len(unpaid_residents) == 6
        and world.metrics.unpaid_residents == 6
        and world.metrics.high_food_risk_residents >= 2
        and world.metrics.social_tension >= 50
        and world.metrics.strike_risk_pct >= 50
        and sum(employer.overdue_payroll_sc for employer in world.employers) >= 180
        and {"PAYROLL_DELAY", "STRIKE_RUMOR"}.issubset(event_types)
    )


def _harbor_priority(world: ChallengeWorld) -> int:
    unpaid_pressure = min(30, world.metrics.unpaid_residents * 5)
    food_pressure = min(10, world.metrics.high_food_risk_residents * 5)
    tension_pressure = round(world.metrics.social_tension * 0.3)
    strike_pressure = round(world.metrics.strike_risk_pct * 0.45)
    operational_pressure = 1 if world.harbor_open else 0
    return min(
        100,
        unpaid_pressure
        + food_pressure
        + tension_pressure
        + strike_pressure
        + operational_pressure,
    )


def investigate_world(
    world: ChallengeWorld,
    budget_cap_sc: int,
    evidence_id: str,
) -> EvidenceSnapshot:
    if budget_cap_sc < 300:
        raise _domain_error(
            ChallengeErrorCode.BUDGET_EXCEEDED,
            message="The Harbor intervention requires a 300 SC policy ceiling.",
            next_action="Set budget_cap_sc to 300 and investigate again.",
        )
    if budget_cap_sc > 300:
        raise _domain_error(
            ChallengeErrorCode.POLICY_VIOLATION,
            message="The challenge policy ceiling cannot exceed 300 SC.",
            next_action="Set budget_cap_sc to 300 and investigate again.",
        )
    if not _has_actionable_harbor_crisis(world):
        raise _domain_error(
            ChallengeErrorCode.NO_ACTIONABLE_CRISIS,
            message="No actionable Harbor wage crisis matches the challenge policy.",
            next_action="Reset the challenge session to restore the locked fixture.",
        )

    affected_residents = [
        resident for resident in world.residents if resident.unpaid_wage_sc > 0
    ]
    untrusted_notice = next(
        event for event in world.events if event.event_type == "UNTRUSTED_CONTENT"
    )
    overdue_payroll = sum(
        employer.overdue_payroll_sc for employer in world.employers
    )
    direct_tension = max(
        relationship.tension for relationship in world.relationships
    )

    return EvidenceSnapshot(
        evidence_id=evidence_id,
        based_on_world_version=world.world_version,
        crisis_id="harbor-wage-crisis",
        priority_score=_harbor_priority(world),
        region_id="harbor",
        affected_resident_ids=[
            resident.resident_id for resident in affected_residents
        ],
        evidence=[
            EvidenceItem(
                evidence_type="economic",
                source_id="harbor-economic-ledger",
                title="Harbor payroll remains overdue",
                detail=(
                    f"{len(affected_residents)} residents await wages while employers "
                    f"report {overdue_payroll} SC overdue payroll."
                ),
                untrusted=False,
            ),
            EvidenceItem(
                evidence_type="map",
                source_id="harbor-map-region",
                title="Harbor remains operational",
                detail="The isolated Harbor district remains open during the crisis.",
                untrusted=False,
            ),
            EvidenceItem(
                evidence_type="relationship",
                source_id="harbor-relationship-pressure",
                title="Resident-employer tension is elevated",
                detail=f"The highest observed direct tension is {direct_tension}.",
                untrusted=False,
            ),
            EvidenceItem(
                evidence_type="resident",
                source_id="harbor-resident-cohort",
                title="Six residents face wage and food pressure",
                detail=(
                    f"{world.metrics.high_food_risk_residents} residents have high "
                    "food risk and all 6 are unpaid."
                ),
                untrusted=False,
            ),
            EvidenceItem(
                evidence_type="event",
                source_id=untrusted_notice.event_id,
                title=untrusted_notice.title,
                detail=untrusted_notice.description,
                untrusted=True,
            ),
        ],
        enforced_constraints=list(ENFORCED_CONSTRAINTS),
    )


def _policy_violation(message: str) -> ChallengeDomainError:
    return _domain_error(
        ChallengeErrorCode.POLICY_VIOLATION,
        message=message,
        next_action="Reset the challenge session and build a policy-safe preview.",
    )


def validate_world_diff(world: ChallengeWorld, diff: WorldDiff) -> None:
    if diff.scenario_id != world.scenario_id:
        raise _policy_violation("The diff targets a different challenge scenario.")
    if diff.based_on_world_version != world.world_version:
        raise _domain_error(
            ChallengeErrorCode.STALE_WORLD_VERSION,
            message="The intervention diff was built from a stale world version.",
            next_action="Investigate the current world and build a new preview.",
        )
    if not diff.session_generation or not diff.preview_id:
        raise _policy_violation("The diff must be bound to a session and preview.")
    if not world.harbor_open:
        raise _policy_violation("The Harbor must remain open during intervention.")

    proposed_cost_sc = diff.budget_before_sc - diff.budget_after_sc
    if diff.budget_after_sc < 0 or proposed_cost_sc > world.budget_sc:
        raise _domain_error(
            ChallengeErrorCode.BUDGET_EXCEEDED,
            message="The intervention exceeds the available 300 SC policy budget.",
            next_action="Use the locked 240 SC Harbor wage bridge.",
        )
    if (
        diff.budget_before_sc != world.budget_sc
        or proposed_cost_sc != INTERVENTION_TOTAL_COST_SC
        or diff.budget_after_sc != world.budget_sc - INTERVENTION_TOTAL_COST_SC
    ):
        raise _policy_violation("The intervention budget does not match the locked plan.")

    prohibited = {
        event.event_type
        for event in diff.events_created
        if event.event_type in PROHIBITED_EVENT_TYPES
    }
    if prohibited:
        raise _policy_violation(
            "The intervention attempts a forced rewrite or Harbor closure."
        )
    if set(diff.explicitly_unchanged) != set(EXPLICITLY_UNCHANGED):
        raise _policy_violation("The diff does not preserve every locked invariant.")

    residents = {resident.resident_id: resident for resident in world.residents}
    expected_resident_ids = {
        resident.resident_id
        for resident in world.residents
        if resident.unpaid_wage_sc > 0
    }
    if {change.resident_id for change in diff.resident_cash_changes} != (
        expected_resident_ids
    ):
        raise _policy_violation("The wage bridge must cover all six unpaid residents.")
    for change in diff.resident_cash_changes:
        resident = residents[change.resident_id]
        if (
            change.before_sc != resident.cash_sc
            or change.delta_sc != resident.unpaid_wage_sc
            or change.after_sc != resident.cash_sc + resident.unpaid_wage_sc
        ):
            raise _policy_violation("A resident wage transfer is not policy-safe.")

    expected_food_ids = {
        resident.resident_id
        for resident in world.residents
        if resident.food_risk == "HIGH"
    }
    if {change.resident_id for change in diff.food_credit_changes} != expected_food_ids:
        raise _policy_violation("Food credits must target the two high-risk residents.")
    for change in diff.food_credit_changes:
        resident = residents[change.resident_id]
        if (
            change.before_sc != resident.food_credit_sc
            or change.delta_sc != 20
            or change.after_sc != resident.food_credit_sc + 20
        ):
            raise _policy_violation("A resident food credit is not policy-safe.")

    employers = {employer.employer_id: employer for employer in world.employers}
    if {claim.employer_id for claim in diff.employer_claims_created} != set(employers):
        raise _policy_violation("Every Harbor employer must receive one repayment claim.")
    for claim in diff.employer_claims_created:
        employer = employers[claim.employer_id]
        if claim.amount_sc != employer.overdue_payroll_sc or claim.status != "PENDING":
            raise _policy_violation("An employer repayment claim is not policy-safe.")

    if len(diff.events_created) != 1:
        raise _policy_violation("The intervention may create only one mediation event.")
    mediation = diff.events_created[0]
    if (
        mediation.event_id != "employer-escrow-mediation"
        or mediation.event_type != "MEDIATION"
        or mediation.region_id != "harbor-district"
    ):
        raise _policy_violation("The intervention event must be Harbor mediation.")

    component_cost_sc = (
        sum(change.delta_sc for change in diff.resident_cash_changes)
        + sum(change.delta_sc for change in diff.food_credit_changes)
        + MEDIATION_COST_SC
    )
    if component_cost_sc != INTERVENTION_TOTAL_COST_SC:
        raise _policy_violation("The intervention components do not total 240 SC.")


def apply_world_diff(world: ChallengeWorld, diff: WorldDiff) -> ChallengeWorld:
    validate_world_diff(world, diff)
    applied = world.model_copy(deep=True)
    applied.world_version += 1
    applied.budget_sc = diff.budget_after_sc

    resident_changes = {
        change.resident_id: change for change in diff.resident_cash_changes
    }
    food_changes = {
        change.resident_id: change for change in diff.food_credit_changes
    }
    for resident in applied.residents:
        if change := resident_changes.get(resident.resident_id):
            resident.cash_sc = change.after_sc
            resident.unpaid_wage_sc = 0
        if food_change := food_changes.get(resident.resident_id):
            resident.food_credit_sc = food_change.after_sc

    claims = {claim.employer_id: claim for claim in diff.employer_claims_created}
    for employer in applied.employers:
        claim = claims[employer.employer_id]
        employer.overdue_payroll_sc = 0
        employer.repayment_claim_sc += claim.amount_sc
        employer.escrow_status = claim.status

    applied.events.extend(event.model_copy(deep=True) for event in diff.events_created)
    applied.events.sort(key=lambda event: event.event_id)
    applied.metrics.unpaid_residents = sum(
        resident.unpaid_wage_sc > 0 for resident in applied.residents
    )
    return applied


def commit_world(
    world: ChallengeWorld,
    diff: WorldDiff,
    approval_fingerprint: str,
) -> tuple[ChallengeWorld, ExecutionReceipt]:
    if (
        len(approval_fingerprint) != 9
        or not approval_fingerprint.startswith("appr-")
        or any(
            character not in "0123456789ABCDEF"
            for character in approval_fingerprint[5:]
        )
    ):
        raise _domain_error(
            ChallengeErrorCode.APPROVAL_MISMATCH,
            message="Approval fingerprint does not match the trusted format.",
            next_action="Approve the current preview again.",
        )

    before_hash = world_hash(world)
    relationships_before = [
        relationship.model_dump(mode="json") for relationship in world.relationships
    ]
    resident_ids_before = [resident.resident_id for resident in world.residents]
    event_ids_before = {event.event_id for event in world.events}
    committed = apply_world_diff(world, diff)

    relationships_after = [
        relationship.model_dump(mode="json")
        for relationship in committed.relationships
    ]
    resident_ids_after = [resident.resident_id for resident in committed.residents]
    created_event_ids = sorted(
        event.event_id
        for event in committed.events
        if event.event_id not in event_ids_before
    )
    postconditions_hold = (
        committed.world_version == world.world_version + 1
        and committed.budget_sc == diff.budget_after_sc == 60
        and committed.harbor_open is True
        and committed.scenario_id == world.scenario_id
        and committed.fixture_version == world.fixture_version
        and committed.world_time == world.world_time
        and relationships_after == relationships_before
        and resident_ids_after == resident_ids_before
        and created_event_ids == ["employer-escrow-mediation"]
        and committed.metrics.unpaid_residents == 0
    )
    if not postconditions_hold:
        raise _policy_violation(
            "The committed world failed an isolated intervention invariant."
        )

    after_hash = world_hash(committed)
    approved_diff_hash = diff_hash(diff)
    receipt_material = "\n".join(
        (
            "simverse-challenge-receipt-v1",
            approved_diff_hash,
            approval_fingerprint,
            before_hash,
            after_hash,
        )
    )
    receipt_suffix = hashlib.sha256(
        receipt_material.encode("utf-8")
    ).hexdigest()[:8].upper()
    receipt = ExecutionReceipt(
        receipt_id=f"SV-{world.world_time.year}-{receipt_suffix}",
        scenario_id=world.scenario_id,
        session_generation=diff.session_generation,
        preview_id=diff.preview_id,
        approval_fingerprint=approval_fingerprint,
        approved_diff_hash=approved_diff_hash,
        world_before_version=world.world_version,
        world_after_version=committed.world_version,
        world_before_hash=before_hash,
        world_after_hash=after_hash,
        budget_before_sc=world.budget_sc,
        budget_delta_sc=committed.budget_sc - world.budget_sc,
        budget_after_sc=committed.budget_sc,
        affected_residents=[
            change.resident_id for change in diff.resident_cash_changes
        ],
        created_events=created_event_ids,
        verified_invariants=list(ENFORCED_CONSTRAINTS),
    )
    return committed, receipt


def _outcome_incomplete(message: str) -> ChallengeDomainError:
    return ChallengeDomainError(
        ChallengeErrorCode.OUTCOME_INCOMPLETE,
        status=409,
        message=message,
        retryable=False,
        current_state=ChallengeState.COMMITTED,
        next_action="reset_town",
    )


def _external_events(seed: int) -> tuple[ExternalEventSlot, ...]:
    digest = hashlib.sha256(
        f"harbor-exogenous-v1:{seed}".encode("utf-8")
    ).digest()
    rng = random.Random(seed)
    escrow_miss = digest[1] > 250
    escrow_tick = 8
    slots = []
    for tick_index in range(1, TICK_COUNT + 1):
        entropy = digest[(tick_index + 1) % len(digest)] ^ rng.randrange(256)
        event_kind = (
            "escrow-miss"
            if escrow_miss and tick_index == escrow_tick
            else "market-shift"
        )
        slots.append(
            ExternalEventSlot(
                tick_index=tick_index,
                event_id=(
                    f"harbor-{event_kind}-{tick_index:02d}-{entropy:02x}"
                ),
                escrow_miss=escrow_miss and tick_index == escrow_tick,
            )
        )
    return tuple(slots)


def build_external_event_stream(seed: int) -> tuple[ExternalEventSlot, ...]:
    return _external_events(seed)


def _outcome_from_world(world: ChallengeWorld) -> OutcomeMetrics:
    return OutcomeMetrics(
        high_food_risk_residents=world.metrics.high_food_risk_residents,
        social_tension=world.metrics.social_tension,
        strike_risk_pct=world.metrics.strike_risk_pct,
        stabilized_residents=world.metrics.stabilized_residents,
    )


def _intervention_outcome(seed: int, escrow_miss: bool) -> OutcomeMetrics:
    return OutcomeMetrics(
        high_food_risk_residents=seed % 2,
        social_tension=50 + 2 * (seed % 5) + (2 if escrow_miss else 0),
        strike_risk_pct=(28, 32, 35, 38, 42)[seed % 5]
        + (6 if escrow_miss else 0),
        stabilized_residents=5 if seed % 2 else 6,
    )


def _no_action_outcome(seed: int, escrow_miss: bool) -> OutcomeMetrics:
    return OutcomeMetrics(
        high_food_risk_residents=2 + seed % 2,
        social_tension=79 + (2 if escrow_miss else 0),
        strike_risk_pct=min(100, 94 + (6 if escrow_miss else 0)),
        stabilized_residents=0,
    )


def _linear_metric(start: int, final: int, tick_index: int) -> int:
    return start + ((final - start) * tick_index) // TICK_COUNT


def _tick_series(
    world: ChallengeWorld,
    final_metrics: OutcomeMetrics,
    external_events: tuple[ExternalEventSlot, ...],
) -> tuple[TickSnapshot, tuple[TickSnapshot, ...]]:
    baseline_metrics = _outcome_from_world(world)
    baseline = TickSnapshot(
        tick_index=0,
        elapsed_hours=0,
        world_time=world.world_time,
        metrics=baseline_metrics,
        external_event_ids=[],
    )
    ticks = tuple(
        TickSnapshot(
            tick_index=slot.tick_index,
            elapsed_hours=slot.tick_index * TICK_HOURS,
            world_time=world.world_time
            + timedelta(hours=slot.tick_index * TICK_HOURS),
            metrics=OutcomeMetrics(
                high_food_risk_residents=_linear_metric(
                    baseline_metrics.high_food_risk_residents,
                    final_metrics.high_food_risk_residents,
                    slot.tick_index,
                ),
                social_tension=_linear_metric(
                    baseline_metrics.social_tension,
                    final_metrics.social_tension,
                    slot.tick_index,
                ),
                strike_risk_pct=_linear_metric(
                    baseline_metrics.strike_risk_pct,
                    final_metrics.strike_risk_pct,
                    slot.tick_index,
                ),
                stabilized_residents=_linear_metric(
                    baseline_metrics.stabilized_residents,
                    final_metrics.stabilized_residents,
                    slot.tick_index,
                ),
            ),
            external_event_ids=[slot.event_id],
        )
        for slot in external_events
    )
    return baseline, ticks


def simulate_world(
    world: ChallengeWorld,
    *,
    seed: int,
    intervention_applied: bool,
    external_events: tuple[ExternalEventSlot, ...],
) -> SimulationRun:
    expected_events = _external_events(seed)
    if external_events != expected_events:
        raise _outcome_incomplete(
            "The simulation external event stream does not match the locked seed."
        )
    escrow_miss = any(slot.escrow_miss for slot in external_events)
    final_metrics = (
        _intervention_outcome(seed, escrow_miss)
        if intervention_applied
        else _no_action_outcome(seed, escrow_miss)
    )
    baseline, ticks = _tick_series(world, final_metrics, external_events)
    strike_event_triggered = (
        not intervention_applied and final_metrics.strike_risk_pct == 100
    )
    return SimulationRun(
        baseline_snapshot=baseline,
        tick_snapshots=ticks,
        final_metrics=final_metrics,
        created_event_ids=(
            ("harbor-general-strike",) if strike_event_triggered else ()
        ),
        escrow_miss=escrow_miss,
    )


def apply_actual_result(
    committed_world: ChallengeWorld,
    actual: SimulationRun,
) -> ChallengeWorld:
    verified = committed_world.model_copy(deep=True)
    verified.world_version += 1
    verified.world_time += timedelta(hours=VERIFICATION_HOURS)
    verified.metrics.high_food_risk_residents = (
        actual.final_metrics.high_food_risk_residents
    )
    verified.metrics.social_tension = actual.final_metrics.social_tension
    verified.metrics.strike_risk_pct = actual.final_metrics.strike_risk_pct
    verified.metrics.stabilized_residents = (
        actual.final_metrics.stabilized_residents
    )
    for index, resident in enumerate(verified.residents):
        resident.food_risk = (
            "HIGH"
            if index < actual.final_metrics.high_food_risk_residents
            else "LOW"
        )
        resident.stabilized = index < actual.final_metrics.stabilized_residents
    for index, employer in enumerate(verified.employers):
        employer.escrow_status = (
            "MISSED" if actual.escrow_miss and index == 0 else "MET"
        )
    return ChallengeWorld.model_validate(verified.model_dump())


def build_verification(
    forecast: ForecastResult,
    actual: SimulationRun,
    control: SimulationRun,
    receipt_id: str,
) -> VerificationResult:
    no_action = NoActionOutcome(
        **control.final_metrics.model_dump(),
        strike_event_triggered=("harbor-general-strike" in control.created_event_ids),
    )
    deviation = (
        "Escrow miss caused a notable deviation: actual social tension reached "
        f"{actual.final_metrics.social_tension} and strike risk reached "
        f"{actual.final_metrics.strike_risk_pct}%."
    )
    return VerificationResult(
        receipt_id=receipt_id,
        advance_hours=VERIFICATION_HOURS,
        baseline_snapshot=control.baseline_snapshot,
        tick_snapshots=list(actual.tick_snapshots),
        forecast=forecast,
        actual=actual.final_metrics,
        no_action=no_action,
        notable_deviation=deviation,
    )


def verify_intervention(
    committed_world: ChallengeWorld,
    baseline_world: ChallengeWorld,
    locked_initial_world_hash: HashString,
    preview: InterventionPreview,
    receipt: ExecutionReceipt,
) -> tuple[ChallengeWorld, VerificationResult]:
    expected_baseline = build_initial_world()
    baseline_hash = world_hash(baseline_world)
    if (
        baseline_hash != world_hash(expected_baseline)
        or baseline_hash != locked_initial_world_hash
        or baseline_hash != receipt.world_before_hash
    ):
        raise _outcome_incomplete(
            "Initial challenge baseline does not match the committed receipt."
        )
    if (
        world_hash(committed_world) != receipt.world_after_hash
        or receipt.world_before_version != 7
        or receipt.world_after_version != 8
        or committed_world.world_version != 8
        or preview.based_on_world_version != 7
        or committed_world.world_version != receipt.world_after_version
        or receipt.approved_diff_hash != preview.diff_hash
        or receipt.preview_id != preview.preview_id
    ):
        raise _outcome_incomplete(
            "Committed challenge world does not match the approved receipt."
        )
    external_events = build_external_event_stream(ACTUAL_SEED)
    actual = simulate_world(
        committed_world,
        seed=ACTUAL_SEED,
        intervention_applied=True,
        external_events=external_events,
    )
    control = simulate_world(
        baseline_world,
        seed=ACTUAL_SEED,
        intervention_applied=False,
        external_events=external_events,
    )
    verified_world = apply_actual_result(committed_world, actual)
    verification = build_verification(
        preview.forecast,
        actual,
        control,
        receipt.receipt_id,
    )
    return verified_world, verification


def _simulate_intervention_seed(
    world: ChallengeWorld,
    diff: WorldDiff,
    seed: int,
) -> ChallengeMetrics:
    simulated = apply_world_diff(world, diff)
    outcome = simulate_world(
        simulated,
        seed=seed,
        intervention_applied=True,
        external_events=build_external_event_stream(seed),
    ).final_metrics
    simulated.metrics.high_food_risk_residents = (
        outcome.high_food_risk_residents
    )
    simulated.metrics.social_tension = outcome.social_tension
    simulated.metrics.strike_risk_pct = outcome.strike_risk_pct
    simulated.metrics.stabilized_residents = outcome.stabilized_residents
    return simulated.metrics


def _metric_range(values: list[int]) -> MetricRange:
    return MetricRange(min=min(values), max=max(values))


def forecast_intervention(
    world: ChallengeWorld,
    diff: WorldDiff,
) -> ForecastResult:
    validate_world_diff(world, diff)
    outcomes = [
        _simulate_intervention_seed(world, diff, seed) for seed in FORECAST_SEEDS
    ]
    return ForecastResult(
        seeds=list(FORECAST_SEEDS),
        high_food_risk_residents=_metric_range(
            [outcome.high_food_risk_residents for outcome in outcomes]
        ),
        social_tension=_metric_range(
            [outcome.social_tension for outcome in outcomes]
        ),
        strike_risk_pct=_metric_range(
            [outcome.strike_risk_pct for outcome in outcomes]
        ),
        stabilized_residents=_metric_range(
            [outcome.stabilized_residents for outcome in outcomes]
        ),
    )


def build_intervention_preview(
    world: ChallengeWorld,
    evidence: EvidenceSnapshot,
    session_generation: str,
    preview_id: str,
    created_at: datetime,
) -> InterventionPreview:
    if evidence.based_on_world_version != world.world_version:
        raise _domain_error(
            ChallengeErrorCode.EVIDENCE_STALE,
            message="The evidence was captured from a stale world version.",
            next_action="Investigate the current world before previewing.",
        )
    affected_residents = {
        resident.resident_id
        for resident in world.residents
        if resident.unpaid_wage_sc > 0
    }
    if (
        evidence.crisis_id != "harbor-wage-crisis"
        or set(evidence.affected_resident_ids) != affected_residents
        or set(evidence.enforced_constraints) != set(ENFORCED_CONSTRAINTS)
    ):
        raise _policy_violation("The evidence does not match the locked Harbor crisis.")

    diff = WorldDiff(
        scenario_id=world.scenario_id,
        session_generation=session_generation,
        preview_id=preview_id,
        based_on_world_version=world.world_version,
        budget_before_sc=world.budget_sc,
        budget_after_sc=world.budget_sc - INTERVENTION_TOTAL_COST_SC,
        resident_cash_changes=[
            ResidentCashChange(
                resident_id=resident.resident_id,
                before_sc=resident.cash_sc,
                delta_sc=resident.unpaid_wage_sc,
                after_sc=resident.cash_sc + resident.unpaid_wage_sc,
            )
            for resident in world.residents
            if resident.unpaid_wage_sc > 0
        ],
        food_credit_changes=[
            FoodCreditChange(
                resident_id=resident.resident_id,
                before_sc=resident.food_credit_sc,
                delta_sc=20,
                after_sc=resident.food_credit_sc + 20,
            )
            for resident in world.residents
            if resident.food_risk == "HIGH"
        ],
        employer_claims_created=[
            EmployerClaim(
                employer_id=employer.employer_id,
                amount_sc=employer.overdue_payroll_sc,
                status="PENDING",
            )
            for employer in world.employers
        ],
        events_created=[
            ChallengeEvent(
                event_id="employer-escrow-mediation",
                event_type="MEDIATION",
                region_id="harbor-district",
                title="Employer escrow mediation opened",
                description=(
                    "Harbor employers enter escrow mediation for the wage bridge."
                ),
                occurs_at=created_at,
            )
        ],
        explicitly_unchanged=list(EXPLICITLY_UNCHANGED),
    )
    validate_world_diff(world, diff)
    forecast = forecast_intervention(world, diff)
    return InterventionPreview(
        preview_id=preview_id,
        crisis_id="harbor-wage-crisis",
        based_on_world_version=world.world_version,
        intervention_id="harbor-wage-bridge",
        total_cost_sc=INTERVENTION_TOTAL_COST_SC,
        remaining_budget_sc=diff.budget_after_sc,
        diff=diff,
        diff_hash=diff_hash(diff),
        forecast=forecast,
        rejected_alternatives=[
            RejectedAlternative(
                alternative_id="universal-town-subsidy",
                title="Universal town subsidy",
                total_cost_sc=320,
                rejected_reason="BUDGET_EXCEEDED",
                violated_invariants=["budget_lte_300_sc"],
            ),
            RejectedAlternative(
                alternative_id="forced-rewrite-and-harbor-closure",
                title="Forced morale rewrite and Harbor closure",
                total_cost_sc=None,
                rejected_reason="POLICY_VIOLATION",
                violated_invariants=[
                    "harbor_must_remain_open",
                    "no_direct_preference_rewrite",
                    "no_direct_relationship_rewrite",
                ],
            ),
        ],
        created_at=created_at,
    )
