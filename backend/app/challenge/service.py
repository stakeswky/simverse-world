from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta

from app.challenge.canonical import world_hash
from app.challenge.engine import build_intervention_preview, investigate_world
from app.challenge.errors import (
    ERROR_STATUS_BY_CODE,
    ChallengeDomainError,
    ChallengeErrorCode,
)
from app.challenge.fixture import build_initial_world
from app.challenge.models import (
    ApprovalRecord,
    AuditEvent,
    ChallengeProjection,
    ChallengeSession,
    ChallengeState,
    InvestigateRequest,
    PreviewRequest,
    ResetRequest,
    SessionResult,
)
from app.challenge.repository import (
    ABSOLUTE_TTL_SECONDS,
    IDLE_TTL_SECONDS,
    ChallengeRepository,
    utc_now,
)

FINAL_TOOL_SURFACE: Mapping[ChallengeState, Sequence[str]] = {
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

_LEGAL_TRANSITIONS: Mapping[tuple[ChallengeState, str], ChallengeState] = {
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


def _error(
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


def validate_transition(state: ChallengeState, action: str) -> ChallengeState:
    target = _LEGAL_TRANSITIONS.get((state, action))
    if target is not None:
        return target
    if state is ChallengeState.EXPIRED:
        raise _error(
            ChallengeErrorCode.CHALLENGE_SESSION_EXPIRED,
            "Challenge session has expired.",
            retryable=False,
            current_state=state,
            next_action="reset",
        )
    if action == "commit" and state in {
        ChallengeState.INITIAL,
        ChallengeState.PREVIEW_READY,
    }:
        raise _error(
            ChallengeErrorCode.APPROVAL_REQUIRED,
            "A trusted one-time approval is required before commit.",
            retryable=False,
            current_state=state,
            next_action="approve",
        )
    if action == "commit" and state in {
        ChallengeState.COMMITTED,
        ChallengeState.VERIFIED,
    }:
        raise _error(
            ChallengeErrorCode.APPROVAL_REPLAYED,
            "The approved intervention has already been committed.",
            retryable=False,
            current_state=state,
            next_action="verify" if state is ChallengeState.COMMITTED else "reset",
        )
    if action == "verify" and state is ChallengeState.VERIFIED:
        raise _error(
            ChallengeErrorCode.OUTCOME_ALREADY_VERIFIED,
            "The outcome has already been verified.",
            retryable=False,
            current_state=state,
            next_action="reset",
        )
    raise _error(
        ChallengeErrorCode.INVALID_STATE_TRANSITION,
        f"Action {action!r} is not allowed from {state.value}.",
        retryable=False,
        current_state=state,
        next_action=None,
    )


class ChallengeService:
    def __init__(
        self,
        repository: ChallengeRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._clock = clock or utc_now
        self._repository = repository or ChallengeRepository(clock=self._clock)

    async def create_or_resume(self, session_id: str | None) -> SessionResult:
        if session_id is not None:
            existing = await self._repository.load_session(session_id)
            if existing is not None:
                return self._result(session_id, existing)
        now = self._clock()
        new_session_id = secrets.token_urlsafe(32)
        session = self._new_session(now)
        await self._repository.create_session(new_session_id, session)
        return self._result(new_session_id, session)

    async def get_session(self, session_id: str | None) -> SessionResult:
        if session_id is None:
            raise _error(
                ChallengeErrorCode.CHALLENGE_SESSION_NOT_READY,
                "Challenge session cookie is required.",
                retryable=True,
                current_state=None,
                next_action="create_session",
            )
        session = await self._repository.load_session(session_id)
        if session is None:
            raise _error(
                ChallengeErrorCode.CHALLENGE_SESSION_EXPIRED,
                "Challenge session no longer exists.",
                retryable=False,
                current_state=None,
                next_action="create_session",
            )
        return self._result(session_id, session)

    async def investigate(
        self, session_id: str, request: InvestigateRequest
    ) -> SessionResult:
        evidence_id = secrets.token_urlsafe(16)
        audit_event_id = secrets.token_urlsafe(16)

        def mutate(session: ChallengeSession, now: datetime) -> ChallengeSession:
            state_before = session.state
            state_after = validate_transition(state_before, "investigate")
            evidence = investigate_world(
                session.world,
                budget_cap_sc=request.budget_cap_sc,
                evidence_id=evidence_id,
            )
            updated = session.model_copy(deep=True)
            updated.state = state_after
            updated.evidence = evidence
            updated.audit_events.append(
                AuditEvent(
                    event_id=audit_event_id,
                    action="investigate",
                    state_before=state_before,
                    state_after=state_after,
                    reason_code=None,
                    world_version_before=session.world.world_version,
                    world_version_after=session.world.world_version,
                    occurred_at=now,
                )
            )
            return updated

        session = await self._repository.mutate_session(session_id, mutate)
        return self._result(session_id, session)

    async def preview(
        self, session_id: str, request: PreviewRequest
    ) -> SessionResult:
        preview_id = secrets.token_urlsafe(16)
        audit_event_id = secrets.token_urlsafe(16)

        def mutate(
            session: ChallengeSession,
            approval: ApprovalRecord | None,
            now: datetime,
        ) -> tuple[ChallengeSession, ApprovalRecord | None]:
            state_before = session.state
            state_after = validate_transition(state_before, "preview")
            if session.evidence is None:
                raise _error(
                    ChallengeErrorCode.EVIDENCE_STALE,
                    "Current Harbor evidence is missing or stale.",
                    retryable=True,
                    current_state=state_before,
                    next_action="investigate",
                )
            if session.evidence.crisis_id != request.crisis_id:
                raise _error(
                    ChallengeErrorCode.EVIDENCE_STALE,
                    "Current evidence does not match the requested crisis.",
                    retryable=True,
                    current_state=state_before,
                    next_action="investigate",
                )
            if state_before is ChallengeState.APPROVED_ONCE:
                if (
                    approval is None
                    or session.preview is None
                    or approval.approval_id != session.active_approval_id
                    or approval.session_generation != session.session_generation
                    or approval.preview_id != session.preview.preview_id
                    or approval.diff_hash != session.preview.diff_hash
                    or approval.world_version != session.world.world_version
                    or approval.status != "APPROVED_ONCE"
                ):
                    raise _error(
                        ChallengeErrorCode.APPROVAL_MISMATCH,
                        "Active approval does not match the server-side preview.",
                        retryable=False,
                        current_state=state_before,
                        next_action="preview",
                    )
                approval = approval.model_copy(update={"status": "INVALIDATED"})

            preview = build_intervention_preview(
                session.world,
                session.evidence,
                session_generation=session.session_generation,
                preview_id=preview_id,
                created_at=now,
            )
            updated = session.model_copy(deep=True)
            updated.state = state_after
            updated.preview = preview
            updated.active_approval_id = None
            updated.approval_fingerprint = None
            updated.approval_expires_at = None
            updated.audit_events.append(
                AuditEvent(
                    event_id=audit_event_id,
                    action="preview",
                    state_before=state_before,
                    state_after=state_after,
                    reason_code=None,
                    world_version_before=session.world.world_version,
                    world_version_after=session.world.world_version,
                    occurred_at=now,
                )
            )
            return updated, approval

        session = await self._repository.mutate_session_with_active_approval(
            session_id,
            mutate,
        )
        return self._result(session_id, session)

    async def reset(
        self, session_id: str, request: ResetRequest
    ) -> SessionResult:
        session = await self._repository.load_session(session_id)
        if session is None:
            raise _error(
                ChallengeErrorCode.CHALLENGE_SESSION_EXPIRED,
                "Challenge session no longer exists.",
                retryable=False,
                current_state=None,
                next_action="create_session",
            )
        validate_transition(session.state, "reset")
        if session.session_generation != request.expected_generation:
            raise _error(
                ChallengeErrorCode.STALE_TOOL_SURFACE,
                "Session generation no longer matches the active tool surface.",
                retryable=True,
                current_state=session.state,
                next_action="get_session",
            )
        expected_world = build_initial_world()
        expected_hash = world_hash(expected_world)
        if session.initial_world_hash != expected_hash:
            raise _error(
                ChallengeErrorCode.RESET_HASH_MISMATCH,
                "Locked initial world hash does not match the deterministic fixture.",
                retryable=False,
                current_state=session.state,
                next_action=None,
            )
        now = self._clock()
        new_session_id = secrets.token_urlsafe(32)
        new_session = self._new_session(now)
        if new_session.initial_world_hash != expected_hash:
            raise _error(
                ChallengeErrorCode.RESET_HASH_MISMATCH,
                "Reset world hash does not match the deterministic fixture.",
                retryable=False,
                current_state=session.state,
                next_action=None,
            )
        await self._repository.replace_session(
            session_id,
            request.expected_generation,
            new_session_id,
            new_session,
        )
        return self._result(new_session_id, new_session)

    @staticmethod
    def _new_session(now: datetime) -> ChallengeSession:
        world = build_initial_world()
        return ChallengeSession(
            session_generation=secrets.token_urlsafe(32),
            scenario_id="harbor-wage-crisis-v1",
            fixture_version=1,
            state=ChallengeState.INITIAL,
            created_at=now,
            idle_expires_at=now + timedelta(seconds=IDLE_TTL_SECONDS),
            absolute_expires_at=now + timedelta(seconds=ABSOLUTE_TTL_SECONDS),
            csrf_token=secrets.token_urlsafe(32),
            initial_world_hash=world_hash(world),
            world=world,
            evidence=None,
            preview=None,
            active_approval_id=None,
            approval_fingerprint=None,
            approval_expires_at=None,
            receipt=None,
            verification=None,
            audit_events=[],
        )

    @staticmethod
    def _projection(session: ChallengeSession) -> ChallengeProjection:
        return ChallengeProjection(
            session_generation=session.session_generation,
            state=session.state,
            scenario_id=session.scenario_id,
            fixture_version=session.fixture_version,
            world_version=session.world.world_version,
            world_hash=world_hash(session.world),
            world_time=session.world.world_time,
            budget_sc=session.world.budget_sc,
            tool_surface=list(FINAL_TOOL_SURFACE[session.state]),
            expires_at=min(session.idle_expires_at, session.absolute_expires_at),
            csrf_token=session.csrf_token,
            world=session.world,
            evidence=session.evidence,
            preview=session.preview,
            approval_fingerprint=session.approval_fingerprint,
            approval_expires_at=session.approval_expires_at,
            receipt=session.receipt,
            verification=session.verification,
        )

    def _result(self, session_id: str, session: ChallengeSession) -> SessionResult:
        return SessionResult(
            session_id=session_id,
            projection=self._projection(session),
            approval_id=None,
        )
