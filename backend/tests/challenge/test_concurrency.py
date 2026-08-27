import asyncio
from datetime import UTC, datetime

import pytest

from app.challenge.engine import commit_world
from app.challenge.errors import ChallengeDomainError, ChallengeErrorCode
from app.challenge.fixture import build_initial_world
from app.challenge.models import (
    ApprovalRecord,
    ApproveRequest,
    ChallengeSession,
    ChallengeState,
    InvestigateRequest,
    PreviewRequest,
)
from app.challenge.repository import ChallengeRepository
from app.challenge.service import ChallengeService
from app.redis_client import get_redis

pytestmark = pytest.mark.anyio

NOW = datetime(2042, 6, 12, 8, tzinfo=UTC)


class _BarrierPipeline:
    def __init__(self, inner, owner: "_BarrierRedis") -> None:
        self._inner = inner
        self._owner = owner

    async def __aenter__(self):
        await self._inner.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return await self._inner.__aexit__(exc_type, exc, traceback)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    async def execute(self):
        self._owner.execute_calls += 1
        if self._owner.execute_calls <= 2:
            self._owner.arrivals += 1
            if self._owner.arrivals == 2:
                self._owner.release.set()
            await self._owner.release.wait()
        return await self._inner.execute()


class _BarrierRedis:
    def __init__(self, real) -> None:
        self.real = real
        self.arrivals = 0
        self.execute_calls = 0
        self.release = asyncio.Event()

    def pipeline(self, transaction: bool = True):
        return _BarrierPipeline(
            self.real.pipeline(transaction=transaction),
            self,
        )

    def __getattr__(self, name: str):
        return getattr(self.real, name)


def _replay_error(state: ChallengeState) -> ChallengeDomainError:
    return ChallengeDomainError(
        ChallengeErrorCode.APPROVAL_REPLAYED,
        status=409,
        message="Approval has already been consumed.",
        retryable=False,
        current_state=state,
        next_action="verify",
    )


def _commit_mutator(
    session: ChallengeSession,
    approval: ApprovalRecord,
    now: datetime,
) -> tuple[ChallengeSession, ApprovalRecord]:
    if (
        session.state is not ChallengeState.APPROVED_ONCE
        or approval.status != "APPROVED_ONCE"
        or session.preview is None
        or session.approval_fingerprint is None
    ):
        raise _replay_error(session.state)
    committed, receipt = commit_world(
        session.world,
        session.preview.diff,
        session.approval_fingerprint,
    )
    return (
        session.model_copy(
            update={
                "state": ChallengeState.COMMITTED,
                "world": committed,
                "receipt": receipt,
            },
            deep=True,
        ),
        approval.model_copy(update={"status": "CONSUMED"}),
    )


async def _approved_session(repository: ChallengeRepository):
    service = ChallengeService(repository=repository, clock=lambda: NOW)
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
            expected_world_version=7,
            diff_hash=preview.diff_hash,
        ),
    )
    assert approved.approval_id is not None
    return created.session_id, approved.approval_id


async def _commit(repository, session_id: str, approval_id: str):
    return await repository.mutate_session_and_approval(
        session_id,
        approval_id,
        _commit_mutator,
    )


async def test_two_concurrent_commits_consume_approval_once() -> None:
    base = ChallengeRepository(clock=lambda: NOW)
    session_id, approval_id = await _approved_session(base)
    barrier = _BarrierRedis(get_redis())
    first = ChallengeRepository(barrier, lambda: NOW)
    second = ChallengeRepository(barrier, lambda: NOW)

    results = await asyncio.gather(
        _commit(first, session_id, approval_id),
        _commit(second, session_id, approval_id),
        return_exceptions=True,
    )

    successes = [result for result in results if isinstance(result, ChallengeSession)]
    failures = [result for result in results if isinstance(result, ChallengeDomainError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].code is ChallengeErrorCode.APPROVAL_REPLAYED
    stored = await base.load_session(session_id)
    approval = await base.load_approval(approval_id)
    assert stored is not None and approval is not None
    assert stored.state is ChallengeState.COMMITTED
    assert stored.world.budget_sc == 60
    assert sum(
        event.event_id == "employer-escrow-mediation"
        for event in stored.world.events
    ) == 1
    assert stored.receipt is not None
    assert approval.status == "CONSUMED"


@pytest.mark.parametrize("competitor", ["revoke", "reset"])
async def test_commit_racing_revoke_or_reset_has_one_winner(
    competitor: str,
) -> None:
    base = ChallengeRepository(clock=lambda: NOW)
    session_id, approval_id = await _approved_session(base)
    original = await base.load_session(session_id)
    assert original is not None
    barrier = _BarrierRedis(get_redis())
    commit_repository = ChallengeRepository(barrier, lambda: NOW)
    competing_repository = ChallengeRepository(barrier, lambda: NOW)

    if competitor == "revoke":
        def revoke_mutator(session, approval, now):
            if (
                session.state is not ChallengeState.APPROVED_ONCE
                or approval is None
                or approval.status != "APPROVED_ONCE"
            ):
                raise _replay_error(session.state)
            return (
                session.model_copy(
                    update={
                        "state": ChallengeState.PREVIEW_READY,
                        "active_approval_id": None,
                        "approval_fingerprint": None,
                        "approval_expires_at": None,
                    }
                ),
                approval.model_copy(update={"status": "REVOKED"}),
            )

        competing = competing_repository.mutate_session_with_active_approval(
            session_id,
            revoke_mutator,
        )
    else:
        replacement_world = build_initial_world()
        replacement = original.model_copy(
            update={
                "session_generation": "generation-reset",
                "state": ChallengeState.INITIAL,
                "world": replacement_world,
                "evidence": None,
                "preview": None,
                "active_approval_id": None,
                "approval_fingerprint": None,
                "approval_expires_at": None,
                "receipt": None,
                "verification": None,
                "audit_events": [],
            },
            deep=True,
        )
        competing = competing_repository.replace_session(
            session_id,
            original.session_generation,
            "session-reset",
            replacement,
        )

    results = await asyncio.gather(
        _commit(commit_repository, session_id, approval_id),
        competing,
        return_exceptions=True,
    )

    successes = [result for result in results if not isinstance(result, Exception)]
    failures = [result for result in results if isinstance(result, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
