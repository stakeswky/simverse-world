from enum import StrEnum

from app.challenge.models import ChallengeState


class ChallengeErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    CHALLENGE_SESSION_NOT_READY = "CHALLENGE_SESSION_NOT_READY"
    CHALLENGE_SESSION_EXPIRED = "CHALLENGE_SESSION_EXPIRED"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    NO_ACTIONABLE_CRISIS = "NO_ACTIONABLE_CRISIS"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    PREVIEW_NOT_FOUND = "PREVIEW_NOT_FOUND"
    PREVIEW_STALE = "PREVIEW_STALE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_MISMATCH = "APPROVAL_MISMATCH"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_REVOKED = "APPROVAL_REVOKED"
    APPROVAL_REPLAYED = "APPROVAL_REPLAYED"
    STALE_WORLD_VERSION = "STALE_WORLD_VERSION"
    STALE_TOOL_SURFACE = "STALE_TOOL_SURFACE"
    OUTCOME_ALREADY_VERIFIED = "OUTCOME_ALREADY_VERIFIED"
    OUTCOME_INCOMPLETE = "OUTCOME_INCOMPLETE"
    RESET_HASH_MISMATCH = "RESET_HASH_MISMATCH"
    CHALLENGE_INTERNAL_ERROR = "CHALLENGE_INTERNAL_ERROR"


ERROR_STATUS_BY_CODE: dict[ChallengeErrorCode, int] = {
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


class ChallengeDomainError(Exception):
    def __init__(
        self,
        code: ChallengeErrorCode,
        *,
        status: int,
        message: str,
        retryable: bool,
        current_state: ChallengeState | None,
        next_action: str | None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message
        self.retryable = retryable
        self.current_state = current_state
        self.next_action = next_action

    def to_payload(self) -> dict[str, dict[str, str | bool | None]]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "retryable": self.retryable,
                "current_state": (
                    self.current_state.value if self.current_state else None
                ),
                "next_action": self.next_action,
            }
        }
