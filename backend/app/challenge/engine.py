from app.challenge.errors import (
    ERROR_STATUS_BY_CODE,
    ChallengeDomainError,
    ChallengeErrorCode,
)
from app.challenge.models import ChallengeWorld, EvidenceItem, EvidenceSnapshot

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
