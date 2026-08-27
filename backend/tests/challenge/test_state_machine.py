from datetime import UTC, datetime
import inspect

import pytest

import app.challenge.service as service_module
from app.challenge.errors import ChallengeDomainError, ChallengeErrorCode
from app.challenge.models import ChallengeState, InvestigateRequest
from app.challenge.canonical import world_hash
from app.challenge.repository import ChallengeRepository, SESSION_PREFIX
from app.challenge.service import (
    FINAL_TOOL_SURFACE,
    ChallengeService,
    validate_transition,
)
from app.redis_client import get_redis

pytestmark = pytest.mark.anyio

NOW = datetime(2042, 6, 12, 8, tzinfo=UTC)
ACTIONS = ("investigate", "preview", "approve", "revoke", "commit", "verify", "reset")
LEGAL_TRANSITIONS = {
    (ChallengeState.INITIAL, "investigate"): ChallengeState.EVIDENCE_READY,
    (ChallengeState.EVIDENCE_READY, "investigate"): ChallengeState.EVIDENCE_READY,
    (ChallengeState.EVIDENCE_READY, "preview"): ChallengeState.PREVIEW_READY,
    (ChallengeState.PREVIEW_READY, "preview"): ChallengeState.PREVIEW_READY,
    (ChallengeState.PREVIEW_READY, "approve"): ChallengeState.APPROVED_ONCE,
    (ChallengeState.APPROVED_ONCE, "preview"): ChallengeState.PREVIEW_READY,
    (ChallengeState.APPROVED_ONCE, "revoke"): ChallengeState.PREVIEW_READY,
    (ChallengeState.APPROVED_ONCE, "commit"): ChallengeState.COMMITTED,
    (ChallengeState.COMMITTED, "verify"): ChallengeState.VERIFIED,
    **{(state, "reset"): ChallengeState.INITIAL for state in ChallengeState},
}


def _expected_error(state: ChallengeState, action: str) -> ChallengeErrorCode:
    if state is ChallengeState.EXPIRED:
        return ChallengeErrorCode.CHALLENGE_SESSION_EXPIRED
    if action == "commit" and state in {
        ChallengeState.INITIAL,
        ChallengeState.PREVIEW_READY,
    }:
        return ChallengeErrorCode.APPROVAL_REQUIRED
    if action == "commit" and state in {
        ChallengeState.COMMITTED,
        ChallengeState.VERIFIED,
    }:
        return ChallengeErrorCode.APPROVAL_REPLAYED
    if action == "verify" and state is ChallengeState.VERIFIED:
        return ChallengeErrorCode.OUTCOME_ALREADY_VERIFIED
    return ChallengeErrorCode.INVALID_STATE_TRANSITION


def test_final_tool_surface_is_exact_for_every_state() -> None:
    assert FINAL_TOOL_SURFACE == {
        ChallengeState.INITIAL: ("simverse_investigate_crisis",),
        ChallengeState.EVIDENCE_READY: (
            "simverse_investigate_crisis",
            "simverse_preview_intervention",
        ),
        ChallengeState.PREVIEW_READY: ("simverse_preview_intervention",),
        ChallengeState.APPROVED_ONCE: ("simverse_commit_approved",),
        ChallengeState.COMMITTED: ("simverse_verify_outcome",),
        ChallengeState.VERIFIED: ("simverse_reset_town",),
        ChallengeState.FAILED: ("simverse_reset_town",),
        ChallengeState.EXPIRED: ("simverse_reset_town",),
    }


@pytest.mark.parametrize(
    ("state", "action"),
    [(state, action) for state in ChallengeState for action in ACTIONS],
)
def test_complete_state_action_matrix(state: ChallengeState, action: str) -> None:
    target = LEGAL_TRANSITIONS.get((state, action))
    if target is not None:
        assert validate_transition(state, action) is target
        return

    with pytest.raises(ChallengeDomainError) as rejected:
        validate_transition(state, action)
    assert rejected.value.code is _expected_error(state, action)
    assert rejected.value.current_state is state


async def test_create_resume_and_projection_security() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)

    created = await service.create_or_resume(None)
    assert created.projection.state is ChallengeState.INITIAL
    assert created.projection.tool_surface == ["simverse_investigate_crisis"]
    assert created.projection.world_hash == created.projection.world_hash
    assert created.projection.world_version == 7
    assert created.approval_id is None
    stored = await repository.load_session(created.session_id)
    assert stored is not None
    assert stored.initial_world_hash == created.projection.world_hash

    resumed = await service.create_or_resume(created.session_id)
    assert resumed.session_id == created.session_id
    assert resumed.projection.session_generation == created.projection.session_generation
    assert len(await get_redis().keys(f"{SESSION_PREFIX}*")) == 1

    dumped = resumed.projection.model_dump()
    assert "initial_world_hash" not in dumped
    assert "active_approval_id" not in dumped
    assert "approval_id" not in dumped


async def test_create_or_resume_replaces_missing_absolute_key_but_get_fails() -> None:
    service = ChallengeService(
        repository=ChallengeRepository(clock=lambda: NOW), clock=lambda: NOW
    )

    replacement = await service.create_or_resume("expired-cookie-session")
    assert replacement.session_id != "expired-cookie-session"
    with pytest.raises(ChallengeDomainError) as missing:
        await service.get_session("expired-cookie-session")
    assert missing.value.code is ChallengeErrorCode.CHALLENGE_SESSION_EXPIRED

    with pytest.raises(ChallengeDomainError) as absent:
        await service.get_session(None)
    assert absent.value.code is ChallengeErrorCode.CHALLENGE_SESSION_NOT_READY


async def test_investigate_transitions_and_rebuilds_evidence_without_world_changes() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    before = created.projection

    investigated = await service.investigate(
        created.session_id, InvestigateRequest(budget_cap_sc=300)
    )

    assert investigated.projection.state is ChallengeState.EVIDENCE_READY
    assert investigated.projection.evidence is not None
    assert investigated.projection.evidence.based_on_world_version == 7
    assert investigated.projection.world_version == before.world_version
    assert investigated.projection.world_time == before.world_time
    assert investigated.projection.budget_sc == before.budget_sc
    assert investigated.projection.world_hash == before.world_hash
    first_evidence_id = investigated.projection.evidence.evidence_id

    rebuilt = await service.investigate(
        created.session_id, InvestigateRequest(budget_cap_sc=300)
    )
    assert rebuilt.projection.state is ChallengeState.EVIDENCE_READY
    assert rebuilt.projection.evidence is not None
    assert rebuilt.projection.evidence.evidence_id != first_evidence_id
    assert rebuilt.projection.world_hash == before.world_hash

    stored = await repository.load_session(created.session_id)
    assert stored is not None
    assert world_hash(stored.world) == before.world_hash
    assert [event.action for event in stored.audit_events] == [
        "investigate",
        "investigate",
    ]
    assert {
        (event.state_before, event.state_after)
        for event in stored.audit_events
    } == {
        (ChallengeState.INITIAL, ChallengeState.EVIDENCE_READY),
        (ChallengeState.EVIDENCE_READY, ChallengeState.EVIDENCE_READY),
    }
    assert all(
        event.world_version_before == event.world_version_after == 7
        for event in stored.audit_events
    )


async def test_investigate_rejects_a_non_investigable_state_without_mutation() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)

    await repository.mutate_session(
        created.session_id,
        lambda session, now: session.model_copy(
            update={"state": ChallengeState.PREVIEW_READY}
        ),
    )

    with pytest.raises(ChallengeDomainError) as rejected:
        await service.investigate(
            created.session_id, InvestigateRequest(budget_cap_sc=300)
        )

    assert rejected.value.code is ChallengeErrorCode.INVALID_STATE_TRANSITION
    assert rejected.value.current_state is ChallengeState.PREVIEW_READY
    stored = await repository.load_session(created.session_id)
    assert stored is not None
    assert stored.state is ChallengeState.PREVIEW_READY
    assert stored.evidence is None
    assert stored.audit_events == []


def test_challenge_service_is_isolated_from_production_state_and_llm() -> None:
    source = inspect.getsource(service_module)
    forbidden = ("sqlalchemy", "app.database", "app.models", "app.services", "app.llm")
    assert all(token not in source for token in forbidden)
