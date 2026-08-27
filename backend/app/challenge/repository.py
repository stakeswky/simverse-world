from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import WatchError

from app.challenge.canonical import canonical_json
from app.challenge.errors import (
    ERROR_STATUS_BY_CODE,
    ChallengeDomainError,
    ChallengeErrorCode,
)
from app.challenge.models import ApprovalRecord, ChallengeSession, ChallengeState
from app.redis_client import get_redis

SESSION_PREFIX = "sv:challenge:session:"
APPROVAL_PREFIX = "sv:challenge:approval:"
IDLE_TTL_SECONDS = 15 * 60
ABSOLUTE_TTL_SECONDS = 20 * 60
APPROVAL_TTL_SECONDS = 90
MAX_WATCH_RETRIES = 4

SessionMutator = Callable[[ChallengeSession, datetime], ChallengeSession]
CommitMutator = Callable[
    [ChallengeSession, ApprovalRecord, datetime],
    tuple[ChallengeSession, ApprovalRecord],
]
ActiveApprovalMutator = Callable[
    [ChallengeSession, ApprovalRecord | None, datetime],
    tuple[ChallengeSession, ApprovalRecord | None],
]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _domain_error(
    code: ChallengeErrorCode,
    message: str,
    *,
    retryable: bool,
    current_state: ChallengeState | None,
    next_action: str | None,
) -> ChallengeDomainError:
    return ChallengeDomainError(
        code,
        status=ERROR_STATUS_BY_CODE[code],
        message=message,
        retryable=retryable,
        current_state=current_state,
        next_action=next_action,
    )


class ChallengeRepository:
    def __init__(
        self,
        redis: Redis | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._redis = redis or get_redis()
        self._clock = clock or utc_now

    async def create_session(
        self, session_id: str, session: ChallengeSession
    ) -> None:
        now = self._clock()
        ttl = self._session_ttl(session, now)
        if ttl is None:
            raise self._expired_error(session.state)
        created = await self._redis.set(
            self._session_key(session_id),
            canonical_json(session),
            ex=ttl,
            nx=True,
        )
        if not created:
            raise _domain_error(
                ChallengeErrorCode.INVALID_STATE_TRANSITION,
                "Challenge session already exists.",
                retryable=True,
                current_state=None,
                next_action="get_session",
            )

    async def load_session(self, session_id: str) -> ChallengeSession | None:
        key = self._session_key(session_id)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        session = self._decode_session(raw)
        if session is None:
            await self._redis.delete(key)
            return None
        now = self._clock()
        if now >= session.absolute_expires_at:
            keys = [key]
            if session.active_approval_id:
                keys.append(self._approval_key(session.active_approval_id))
            await self._redis.delete(*keys)
            return None
        if now >= session.idle_expires_at and session.state is not ChallengeState.EXPIRED:
            return await self._expire_idle_session(session_id)
        return session

    async def save_session(self, session_id: str, session: ChallengeSession) -> None:
        now = self._clock()
        ttl = self._session_ttl(session, now)
        key = self._session_key(session_id)
        if ttl is None:
            keys = [key]
            if session.active_approval_id:
                keys.append(self._approval_key(session.active_approval_id))
            await self._redis.delete(*keys)
            return
        await self._redis.set(key, canonical_json(session), ex=ttl)

    async def load_approval(self, approval_id: str) -> ApprovalRecord | None:
        key = self._approval_key(approval_id)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        approval = self._decode_approval(raw)
        if approval is None:
            await self._redis.delete(key)
            return None
        now = self._clock()
        retention_deadline = approval.created_at + timedelta(
            seconds=ABSOLUTE_TTL_SECONDS
        )
        if now >= retention_deadline:
            await self._redis.delete(key)
            return None
        if approval.status == "APPROVED_ONCE" and now >= approval.expires_at:
            approval = approval.model_copy(update={"status": "EXPIRED"})
            await self._redis.set(
                key,
                canonical_json(approval),
                ex=self._ttl_until(retention_deadline, now),
            )
        return approval

    async def save_approval(self, approval: ApprovalRecord) -> None:
        now = self._clock()
        retention_deadline = approval.created_at + timedelta(
            seconds=ABSOLUTE_TTL_SECONDS
        )
        ttl = self._ttl_until(retention_deadline, now)
        if ttl is None:
            await self._redis.delete(self._approval_key(approval.approval_id))
            return
        await self._redis.set(
            self._approval_key(approval.approval_id),
            canonical_json(approval),
            ex=ttl,
        )

    async def delete_approval(self, approval_id: str | None) -> None:
        if approval_id is not None:
            await self._redis.delete(self._approval_key(approval_id))

    async def mutate_session(
        self, session_id: str, mutator: SessionMutator
    ) -> ChallengeSession:
        key = self._session_key(session_id)
        for _ in range(MAX_WATCH_RETRIES):
            async with self._redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    session = self._required_session(raw)
                    now = self._clock()
                    approval_key = None
                    approval = None
                    if (
                        now >= session.idle_expires_at
                        and session.active_approval_id
                    ):
                        approval_key = self._approval_key(
                            session.active_approval_id
                        )
                        await pipe.watch(approval_key)
                        approval = self._decode_approval(await pipe.get(approval_key))
                    await self._expire_transaction_if_needed(
                        pipe,
                        key,
                        approval_key,
                        session,
                        approval,
                        now,
                    )
                    updated = mutator(session.model_copy(deep=True), now)
                    updated = self._validated_session(updated)
                    updated = self._refresh_idle(updated, now)
                    pipe.multi()
                    pipe.set(
                        key,
                        canonical_json(updated),
                        ex=self._session_ttl(updated, now),
                    )
                    await pipe.execute()
                    return updated
                except WatchError:
                    continue
        raise self._watch_retry_error()

    async def mutate_session_and_approval(
        self,
        session_id: str,
        approval_id: str,
        mutator: CommitMutator,
    ) -> ChallengeSession:
        session_key = self._session_key(session_id)
        approval_key = self._approval_key(approval_id)
        for _ in range(MAX_WATCH_RETRIES):
            async with self._redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(session_key, approval_key)
                    session = self._required_session(await pipe.get(session_key))
                    now = self._clock()
                    approval = self._decode_approval(await pipe.get(approval_key))
                    await self._expire_transaction_if_needed(
                        pipe,
                        session_key,
                        approval_key,
                        session,
                        approval,
                        now,
                    )
                    if session.state in {
                        ChallengeState.COMMITTED,
                        ChallengeState.VERIFIED,
                    } or (
                        approval is not None and approval.status == "CONSUMED"
                    ):
                        raise self._approval_replayed_error(session.state)
                    if approval is None:
                        raise self._missing_approval_error(session, now)
                    if approval.status == "APPROVED_ONCE" and now >= approval.expires_at:
                        expired = approval.model_copy(update={"status": "EXPIRED"})
                        pipe.multi()
                        pipe.set(
                            approval_key,
                            canonical_json(expired),
                            ex=self._session_ttl(session, now),
                        )
                        await pipe.execute()
                        raise _domain_error(
                            ChallengeErrorCode.APPROVAL_EXPIRED,
                            "Approval capability has expired.",
                            retryable=False,
                            current_state=session.state,
                            next_action="preview",
                        )
                    updated_session, updated_approval = mutator(
                        session.model_copy(deep=True),
                        approval.model_copy(deep=True),
                        now,
                    )
                    updated_session = self._refresh_idle(
                        self._validated_session(updated_session), now
                    )
                    updated_approval = self._validated_approval(updated_approval)
                    if (
                        updated_session.absolute_expires_at
                        != session.absolute_expires_at
                        or updated_approval.approval_id != approval_id
                        or updated_approval.status != "CONSUMED"
                    ):
                        raise TypeError(
                            "commit mutator must preserve the absolute deadline "
                            "and consume the watched approval"
                        )
                    ttl = self._session_ttl(updated_session, now)
                    pipe.multi()
                    pipe.set(
                        session_key,
                        canonical_json(updated_session),
                        ex=ttl,
                    )
                    pipe.set(
                        approval_key,
                        canonical_json(updated_approval),
                        ex=ttl,
                    )
                    await pipe.execute()
                    return updated_session
                except WatchError:
                    continue
        raise self._watch_retry_error()

    async def mutate_session_with_active_approval(
        self,
        session_id: str,
        mutator: ActiveApprovalMutator,
    ) -> ChallengeSession:
        session_key = self._session_key(session_id)
        for _ in range(MAX_WATCH_RETRIES):
            async with self._redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(session_key)
                    session = self._required_session(await pipe.get(session_key))
                    now = self._clock()
                    approval_id = session.active_approval_id
                    approval_key = (
                        self._approval_key(approval_id) if approval_id else None
                    )
                    if approval_key:
                        await pipe.watch(approval_key)
                        approval = self._decode_approval(await pipe.get(approval_key))
                    else:
                        approval = None
                    await self._expire_transaction_if_needed(
                        pipe,
                        session_key,
                        approval_key,
                        session,
                        approval,
                        now,
                    )
                    if (
                        approval is not None
                        and approval.status == "APPROVED_ONCE"
                        and now >= approval.expires_at
                    ):
                        approval = approval.model_copy(update={"status": "EXPIRED"})
                    updated_session, updated_approval = mutator(
                        session.model_copy(deep=True),
                        approval.model_copy(deep=True) if approval else None,
                        now,
                    )
                    updated_session = self._refresh_idle(
                        self._validated_session(updated_session), now
                    )
                    if updated_approval is not None:
                        updated_approval = self._validated_approval(updated_approval)
                    ttl = self._session_ttl(updated_session, now)
                    pipe.multi()
                    pipe.set(
                        session_key,
                        canonical_json(updated_session),
                        ex=ttl,
                    )
                    if approval_key and updated_approval is None:
                        pipe.delete(approval_key)
                    elif updated_approval is not None:
                        if (
                            approval_key
                            and approval_key
                            != self._approval_key(updated_approval.approval_id)
                        ):
                            pipe.delete(approval_key)
                        pipe.set(
                            self._approval_key(updated_approval.approval_id),
                            canonical_json(updated_approval),
                            ex=ttl,
                        )
                    await pipe.execute()
                    return updated_session
                except WatchError:
                    continue
        raise self._watch_retry_error()

    async def _expire_transaction_if_needed(
        self,
        pipe,
        session_key: str,
        approval_key: str | None,
        session: ChallengeSession,
        approval: ApprovalRecord | None,
        now: datetime,
    ) -> None:
        if now >= session.absolute_expires_at:
            pipe.multi()
            pipe.delete(session_key)
            if approval_key:
                pipe.delete(approval_key)
            await pipe.execute()
            raise self._expired_error(session.state)
        if session.state is ChallengeState.EXPIRED:
            raise self._expired_error(session.state)
        if now < session.idle_expires_at:
            return
        tombstone = self._expired_session(session)
        ttl = self._session_ttl(tombstone, now)
        pipe.multi()
        pipe.set(session_key, canonical_json(tombstone), ex=ttl)
        if approval_key and approval is None:
            pipe.delete(approval_key)
        elif approval_key and approval is not None:
            expired_approval = approval.model_copy(update={"status": "EXPIRED"})
            pipe.set(approval_key, canonical_json(expired_approval), ex=ttl)
        await pipe.execute()
        raise self._expired_error(ChallengeState.EXPIRED)

    async def replace_session(
        self,
        old_session_id: str,
        expected_generation: str,
        new_session_id: str,
        new_session: ChallengeSession,
    ) -> None:
        old_key = self._session_key(old_session_id)
        new_key = self._session_key(new_session_id)
        baseline_session_json: str | bytes | None = None
        baseline_approval_json: str | bytes | None = None
        for _ in range(MAX_WATCH_RETRIES):
            async with self._redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(old_key)
                    old_session_json = await pipe.get(old_key)
                    old_session = self._required_session(old_session_json)
                    approval_key = (
                        self._approval_key(old_session.active_approval_id)
                        if old_session.active_approval_id
                        else None
                    )
                    if approval_key:
                        await pipe.watch(approval_key)
                        approval_json = await pipe.get(approval_key)
                    else:
                        approval_json = None
                    if baseline_session_json is None:
                        baseline_session_json = old_session_json
                        baseline_approval_json = approval_json
                    elif (
                        old_session_json != baseline_session_json
                        or approval_json != baseline_approval_json
                    ):
                        raise self._watch_retry_error()
                    if old_session.session_generation != expected_generation:
                        raise _domain_error(
                            ChallengeErrorCode.STALE_TOOL_SURFACE,
                            "Session generation no longer matches the active tool surface.",
                            retryable=True,
                            current_state=old_session.state,
                            next_action="get_session",
                        )
                    now = self._clock()
                    if now >= old_session.absolute_expires_at:
                        pipe.multi()
                        pipe.delete(old_key)
                        if approval_key:
                            pipe.delete(approval_key)
                        await pipe.execute()
                        raise self._expired_error(old_session.state)
                    ttl = self._session_ttl(new_session, now)
                    if ttl is None:
                        raise self._expired_error(new_session.state)
                    pipe.multi()
                    pipe.delete(old_key)
                    if approval_key:
                        pipe.delete(approval_key)
                    pipe.set(new_key, canonical_json(new_session), ex=ttl)
                    await pipe.execute()
                    return
                except WatchError:
                    continue
        raise self._watch_retry_error()

    async def _expire_idle_session(
        self, session_id: str
    ) -> ChallengeSession | None:
        session_key = self._session_key(session_id)
        for _ in range(MAX_WATCH_RETRIES):
            async with self._redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(session_key)
                    raw = await pipe.get(session_key)
                    if raw is None:
                        return None
                    session = self._decode_session(raw)
                    if session is None:
                        pipe.multi()
                        pipe.delete(session_key)
                        await pipe.execute()
                        return None
                    now = self._clock()
                    approval_key = (
                        self._approval_key(session.active_approval_id)
                        if session.active_approval_id
                        else None
                    )
                    approval = None
                    if approval_key:
                        await pipe.watch(approval_key)
                        approval = self._decode_approval(await pipe.get(approval_key))
                    if now >= session.absolute_expires_at:
                        pipe.multi()
                        pipe.delete(session_key)
                        if approval_key:
                            pipe.delete(approval_key)
                        await pipe.execute()
                        return None
                    if (
                        now < session.idle_expires_at
                        or session.state is ChallengeState.EXPIRED
                    ):
                        return session
                    tombstone = self._expired_session(session)
                    ttl = self._session_ttl(tombstone, now)
                    pipe.multi()
                    pipe.set(session_key, canonical_json(tombstone), ex=ttl)
                    if approval_key and approval is None:
                        pipe.delete(approval_key)
                    elif approval_key and approval is not None:
                        approval = approval.model_copy(update={"status": "EXPIRED"})
                        pipe.set(approval_key, canonical_json(approval), ex=ttl)
                    await pipe.execute()
                    return tombstone
                except WatchError:
                    continue
        raise self._watch_retry_error()

    @staticmethod
    def _session_key(session_id: str) -> str:
        return f"{SESSION_PREFIX}{session_id}"

    @staticmethod
    def _approval_key(approval_id: str) -> str:
        return f"{APPROVAL_PREFIX}{approval_id}"

    @staticmethod
    def _decode_session(raw: str | bytes | None) -> ChallengeSession | None:
        if raw is None:
            return None
        try:
            return ChallengeSession.model_validate_json(raw)
        except (ValidationError, ValueError, TypeError):
            return None

    @staticmethod
    def _decode_approval(raw: str | bytes | None) -> ApprovalRecord | None:
        if raw is None:
            return None
        try:
            return ApprovalRecord.model_validate_json(raw)
        except (ValidationError, ValueError, TypeError):
            return None

    def _required_session(self, raw: str | bytes | None) -> ChallengeSession:
        session = self._decode_session(raw)
        if session is None:
            raise _domain_error(
                ChallengeErrorCode.CHALLENGE_SESSION_NOT_READY,
                "Challenge session is not ready.",
                retryable=True,
                current_state=None,
                next_action="create_session",
            )
        return session

    @staticmethod
    def _validated_session(value: ChallengeSession) -> ChallengeSession:
        if not isinstance(value, ChallengeSession):
            raise TypeError("session mutator must return ChallengeSession")
        return ChallengeSession.model_validate(value.model_dump())

    @staticmethod
    def _validated_approval(value: ApprovalRecord) -> ApprovalRecord:
        if not isinstance(value, ApprovalRecord):
            raise TypeError("approval mutator must return ApprovalRecord")
        return ApprovalRecord.model_validate(value.model_dump())

    @staticmethod
    def _refresh_idle(session: ChallengeSession, now: datetime) -> ChallengeSession:
        refreshed = min(
            now + timedelta(seconds=IDLE_TTL_SECONDS),
            session.absolute_expires_at,
        )
        return session.model_copy(update={"idle_expires_at": refreshed})

    @staticmethod
    def _expired_session(session: ChallengeSession) -> ChallengeSession:
        return session.model_copy(
            update={
                "state": ChallengeState.EXPIRED,
                "evidence": None,
                "preview": None,
                "receipt": None,
                "verification": None,
                "audit_events": [],
            }
        )

    @staticmethod
    def _session_ttl(session: ChallengeSession, now: datetime) -> int | None:
        return ChallengeRepository._ttl_until(session.absolute_expires_at, now)

    @staticmethod
    def _ttl_until(deadline: datetime, now: datetime) -> int | None:
        remaining = (deadline - now).total_seconds()
        if remaining <= 0:
            return None
        return max(1, math.ceil(remaining))

    @staticmethod
    def _expired_error(current_state: ChallengeState) -> ChallengeDomainError:
        return _domain_error(
            ChallengeErrorCode.CHALLENGE_SESSION_EXPIRED,
            "Challenge session has expired.",
            retryable=False,
            current_state=current_state,
            next_action="reset",
        )

    @staticmethod
    def _missing_approval_error(
        session: ChallengeSession, now: datetime
    ) -> ChallengeDomainError:
        if session.approval_expires_at and now >= session.approval_expires_at:
            return _domain_error(
                ChallengeErrorCode.APPROVAL_EXPIRED,
                "Approval capability has expired.",
                retryable=False,
                current_state=session.state,
                next_action="preview",
            )
        return _domain_error(
            ChallengeErrorCode.APPROVAL_REQUIRED,
            "A matching one-time approval capability is required.",
            retryable=False,
            current_state=session.state,
            next_action="approve",
        )

    @staticmethod
    def _approval_replayed_error(
        current_state: ChallengeState,
    ) -> ChallengeDomainError:
        return _domain_error(
            ChallengeErrorCode.APPROVAL_REPLAYED,
            "The one-time approval capability has already been consumed.",
            retryable=False,
            current_state=current_state,
            next_action=(
                "verify" if current_state is ChallengeState.COMMITTED else "reset"
            ),
        )

    @staticmethod
    def _watch_retry_error() -> ChallengeDomainError:
        return _domain_error(
            ChallengeErrorCode.STALE_WORLD_VERSION,
            "Challenge state changed during the operation.",
            retryable=True,
            current_state=None,
            next_action="get_session",
        )
