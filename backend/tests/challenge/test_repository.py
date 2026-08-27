from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from redis.exceptions import WatchError

from app.challenge.canonical import canonical_json, diff_hash, world_hash
from app.challenge.errors import (
    ERROR_STATUS_BY_CODE,
    ChallengeDomainError,
    ChallengeErrorCode,
)
from app.challenge.fixture import build_initial_world
from app.challenge.models import (
    ApprovalRecord,
    ChallengeSession,
    ChallengeState,
    ExecutionReceipt,
    ForecastResult,
    InterventionPreview,
    MetricRange,
    NoActionOutcome,
    OutcomeMetrics,
    TickSnapshot,
    VerificationResult,
    WorldDiff,
)
from app.challenge.repository import (
    ABSOLUTE_TTL_SECONDS,
    APPROVAL_PREFIX,
    APPROVAL_TTL_SECONDS,
    IDLE_TTL_SECONDS,
    MAX_WATCH_RETRIES,
    SESSION_PREFIX,
    ChallengeRepository,
)
from app.redis_client import get_redis

pytestmark = pytest.mark.anyio

NOW = datetime(2042, 6, 12, 8, tzinfo=UTC)


def _clock() -> tuple[dict[str, datetime], Callable[[], datetime]]:
    current = {"now": NOW}
    return current, lambda: current["now"]


def _forecast() -> ForecastResult:
    return ForecastResult(
        seeds=[1],
        high_food_risk_residents=MetricRange(min=0, max=1),
        social_tension=MetricRange(min=30, max=40),
        strike_risk_pct=MetricRange(min=10, max=20),
        stabilized_residents=MetricRange(min=5, max=6),
    )


def _preview(now: datetime) -> InterventionPreview:
    diff = WorldDiff(
        scenario_id="harbor-wage-crisis-v1",
        session_generation="generation-01",
        preview_id="preview-01",
        based_on_world_version=7,
        budget_before_sc=300,
        budget_after_sc=0,
        resident_cash_changes=[],
        food_credit_changes=[],
        employer_claims_created=[],
        events_created=[],
        explicitly_unchanged=["harbor_open"],
    )
    return InterventionPreview(
        preview_id="preview-01",
        crisis_id="harbor-wage-crisis",
        based_on_world_version=7,
        intervention_id="harbor-wage-bridge",
        total_cost_sc=300,
        remaining_budget_sc=0,
        diff=diff,
        diff_hash=diff_hash(diff),
        forecast=_forecast(),
        rejected_alternatives=[],
        created_at=now,
    )


def _receipt(now: datetime) -> ExecutionReceipt:
    locked_hash = world_hash(build_initial_world())
    return ExecutionReceipt(
        receipt_id="receipt-01",
        scenario_id="harbor-wage-crisis-v1",
        session_generation="generation-01",
        preview_id="preview-01",
        approval_fingerprint="fingerprint-01",
        approved_diff_hash=_preview(now).diff_hash,
        world_before_version=7,
        world_after_version=8,
        world_before_hash=locked_hash,
        world_after_hash=locked_hash,
        budget_before_sc=300,
        budget_delta_sc=-300,
        budget_after_sc=0,
        affected_residents=[],
        created_events=[],
        verified_invariants=["budget_nonnegative"],
    )


def _verification(now: datetime) -> VerificationResult:
    metrics = OutcomeMetrics(
        high_food_risk_residents=0,
        social_tension=30,
        strike_risk_pct=10,
        stabilized_residents=6,
    )
    baseline = TickSnapshot(
        tick_index=0,
        elapsed_hours=0,
        world_time=now,
        metrics=metrics,
        external_event_ids=[],
    )
    ticks = [
        TickSnapshot(
            tick_index=index,
            elapsed_hours=index * 6,
            world_time=now + timedelta(hours=index * 6),
            metrics=metrics,
            external_event_ids=[],
        )
        for index in range(1, 13)
    ]
    return VerificationResult(
        receipt_id="receipt-01",
        advance_hours=72,
        baseline_snapshot=baseline,
        tick_snapshots=ticks,
        forecast=_forecast(),
        actual=metrics,
        no_action=NoActionOutcome(
            **metrics.model_dump(), strike_event_triggered=True
        ),
        notable_deviation="none",
    )


def _session(
    now: datetime,
    *,
    generation: str = "generation-01",
    active_approval_id: str | None = None,
    populated: bool = False,
) -> ChallengeSession:
    world = build_initial_world()
    return ChallengeSession(
        session_generation=generation,
        scenario_id="harbor-wage-crisis-v1",
        fixture_version=1,
        state=ChallengeState.VERIFIED if populated else ChallengeState.INITIAL,
        created_at=now,
        idle_expires_at=now + timedelta(seconds=IDLE_TTL_SECONDS),
        absolute_expires_at=now + timedelta(seconds=ABSOLUTE_TTL_SECONDS),
        csrf_token="csrf-01",
        initial_world_hash=world_hash(world),
        world=world,
        evidence=None,
        preview=_preview(now) if populated else None,
        active_approval_id=active_approval_id,
        approval_fingerprint="fingerprint-01" if active_approval_id else None,
        approval_expires_at=(
            now + timedelta(seconds=APPROVAL_TTL_SECONDS)
            if active_approval_id
            else None
        ),
        receipt=_receipt(now) if populated else None,
        verification=_verification(now) if populated else None,
        audit_events=[],
    )


def _approval(now: datetime, *, status: str = "APPROVED_ONCE") -> ApprovalRecord:
    preview = _preview(now)
    return ApprovalRecord(
        approval_id="approval-01",
        session_generation="generation-01",
        preview_id=preview.preview_id,
        diff_hash=preview.diff_hash,
        world_version=7,
        status=status,
        created_at=now,
        expires_at=now + timedelta(seconds=APPROVAL_TTL_SECONDS),
    )


EXPECTED_STATUS = {
    ChallengeErrorCode.INVALID_INPUT: 422,
    ChallengeErrorCode.CHALLENGE_SESSION_NOT_READY: 409,
    ChallengeErrorCode.CHALLENGE_SESSION_EXPIRED: 410,
    ChallengeErrorCode.INVALID_STATE_TRANSITION: 409,
    ChallengeErrorCode.NO_ACTIONABLE_CRISIS: 409,
    ChallengeErrorCode.EVIDENCE_STALE: 412,
    ChallengeErrorCode.BUDGET_EXCEEDED: 422,
    ChallengeErrorCode.POLICY_VIOLATION: 422,
    ChallengeErrorCode.PREVIEW_NOT_FOUND: 404,
    ChallengeErrorCode.PREVIEW_STALE: 412,
    ChallengeErrorCode.APPROVAL_REQUIRED: 403,
    ChallengeErrorCode.APPROVAL_MISMATCH: 403,
    ChallengeErrorCode.APPROVAL_EXPIRED: 410,
    ChallengeErrorCode.APPROVAL_REVOKED: 403,
    ChallengeErrorCode.APPROVAL_REPLAYED: 409,
    ChallengeErrorCode.STALE_WORLD_VERSION: 412,
    ChallengeErrorCode.STALE_TOOL_SURFACE: 409,
    ChallengeErrorCode.OUTCOME_ALREADY_VERIFIED: 409,
    ChallengeErrorCode.OUTCOME_INCOMPLETE: 500,
    ChallengeErrorCode.RESET_HASH_MISMATCH: 500,
    ChallengeErrorCode.CHALLENGE_INTERNAL_ERROR: 500,
}


def test_error_code_status_contract_is_exact() -> None:
    assert set(ChallengeErrorCode) == set(EXPECTED_STATUS)
    assert ERROR_STATUS_BY_CODE == EXPECTED_STATUS


def test_domain_error_payload_is_stable_and_does_not_serialize_causes() -> None:
    error = ChallengeDomainError(
        ChallengeErrorCode.PREVIEW_STALE,
        status=412,
        message="Preview no longer matches the world.",
        retryable=True,
        current_state=ChallengeState.EVIDENCE_READY,
        next_action="preview",
    )

    assert error.to_payload() == {
        "error": {
            "code": "PREVIEW_STALE",
            "message": "Preview no longer matches the world.",
            "retryable": True,
            "current_state": "EVIDENCE_READY",
            "next_action": "preview",
        }
    }
    assert vars(error).keys() >= {
        "code", "status", "message", "retryable", "current_state", "next_action"
    }


def test_repository_constants_and_key_prefixes_are_locked() -> None:
    assert SESSION_PREFIX == "sv:challenge:session:"
    assert APPROVAL_PREFIX == "sv:challenge:approval:"
    assert IDLE_TTL_SECONDS == 15 * 60
    assert ABSOLUTE_TTL_SECONDS == 20 * 60
    assert APPROVAL_TTL_SECONDS == 90
    assert MAX_WATCH_RETRIES == 4


async def test_create_load_save_and_absolute_redis_ttl() -> None:
    current, clock = _clock()
    repository = ChallengeRepository(clock=clock)
    redis = get_redis()
    session = _session(current["now"])

    await repository.create_session("session-01", session)
    assert await redis.exists(f"{SESSION_PREFIX}session-01") == 1
    assert 1199 <= await redis.ttl(f"{SESSION_PREFIX}session-01") <= 1200
    assert await repository.load_session("session-01") == session

    changed = session.model_copy(
        update={"world": session.world.model_copy(update={"budget_sc": 299})}
    )
    await repository.save_session("session-01", changed)
    assert (await repository.load_session("session-01")).world.budget_sc == 299


async def test_valid_mutation_refreshes_idle_without_crossing_absolute() -> None:
    current, clock = _clock()
    repository = ChallengeRepository(clock=clock)
    session = _session(current["now"])
    await repository.create_session("session-01", session)
    current["now"] += timedelta(minutes=10)

    calls: list[datetime] = []

    def mutate(value: ChallengeSession, now: datetime) -> ChallengeSession:
        calls.append(now)
        return value.model_copy(
            update={"world": value.world.model_copy(update={"budget_sc": 298})}
        )

    updated = await repository.mutate_session("session-01", mutate)
    assert calls == [current["now"]]
    assert updated.idle_expires_at == updated.absolute_expires_at
    assert updated.world.budget_sc == 298


async def test_idle_expiry_writes_minimal_session_and_approval_tombstones() -> None:
    current, clock = _clock()
    repository = ChallengeRepository(clock=clock)
    session = _session(
        current["now"], active_approval_id="approval-01", populated=True
    )
    await repository.create_session("session-01", session)
    await repository.save_approval(_approval(current["now"]))
    current["now"] += timedelta(seconds=IDLE_TTL_SECONDS + 1)

    expired = await repository.load_session("session-01")
    assert expired is not None
    assert expired.state is ChallengeState.EXPIRED
    assert expired.preview is None
    assert expired.receipt is None
    assert expired.verification is None
    approval = await repository.load_approval("approval-01")
    assert approval is not None
    assert approval.status == "EXPIRED"
    assert await get_redis().ttl(f"{APPROVAL_PREFIX}approval-01") > 0


async def test_absolute_expiry_deletes_session_and_active_approval() -> None:
    current, clock = _clock()
    repository = ChallengeRepository(clock=clock)
    session = _session(current["now"], active_approval_id="approval-01")
    await repository.create_session("session-01", session)
    await repository.save_approval(_approval(current["now"]))
    current["now"] += timedelta(seconds=ABSOLUTE_TTL_SECONDS + 1)

    assert await repository.load_session("session-01") is None
    assert await get_redis().exists(f"{SESSION_PREFIX}session-01") == 0
    assert await get_redis().exists(f"{APPROVAL_PREFIX}approval-01") == 0


async def test_approval_is_logically_expired_after_ninety_seconds_but_retained() -> None:
    current, clock = _clock()
    repository = ChallengeRepository(clock=clock)
    await repository.save_approval(_approval(current["now"]))
    assert (await repository.load_approval("approval-01")).status == "APPROVED_ONCE"

    current["now"] += timedelta(seconds=APPROVAL_TTL_SECONDS + 1)
    expired = await repository.load_approval("approval-01")
    assert expired is not None
    assert expired.status == "EXPIRED"
    assert await get_redis().ttl(f"{APPROVAL_PREFIX}approval-01") > 0


async def test_corrupt_json_fails_closed_and_is_removed() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    redis = get_redis()
    await redis.set(f"{SESSION_PREFIX}broken", "{not-json")
    await redis.set(f"{APPROVAL_PREFIX}broken", "[]")

    assert await repository.load_session("broken") is None
    assert await repository.load_approval("broken") is None
    assert await redis.exists(f"{SESSION_PREFIX}broken") == 0
    assert await redis.exists(f"{APPROVAL_PREFIX}broken") == 0


async def test_explicit_and_active_approval_mutations_are_atomic() -> None:
    current, clock = _clock()
    repository = ChallengeRepository(clock=clock)
    session = _session(current["now"], active_approval_id="approval-01")
    approval = _approval(current["now"])
    await repository.create_session("session-01", session)
    await repository.save_approval(approval)

    committed = await repository.mutate_session_and_approval(
        "session-01",
        "approval-01",
        lambda value, capability, now: (
            value.model_copy(update={"state": ChallengeState.COMMITTED}),
            capability.model_copy(update={"status": "CONSUMED"}),
        ),
    )
    assert committed.state is ChallengeState.COMMITTED
    assert (await repository.load_approval("approval-01")).status == "CONSUMED"

    revoked = await repository.mutate_session_with_active_approval(
        "session-01",
        lambda value, capability, now: (
            value.model_copy(update={"state": ChallengeState.FAILED}),
            capability.model_copy(update={"status": "REVOKED"}),
        ),
    )
    assert revoked.state is ChallengeState.FAILED
    assert (await repository.load_approval("approval-01")).status == "REVOKED"


async def test_idle_detected_by_mutation_persists_both_tombstones() -> None:
    current, clock = _clock()
    repository = ChallengeRepository(clock=clock)
    session = _session(current["now"], active_approval_id="approval-01")
    await repository.create_session("session-01", session)
    await repository.save_approval(_approval(current["now"]))
    current["now"] += timedelta(seconds=IDLE_TTL_SECONDS + 1)
    callback_called = False

    def should_not_run(
        value: ChallengeSession, capability: ApprovalRecord, now: datetime
    ) -> tuple[ChallengeSession, ApprovalRecord]:
        nonlocal callback_called
        callback_called = True
        return value, capability

    with pytest.raises(ChallengeDomainError) as expired:
        await repository.mutate_session_and_approval(
            "session-01", "approval-01", should_not_run
        )
    assert expired.value.code is ChallengeErrorCode.CHALLENGE_SESSION_EXPIRED
    assert callback_called is False
    assert (await repository.load_session("session-01")).state is ChallengeState.EXPIRED
    assert (await repository.load_approval("approval-01")).status == "EXPIRED"


class _RetryPipeline:
    def __init__(self, inner, owner: "_RetryRedis") -> None:
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
        should_conflict = self._owner.always_conflict or self._owner.execute_calls == 1
        if not should_conflict:
            return await self._inner.execute()
        await self._inner.reset()
        if self._owner.replacement_json is not None and self._owner.execute_calls == 1:
            await self._owner.real.set(
                self._owner.session_key,
                self._owner.replacement_json,
                ex=ABSOLUTE_TTL_SECONDS,
            )
        raise WatchError("injected conflict")


class _RetryRedis:
    def __init__(
        self,
        real,
        *,
        session_key: str,
        replacement_json: str | None,
        always_conflict: bool = False,
    ) -> None:
        self.real = real
        self.session_key = session_key
        self.replacement_json = replacement_json
        self.always_conflict = always_conflict
        self.execute_calls = 0

    def pipeline(self, transaction: bool = True):
        return _RetryPipeline(self.real.pipeline(transaction=transaction), self)

    def __getattr__(self, name: str):
        return getattr(self.real, name)


async def test_watch_retry_rereads_state_and_reinvokes_mutator() -> None:
    real = get_redis()
    initial = _session(NOW)
    await ChallengeRepository(real, lambda: NOW).create_session("session-01", initial)
    replacement = initial.model_copy(
        update={"world": initial.world.model_copy(update={"budget_sc": 250})}
    )
    wrapped = _RetryRedis(
        real,
        session_key=f"{SESSION_PREFIX}session-01",
        replacement_json=canonical_json(replacement),
    )
    repository = ChallengeRepository(wrapped, lambda: NOW)
    seen_budgets: list[int] = []

    def mutate(value: ChallengeSession, now: datetime) -> ChallengeSession:
        seen_budgets.append(value.world.budget_sc)
        return value.model_copy(
            update={
                "world": value.world.model_copy(
                    update={"budget_sc": value.world.budget_sc - 1}
                )
            }
        )

    result = await repository.mutate_session("session-01", mutate)
    assert seen_budgets == [300, 250]
    assert result.world.budget_sc == 249
    assert (await ChallengeRepository(real, lambda: NOW).load_session("session-01")).world.budget_sc == 249


async def test_four_watch_conflicts_return_stable_stale_world_error() -> None:
    real = get_redis()
    await ChallengeRepository(real, lambda: NOW).create_session(
        "session-01", _session(NOW)
    )
    wrapped = _RetryRedis(
        real,
        session_key=f"{SESSION_PREFIX}session-01",
        replacement_json=None,
        always_conflict=True,
    )
    repository = ChallengeRepository(wrapped, lambda: NOW)
    calls = 0

    def mutate(value: ChallengeSession, now: datetime) -> ChallengeSession:
        nonlocal calls
        calls += 1
        return value

    with pytest.raises(ChallengeDomainError) as stale:
        await repository.mutate_session("session-01", mutate)
    assert stale.value.code is ChallengeErrorCode.STALE_WORLD_VERSION
    assert calls == MAX_WATCH_RETRIES
    assert wrapped.execute_calls == MAX_WATCH_RETRIES


async def test_replace_session_checks_generation_and_deletes_old_capability() -> None:
    current, clock = _clock()
    repository = ChallengeRepository(clock=clock)
    old = _session(current["now"], active_approval_id="approval-01")
    new = _session(current["now"], generation="generation-02")
    await repository.create_session("old-session", old)
    await repository.save_approval(_approval(current["now"]))

    with pytest.raises(ChallengeDomainError) as mismatch:
        await repository.replace_session(
            "old-session", "wrong-generation", "new-session", new
        )
    assert mismatch.value.code is ChallengeErrorCode.STALE_TOOL_SURFACE
    assert await repository.load_session("old-session") is not None

    await repository.replace_session(
        "old-session", "generation-01", "new-session", new
    )
    assert await repository.load_session("old-session") is None
    assert await repository.load_approval("approval-01") is None
    assert (await repository.load_session("new-session")).session_generation == "generation-02"
