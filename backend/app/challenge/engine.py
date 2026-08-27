from datetime import datetime

from app.challenge.canonical import diff_hash
from app.challenge.errors import (
    ERROR_STATUS_BY_CODE,
    ChallengeDomainError,
    ChallengeErrorCode,
)
from app.challenge.models import (
    ChallengeEvent,
    ChallengeMetrics,
    ChallengeWorld,
    EmployerClaim,
    EvidenceItem,
    EvidenceSnapshot,
    FoodCreditChange,
    ForecastResult,
    InterventionPreview,
    MetricRange,
    RejectedAlternative,
    ResidentCashChange,
    WorldDiff,
)

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


def _simulate_intervention_seed(
    world: ChallengeWorld,
    diff: WorldDiff,
    seed: int,
) -> ChallengeMetrics:
    simulated = apply_world_diff(world, diff)
    seed_offset = seed - FORECAST_SEEDS[0]
    simulated.metrics.high_food_risk_residents = seed % 2
    simulated.metrics.social_tension = 50 + (seed_offset * 2) % 10
    simulated.metrics.strike_risk_pct = 28 + (seed_offset * 7) % 21
    simulated.metrics.stabilized_residents = 5 + seed % 2
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
