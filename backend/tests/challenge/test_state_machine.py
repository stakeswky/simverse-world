from datetime import UTC, datetime, timedelta
import inspect

import pytest

import app.challenge.service as service_module
from app.challenge.errors import ChallengeDomainError, ChallengeErrorCode
from app.challenge.fixture import build_initial_world
from app.challenge.models import (
    ApproveRequest,
    ChallengeState,
    CommitRequest,
    InvestigateRequest,
    PreviewRequest,
    ResetRequest,
    VerifyRequest,
)
from app.challenge.canonical import diff_hash, world_hash
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


async def _committed_session(service: ChallengeService):
    created = await service.create_or_resume(None)
    await service.investigate(
        created.session_id, InvestigateRequest(budget_cap_sc=300)
    )
    previewed = await service.preview(
        created.session_id,
        PreviewRequest(crisis_id="harbor-wage-crisis", budget_cap_sc=300),
    )
    preview = previewed.projection.preview
    assert preview is not None
    approved = await service.approve(
        created.session_id,
        ApproveRequest(
            preview_id=preview.preview_id,
            expected_world_version=preview.based_on_world_version,
            diff_hash=preview.diff_hash,
        ),
    )
    assert approved.approval_id is not None
    committed = await service.commit(
        created.session_id,
        approved.approval_id,
        CommitRequest(
            preview_id=preview.preview_id,
            expected_world_version=preview.based_on_world_version,
            diff_hash=preview.diff_hash,
        ),
    )
    return created, committed


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


async def test_preview_transitions_rebuilds_hash_without_world_changes() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    investigated = await service.investigate(
        created.session_id, InvestigateRequest(budget_cap_sc=300)
    )
    before_hash = investigated.projection.world_hash

    first = await service.preview(
        created.session_id,
        PreviewRequest(crisis_id="harbor-wage-crisis", budget_cap_sc=300),
    )

    assert first.projection.state is ChallengeState.PREVIEW_READY
    assert first.projection.tool_surface == ["simverse_preview_intervention"]
    assert first.projection.preview is not None
    assert first.projection.preview.based_on_world_version == 7
    assert first.projection.preview.diff_hash == diff_hash(first.projection.preview.diff)
    assert first.projection.world_version == 7
    assert first.projection.world_hash == before_hash
    first_preview_id = first.projection.preview.preview_id
    first_diff_hash = first.projection.preview.diff_hash

    rebuilt = await service.preview(
        created.session_id,
        PreviewRequest(crisis_id="harbor-wage-crisis", budget_cap_sc=300),
    )

    assert rebuilt.projection.state is ChallengeState.PREVIEW_READY
    assert rebuilt.projection.preview is not None
    assert rebuilt.projection.preview.preview_id != first_preview_id
    assert rebuilt.projection.preview.diff_hash != first_diff_hash
    assert rebuilt.projection.preview.based_on_world_version == 7
    assert rebuilt.projection.world_hash == before_hash
    stored = await repository.load_session(created.session_id)
    assert stored is not None
    assert world_hash(stored.world) == before_hash
    assert [event.action for event in stored.audit_events].count("investigate") == 1
    assert [event.action for event in stored.audit_events].count("preview") == 2
    assert all(
        event.world_version_before == event.world_version_after == 7
        for event in stored.audit_events
    )


async def test_preview_rejects_stale_evidence_without_partial_mutation() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    await service.investigate(
        created.session_id, InvestigateRequest(budget_cap_sc=300)
    )
    await repository.mutate_session(
        created.session_id,
        lambda session, now: session.model_copy(
            update={
                "world": session.world.model_copy(
                    update={"world_version": session.world.world_version + 1},
                    deep=True,
                )
            }
        ),
    )

    with pytest.raises(ChallengeDomainError) as rejected:
        await service.preview(
            created.session_id,
            PreviewRequest(crisis_id="harbor-wage-crisis", budget_cap_sc=300),
        )

    assert rejected.value.code is ChallengeErrorCode.EVIDENCE_STALE
    assert rejected.value.status == 412
    stored = await repository.load_session(created.session_id)
    assert stored is not None
    assert stored.state is ChallengeState.EVIDENCE_READY
    assert stored.world.world_version == 8
    assert stored.preview is None
    assert [event.action for event in stored.audit_events] == ["investigate"]


async def test_verify_atomically_persists_v9_and_paired_timeline() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created, committed = await _committed_session(service)
    receipt = committed.projection.receipt
    assert receipt is not None

    verified = await service.verify(
        created.session_id,
        VerifyRequest(receipt_id=receipt.receipt_id, advance_hours=72),
    )

    assert verified.projection.state is ChallengeState.VERIFIED
    assert verified.projection.tool_surface == ["simverse_reset_town"]
    assert verified.projection.world_version == 9
    assert verified.projection.world_time == created.projection.world_time + timedelta(
        hours=72
    )
    verification = verified.projection.verification
    assert verification is not None
    assert verification.receipt_id == receipt.receipt_id
    assert verification.advance_hours == 72
    assert verification.baseline_snapshot.tick_index == 0
    assert verification.baseline_snapshot.elapsed_hours == 0
    assert [tick.tick_index for tick in verification.tick_snapshots] == list(
        range(1, 13)
    )
    assert [tick.elapsed_hours for tick in verification.tick_snapshots] == list(
        range(6, 73, 6)
    )
    stored = await repository.load_session(created.session_id)
    assert stored is not None
    assert stored.state is ChallengeState.VERIFIED
    assert stored.world.world_version == 9
    assert stored.verification == verification
    assert stored.initial_world_hash == receipt.world_before_hash
    assert world_hash(build_initial_world()) == receipt.world_before_hash
    verify_audit = next(
        event for event in stored.audit_events if event.action == "verify"
    )
    assert verify_audit.state_before is ChallengeState.COMMITTED
    assert verify_audit.state_after is ChallengeState.VERIFIED
    assert verify_audit.world_version_before == 8
    assert verify_audit.world_version_after == 9

    with pytest.raises(ChallengeDomainError) as replayed:
        await service.verify(
            created.session_id,
            VerifyRequest(receipt_id=receipt.receipt_id, advance_hours=72),
        )
    assert replayed.value.code is ChallengeErrorCode.OUTCOME_ALREADY_VERIFIED


async def test_verify_rejects_foreign_receipt_and_persists_failed_without_partial_v9() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created, committed = await _committed_session(service)
    receipt = committed.projection.receipt
    assert receipt is not None

    with pytest.raises(ChallengeDomainError) as rejected:
        await service.verify(
            created.session_id,
            VerifyRequest(receipt_id="receipt-from-another-session", advance_hours=72),
        )

    assert rejected.value.code is ChallengeErrorCode.OUTCOME_INCOMPLETE
    assert rejected.value.status == 500
    assert rejected.value.current_state is ChallengeState.FAILED
    stored = await repository.load_session(created.session_id)
    assert stored is not None
    assert stored.state is ChallengeState.FAILED
    assert stored.world.world_version == 8
    assert world_hash(stored.world) == receipt.world_after_hash
    assert stored.verification is None
    failed_audit = next(
        event for event in stored.audit_events if event.action == "verify_failed"
    )
    assert failed_audit.reason_code == "OUTCOME_INCOMPLETE"


async def test_verify_normalizes_engine_invariant_failure_and_allows_reset() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created, committed = await _committed_session(service)
    receipt = committed.projection.receipt
    assert receipt is not None
    await repository.mutate_session(
        created.session_id,
        lambda session, now: session.model_copy(
            update={
                "receipt": session.receipt.model_copy(
                    update={"world_before_hash": "sha256:" + "f" * 64}
                )
            },
            deep=True,
        ),
    )

    with pytest.raises(ChallengeDomainError) as rejected:
        await service.verify(
            created.session_id,
            VerifyRequest(receipt_id=receipt.receipt_id, advance_hours=72),
        )

    assert rejected.value.code is ChallengeErrorCode.OUTCOME_INCOMPLETE
    assert rejected.value.status == 500
    assert rejected.value.current_state is ChallengeState.FAILED
    stored = await repository.load_session(created.session_id)
    assert stored is not None
    assert stored.state is ChallengeState.FAILED
    assert stored.world.world_version == 8
    assert stored.verification is None
    failed_audit = next(
        event for event in stored.audit_events if event.action == "verify_failed"
    )
    assert failed_audit.reason_code == "OUTCOME_INCOMPLETE"
    reset = await service.reset(
        created.session_id,
        ResetRequest(expected_generation=stored.session_generation),
    )
    assert reset.projection.state is ChallengeState.INITIAL
    assert reset.projection.world_version == 7
    assert reset.projection.world_hash == world_hash(build_initial_world())


def test_challenge_service_is_isolated_from_production_state_and_llm() -> None:
    source = inspect.getsource(service_module)
    forbidden = ("sqlalchemy", "app.database", "app.models", "app.services", "app.llm")
    assert all(token not in source for token in forbidden)
