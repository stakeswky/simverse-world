from __future__ import annotations

import asyncio
import ipaddress
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse, urlunparse
from uuid import uuid4

import pytest
import redis.asyncio as aioredis
from redis.exceptions import WatchError

from app.challenge.canonical import canonical_json
from app.challenge.errors import ChallengeDomainError, ChallengeErrorCode
from app.challenge.models import (
    ApproveRequest,
    ChallengeSession,
    ChallengeState,
    CommitRequest,
    InvestigateRequest,
    PreviewRequest,
    ResetRequest,
)
from app.challenge.repository import (
    APPROVAL_PREFIX,
    SESSION_PREFIX,
    ChallengeRepository,
)
from app.challenge.service import ChallengeService
from app.redis_client import set_redis

NOW = datetime(2042, 6, 12, 8, tzinfo=UTC)


@dataclass
class _RealRedisCase:
    url: str
    client: aioredis.Redis
    control_client: aioredis.Redis
    db15_size_before: int
    db0_size_before: int
    challenge_keys_before: set[str]
    keys: set[str] = field(default_factory=set)

    def track_session(self, session_id: str) -> None:
        self.keys.add(f"{SESSION_PREFIX}{session_id}")

    def track_approval(self, approval_id: str) -> None:
        self.keys.add(f"{APPROVAL_PREFIX}{approval_id}")


def _is_loopback(hostname: str | None) -> bool:
    if hostname == "localhost":
        return True
    if hostname is None:
        return False
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _url_for_database(url: str, database: int) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{database}", query=""))


async def _challenge_keys(client: aioredis.Redis) -> set[str]:
    found: set[str] = set()
    for pattern in (f"{SESSION_PREFIX}*", f"{APPROVAL_PREFIX}*"):
        async for key in client.scan_iter(match=pattern):
            found.add(key)
    return found


@pytest.fixture
async def real_redis_case() -> _RealRedisCase:
    url = os.environ.get("CHALLENGE_REAL_REDIS_URL")
    if url is None:
        pytest.skip("CHALLENGE_REAL_REDIS_URL is not set")
    parsed = urlparse(url)
    if not _is_loopback(parsed.hostname):
        pytest.fail("CHALLENGE_REAL_REDIS_URL must use a loopback Redis host")
    query_databases = parse_qs(parsed.query).get("db", [])
    if query_databases:
        pytest.fail("CHALLENGE_REAL_REDIS_URL must select database 15 by URL path only")
    try:
        database = int(parsed.path.removeprefix("/"))
    except ValueError:
        pytest.fail("CHALLENGE_REAL_REDIS_URL must select Redis database 15")
    if database != 15:
        pytest.fail("CHALLENGE_REAL_REDIS_URL must select isolated Redis database 15")

    client = aioredis.from_url(url, decode_responses=True)
    actual_database = int(client.connection_pool.connection_kwargs.get("db", -1))
    if actual_database != 15:
        pytest.fail("Redis client resolved to a database other than 15")
    control_client = aioredis.from_url(
        _url_for_database(url, 0),
        decode_responses=True,
    )
    await client.ping()
    await control_client.ping()
    set_redis(client)
    case = _RealRedisCase(
        url=url,
        client=client,
        control_client=control_client,
        db15_size_before=await client.dbsize(),
        db0_size_before=await control_client.dbsize(),
        challenge_keys_before=await _challenge_keys(client),
    )
    try:
        yield case
    finally:
        challenge_keys_before_cleanup = await _challenge_keys(client)
        unexpected = (
            challenge_keys_before_cleanup
            - case.challenge_keys_before
            - case.keys
        )
        if case.keys:
            await client.delete(*sorted(case.keys))
        challenge_keys_after = await _challenge_keys(client)
        db15_size_after = await client.dbsize()
        db0_size_after = await control_client.dbsize()
        set_redis(None)
        await client.aclose()
        await control_client.aclose()
        assert unexpected == set()
        assert challenge_keys_after == case.challenge_keys_before
        assert db15_size_after == case.db15_size_before
        assert db0_size_after == case.db0_size_before


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
        try:
            return await self._inner.execute()
        except WatchError:
            self._owner.watch_errors.append("WatchError")
            raise


class _BarrierRedis:
    def __init__(self, real: aioredis.Redis) -> None:
        self.real = real
        self.arrivals = 0
        self.execute_calls = 0
        self.release = asyncio.Event()
        self.watch_errors: list[str] = []

    def pipeline(self, transaction: bool = True):
        return _BarrierPipeline(
            self.real.pipeline(transaction=transaction),
            self,
        )

    def __getattr__(self, name: str):
        return getattr(self.real, name)


class _ConflictOncePipeline:
    def __init__(self, inner, owner: "_ConflictOnceRedis") -> None:
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
        if not self._owner.conflict_written:
            self._owner.conflict_written = True
            raw = await self._owner.writer.get(self._owner.session_key)
            assert raw is not None
            session = ChallengeSession.model_validate_json(raw)
            replacement = session.model_copy(
                update={
                    "world": session.world.model_copy(update={"budget_sc": 250})
                },
                deep=True,
            )
            ttl = await self._owner.writer.ttl(self._owner.session_key)
            await self._owner.writer.set(
                self._owner.session_key,
                canonical_json(replacement),
                ex=max(1, ttl),
            )
        try:
            return await self._inner.execute()
        except WatchError:
            self._owner.watch_errors.append("WatchError")
            raise


class _ConflictOnceRedis:
    def __init__(
        self,
        real: aioredis.Redis,
        writer: aioredis.Redis,
        session_key: str,
    ) -> None:
        self.real = real
        self.writer = writer
        self.session_key = session_key
        self.execute_calls = 0
        self.conflict_written = False
        self.watch_errors: list[str] = []

    def pipeline(self, transaction: bool = True):
        return _ConflictOncePipeline(
            self.real.pipeline(transaction=transaction),
            self,
        )

    def __getattr__(self, name: str):
        return getattr(self.real, name)


async def _approved_session(
    case: _RealRedisCase,
) -> tuple[ChallengeRepository, str, str, CommitRequest]:
    repository = ChallengeRepository(case.client, lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    session_id = f"real-{uuid4().hex}"
    case.track_session(session_id)
    await repository.create_session(session_id, service._new_session(NOW))
    await service.investigate(
        session_id,
        InvestigateRequest(budget_cap_sc=300),
    )
    previewed = await service.preview(
        session_id,
        PreviewRequest(crisis_id="harbor-wage-crisis", budget_cap_sc=300),
    )
    preview = previewed.projection.preview
    assert preview is not None
    approved = await service.approve(
        session_id,
        ApproveRequest(
            preview_id=preview.preview_id,
            expected_world_version=preview.based_on_world_version,
            diff_hash=preview.diff_hash,
        ),
    )
    assert approved.approval_id is not None
    case.track_approval(approved.approval_id)
    return (
        repository,
        session_id,
        approved.approval_id,
        CommitRequest(
            preview_id=preview.preview_id,
            expected_world_version=preview.based_on_world_version,
            diff_hash=preview.diff_hash,
        ),
    )


def _assert_single_commit(session: ChallengeSession) -> None:
    assert session.state is ChallengeState.COMMITTED
    assert session.world.world_version == 8
    assert session.world.budget_sc == 60
    assert session.receipt is not None
    assert session.receipt.world_before_version == 7
    assert session.receipt.world_after_version == 8
    assert session.receipt.budget_before_sc == 300
    assert session.receipt.budget_delta_sc == -240
    assert session.receipt.budget_after_sc == 60
    assert sum(event.action == "commit" for event in session.audit_events) == 1
    assert sum(
        event.event_id == "employer-escrow-mediation"
        for event in session.world.events
    ) == 1
    assert session.world.scenario_id == "harbor-wage-crisis-v1"
    assert all(
        resident.resident_id.startswith("harbor-resident-")
        for resident in session.world.residents
    )


async def test_real_redis_two_concurrent_commits_consume_approval_once(
    real_redis_case: _RealRedisCase,
) -> None:
    base, session_id, approval_id, request = await _approved_session(real_redis_case)
    barrier = _BarrierRedis(real_redis_case.client)
    first = ChallengeService(
        repository=ChallengeRepository(barrier, lambda: NOW),
        clock=lambda: NOW,
    )
    second = ChallengeService(
        repository=ChallengeRepository(barrier, lambda: NOW),
        clock=lambda: NOW,
    )

    results = await asyncio.gather(
        first.commit(session_id, approval_id, request),
        second.commit(session_id, approval_id, request),
        return_exceptions=True,
    )

    successes = [result for result in results if not isinstance(result, Exception)]
    failures = [
        result for result in results if isinstance(result, ChallengeDomainError)
    ]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].code is ChallengeErrorCode.APPROVAL_REPLAYED
    assert 1 <= len(barrier.watch_errors) <= 4
    assert set(barrier.watch_errors) == {"WatchError"}
    stored = await base.load_session(session_id)
    approval = await base.load_approval(approval_id)
    assert stored is not None and approval is not None
    _assert_single_commit(stored)
    assert approval.status == "CONSUMED"


async def test_real_redis_commit_racing_revoke_has_one_winner(
    real_redis_case: _RealRedisCase,
) -> None:
    base, session_id, approval_id, request = await _approved_session(real_redis_case)
    barrier = _BarrierRedis(real_redis_case.client)
    commit_service = ChallengeService(
        repository=ChallengeRepository(barrier, lambda: NOW),
        clock=lambda: NOW,
    )
    revoke_service = ChallengeService(
        repository=ChallengeRepository(barrier, lambda: NOW),
        clock=lambda: NOW,
    )

    results = await asyncio.gather(
        commit_service.commit(session_id, approval_id, request),
        revoke_service.revoke(session_id),
        return_exceptions=True,
    )

    successes = [result for result in results if not isinstance(result, Exception)]
    failures = [
        result for result in results if isinstance(result, ChallengeDomainError)
    ]
    assert len(successes) == 1
    assert len(failures) == 1
    stored = await base.load_session(session_id)
    approval = await base.load_approval(approval_id)
    assert stored is not None and approval is not None
    if stored.state is ChallengeState.COMMITTED:
        _assert_single_commit(stored)
        assert approval.status == "CONSUMED"
        expected_loser = ChallengeErrorCode.INVALID_STATE_TRANSITION
        expected_replay = ChallengeErrorCode.APPROVAL_REPLAYED
    else:
        assert stored.state is ChallengeState.PREVIEW_READY
        assert stored.world.world_version == 7
        assert stored.world.budget_sc == 300
        assert stored.receipt is None
        assert sum(event.action == "commit" for event in stored.audit_events) == 0
        assert approval.status == "REVOKED"
        expected_loser = ChallengeErrorCode.APPROVAL_REQUIRED
        expected_replay = ChallengeErrorCode.APPROVAL_REQUIRED
    assert failures[0].code is expected_loser
    assert 1 <= len(barrier.watch_errors) <= 4
    assert set(barrier.watch_errors) == {"WatchError"}

    with pytest.raises(ChallengeDomainError) as replay:
        await ChallengeService(repository=base, clock=lambda: NOW).commit(
            session_id,
            approval_id,
            request,
        )
    assert replay.value.code is expected_replay


async def test_real_redis_commit_racing_reset_has_one_winner(
    real_redis_case: _RealRedisCase,
) -> None:
    base, session_id, approval_id, request = await _approved_session(real_redis_case)
    stored_before = await base.load_session(session_id)
    assert stored_before is not None
    barrier = _BarrierRedis(real_redis_case.client)
    commit_service = ChallengeService(
        repository=ChallengeRepository(barrier, lambda: NOW),
        clock=lambda: NOW,
    )
    reset_service = ChallengeService(
        repository=ChallengeRepository(barrier, lambda: NOW),
        clock=lambda: NOW,
    )

    results = await asyncio.gather(
        commit_service.commit(session_id, approval_id, request),
        reset_service.reset(
            session_id,
            ResetRequest(expected_generation=stored_before.session_generation),
        ),
        return_exceptions=True,
    )

    successes = [result for result in results if not isinstance(result, Exception)]
    failures = [
        result for result in results if isinstance(result, ChallengeDomainError)
    ]
    assert len(successes) == 1
    assert len(failures) == 1
    success = successes[0]
    real_redis_case.track_session(success.session_id)
    old_session = await base.load_session(session_id)
    approval = await base.load_approval(approval_id)
    if success.projection.state is ChallengeState.COMMITTED:
        assert old_session is not None and approval is not None
        _assert_single_commit(old_session)
        assert approval.status == "CONSUMED"
        expected_loser = ChallengeErrorCode.STALE_WORLD_VERSION
        expected_replay = ChallengeErrorCode.APPROVAL_REPLAYED
    else:
        assert success.projection.state is ChallengeState.INITIAL
        assert success.session_id != session_id
        assert old_session is None
        assert approval is None
        assert success.projection.world_version == 7
        assert success.projection.budget_sc == 300
        assert success.projection.receipt is None
        expected_loser = ChallengeErrorCode.CHALLENGE_SESSION_NOT_READY
        expected_replay = ChallengeErrorCode.CHALLENGE_SESSION_NOT_READY
    assert failures[0].code is expected_loser
    assert 1 <= len(barrier.watch_errors) <= 4
    assert set(barrier.watch_errors) == {"WatchError"}

    with pytest.raises(ChallengeDomainError) as replay:
        await ChallengeService(repository=base, clock=lambda: NOW).commit(
            session_id,
            approval_id,
            request,
        )
    assert replay.value.code is expected_replay


async def test_real_redis_watch_retry_rereads_state_and_reinvokes_mutator(
    real_redis_case: _RealRedisCase,
) -> None:
    base = ChallengeRepository(real_redis_case.client, lambda: NOW)
    service = ChallengeService(
        repository=base,
        clock=lambda: NOW,
    )
    session_id = f"real-{uuid4().hex}"
    real_redis_case.track_session(session_id)
    await base.create_session(session_id, service._new_session(NOW))
    session_key = f"{SESSION_PREFIX}{session_id}"
    writer = aioredis.from_url(real_redis_case.url, decode_responses=True)
    wrapped = _ConflictOnceRedis(real_redis_case.client, writer, session_key)
    repository = ChallengeRepository(wrapped, lambda: NOW)
    seen_budgets: list[int] = []

    def mutate(session: ChallengeSession, now: datetime) -> ChallengeSession:
        seen_budgets.append(session.world.budget_sc)
        return session.model_copy(
            update={
                "world": session.world.model_copy(
                    update={"budget_sc": session.world.budget_sc - 1}
                )
            },
            deep=True,
        )

    try:
        updated = await repository.mutate_session(session_id, mutate)
    finally:
        await writer.aclose()

    assert wrapped.conflict_written is True
    assert wrapped.execute_calls == 2
    assert wrapped.watch_errors == ["WatchError"]
    assert seen_budgets == [300, 250]
    assert updated.world.budget_sc == 249
    stored = await base.load_session(session_id)
    assert stored is not None
    assert stored.world.budget_sc == 249
