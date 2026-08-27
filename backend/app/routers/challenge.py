from __future__ import annotations

import logging
import secrets
from collections.abc import Callable

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.challenge.errors import (
    ERROR_STATUS_BY_CODE,
    ChallengeDomainError,
    ChallengeErrorCode,
)
from app.challenge.models import (
    ApproveRequest,
    ChallengeProjection,
    InvestigateRequest,
    PreviewRequest,
    ResetRequest,
)
from app.challenge.service import ChallengeService
from app.config import settings

logger = logging.getLogger(__name__)

SESSION_COOKIE = "sv_challenge_session"
APPROVAL_COOKIE = "sv_challenge_approval"
CSRF_HEADER = "X-CSRF-Token"
PROTECTED_MUTATION_PATHS = (
    "/investigate",
    "/preview",
    "/approve",
    "/revoke",
    "/commit",
    "/verify",
    "/reset",
)


def _error_response(error: ChallengeDomainError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.to_payload())


def _domain_error(
    code: ChallengeErrorCode,
    message: str,
    *,
    retryable: bool = False,
    next_action: str | None = None,
) -> ChallengeDomainError:
    return ChallengeDomainError(
        code,
        status=ERROR_STATUS_BY_CODE[code],
        message=message,
        retryable=retryable,
        current_state=None,
        next_action=next_action,
    )


class ChallengeRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_handler = super().get_route_handler()

        async def challenge_handler(request: Request) -> Response:
            try:
                return await original_handler(request)
            except RequestValidationError:
                return _error_response(
                    _domain_error(
                        ChallengeErrorCode.INVALID_INPUT,
                        "Challenge request did not match the required schema.",
                    )
                )
            except ChallengeDomainError as error:
                return _error_response(error)
            except Exception:
                logger.exception("Unhandled challenge route error")
                return _error_response(
                    _domain_error(
                        ChallengeErrorCode.CHALLENGE_INTERNAL_ERROR,
                        "Challenge request could not be completed.",
                    )
                )

        return challenge_handler


router = APIRouter(
    prefix="/challenge",
    tags=["challenge"],
    route_class=ChallengeRoute,
)


def _cookie_secure() -> bool:
    override = settings.challenge_cookie_secure
    return override if override is not None else not settings.debug


def set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/challenge",
    )


def set_approval_cookie(response: Response, approval_id: str) -> None:
    response.set_cookie(
        APPROVAL_COOKIE,
        approval_id,
        max_age=90,
        httponly=True,
        secure=_cookie_secure(),
        samesite="strict",
        path="/challenge/commit",
    )


def delete_approval_cookie(response: Response) -> None:
    response.delete_cookie(
        APPROVAL_COOKIE,
        httponly=True,
        secure=_cookie_secure(),
        samesite="strict",
        path="/challenge/commit",
    )


def _require_exact_origin(request: Request) -> None:
    allowed_origins = settings.challenge_allowed_origins or []
    if request.headers.get("origin") not in allowed_origins:
        raise _domain_error(
            ChallengeErrorCode.INVALID_INPUT,
            "Request Origin is missing or not allowed.",
        )


def _require_session_cookie(request: Request) -> str:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise _domain_error(
            ChallengeErrorCode.CHALLENGE_SESSION_NOT_READY,
            "Challenge session cookie is required.",
            retryable=True,
            next_action="create_session",
        )
    return session_id


async def require_mutation_context(
    request: Request, service: ChallengeService
) -> str:
    _require_exact_origin(request)
    session_id = _require_session_cookie(request)
    current = await service.get_session(session_id)
    supplied_csrf = request.headers.get(CSRF_HEADER)
    if supplied_csrf is None or not secrets.compare_digest(
        supplied_csrf, current.projection.csrf_token
    ):
        raise _domain_error(
            ChallengeErrorCode.INVALID_INPUT,
            "A valid challenge CSRF token is required.",
        )
    return session_id


@router.post("/session", response_model=ChallengeProjection)
async def create_session(request: Request, response: Response) -> ChallengeProjection:
    _require_exact_origin(request)
    if await request.body():
        raise _domain_error(
            ChallengeErrorCode.INVALID_INPUT,
            "Challenge session creation does not accept a request body.",
        )
    result = await ChallengeService().create_or_resume(
        request.cookies.get(SESSION_COOKIE)
    )
    set_session_cookie(response, result.session_id)
    return result.projection


@router.get("/session", response_model=ChallengeProjection)
async def get_session(request: Request) -> ChallengeProjection:
    result = await ChallengeService().get_session(_require_session_cookie(request))
    return result.projection


@router.post("/investigate", response_model=ChallengeProjection)
async def investigate(
    body: InvestigateRequest, request: Request
) -> ChallengeProjection:
    service = ChallengeService()
    session_id = await require_mutation_context(request, service)
    result = await service.investigate(session_id, body)
    return result.projection


@router.post("/preview", response_model=ChallengeProjection)
async def preview(
    body: PreviewRequest, request: Request, response: Response
) -> ChallengeProjection:
    service = ChallengeService()
    session_id = await require_mutation_context(request, service)
    result = await service.preview(session_id, body)
    delete_approval_cookie(response)
    return result.projection


@router.post("/approve", response_model=ChallengeProjection)
async def approve(
    body: ApproveRequest,
    request: Request,
    response: Response,
) -> ChallengeProjection:
    service = ChallengeService()
    session_id = await require_mutation_context(request, service)
    result = await service.approve(session_id, body)
    if result.approval_id is None:
        raise _domain_error(
            ChallengeErrorCode.CHALLENGE_INTERNAL_ERROR,
            "Approval capability could not be issued.",
        )
    set_approval_cookie(response, result.approval_id)
    return result.projection


@router.post("/revoke", response_model=ChallengeProjection)
async def revoke(request: Request, response: Response) -> ChallengeProjection:
    service = ChallengeService()
    session_id = await require_mutation_context(request, service)
    result = await service.revoke(session_id)
    delete_approval_cookie(response)
    return result.projection


@router.post("/reset", response_model=ChallengeProjection)
async def reset_session(
    body: ResetRequest, request: Request, response: Response
) -> ChallengeProjection:
    service = ChallengeService()
    session_id = await require_mutation_context(request, service)
    result = await service.reset(session_id, body)
    set_session_cookie(response, result.session_id)
    delete_approval_cookie(response)
    return result.projection
