from datetime import UTC, datetime, timedelta

import pytest

from app.challenge.canonical import world_hash
from app.challenge.errors import ChallengeDomainError, ChallengeErrorCode
from app.challenge.fixture import build_initial_world
from app.challenge.models import (
    ApprovalRecord,
    ChallengeState,
    ExecutionReceipt,
    ResetRequest,
)
from app.challenge.repository import APPROVAL_PREFIX, SESSION_PREFIX, ChallengeRepository
from app.challenge.service import ChallengeService
from app.redis_client import get_redis

pytestmark = pytest.mark.anyio

NOW = datetime(2042, 6, 12, 8, tzinfo=UTC)
LOCKED_HASH = world_hash(build_initial_world())


def _receipt(generation: str) -> ExecutionReceipt:
    return ExecutionReceipt(
        receipt_id="receipt-old",
        scenario_id="harbor-wage-crisis-v1",
        session_generation=generation,
        preview_id="preview-old",
        approval_fingerprint="fingerprint-old",
        approved_diff_hash=LOCKED_HASH,
        world_before_version=7,
        world_after_version=8,
        world_before_hash=LOCKED_HASH,
        world_after_hash=LOCKED_HASH,
        budget_before_sc=300,
        budget_delta_sc=-300,
        budget_after_sc=0,
        affected_residents=[],
        created_events=[],
        verified_invariants=["budget_nonnegative"],
    )


@pytest.mark.parametrize("state", list(ChallengeState))
async def test_reset_is_legal_from_every_state(state: ChallengeState) -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    session = await repository.load_session(created.session_id)
    await repository.save_session(
        created.session_id, session.model_copy(update={"state": state})
    )

    reset = await service.reset(
        created.session_id,
        ResetRequest(expected_generation=session.session_generation),
    )
    assert reset.projection.state is ChallengeState.INITIAL
    assert reset.projection.world_version == 7
    assert reset.projection.world_hash == LOCKED_HASH
    assert reset.session_id != created.session_id
    assert reset.projection.session_generation != session.session_generation


async def test_reset_atomically_invalidates_old_generation_receipt_and_approval() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    session = await repository.load_session(created.session_id)
    approval = ApprovalRecord(
        approval_id="approval-old",
        session_generation=session.session_generation,
        preview_id="preview-old",
        diff_hash=LOCKED_HASH,
        world_version=7,
        status="CONSUMED",
        created_at=NOW,
        expires_at=NOW + timedelta(seconds=90),
    )
    old = session.model_copy(
        update={
            "state": ChallengeState.VERIFIED,
            "active_approval_id": approval.approval_id,
            "approval_fingerprint": "fingerprint-old",
            "approval_expires_at": approval.expires_at,
            "receipt": _receipt(session.session_generation),
        }
    )
    await repository.save_session(created.session_id, old)
    await repository.save_approval(approval)

    reset = await service.reset(
        created.session_id,
        ResetRequest(expected_generation=old.session_generation),
    )
    redis = get_redis()
    assert await redis.exists(f"{SESSION_PREFIX}{created.session_id}") == 0
    assert await redis.exists(f"{APPROVAL_PREFIX}{approval.approval_id}") == 0
    assert reset.projection.receipt is None
    assert reset.projection.approval_fingerprint is None
    assert reset.projection.session_generation != old.session_generation


async def test_reset_rejects_stale_generation_and_locked_hash_mismatch() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    session = await repository.load_session(created.session_id)

    with pytest.raises(ChallengeDomainError) as stale:
        await service.reset(
            created.session_id,
            ResetRequest(expected_generation="stale-generation"),
        )
    assert stale.value.code is ChallengeErrorCode.STALE_TOOL_SURFACE

    mismatched = session.model_copy(
        update={"initial_world_hash": "sha256:" + "f" * 64}
    )
    await repository.save_session(created.session_id, mismatched)
    with pytest.raises(ChallengeDomainError) as mismatch:
        await service.reset(
            created.session_id,
            ResetRequest(expected_generation=session.session_generation),
        )
    assert mismatch.value.code is ChallengeErrorCode.RESET_HASH_MISMATCH
    assert await repository.load_session(created.session_id) is not None


async def test_ten_consecutive_resets_restore_the_identical_fixture_hash() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    result = await service.create_or_resume(None)
    hashes: list[str] = []

    for _ in range(10):
        result = await service.reset(
            result.session_id,
            ResetRequest(expected_generation=result.projection.session_generation),
        )
        hashes.append(result.projection.world_hash)

    assert hashes == [LOCKED_HASH] * 10
