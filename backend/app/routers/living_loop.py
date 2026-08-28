"""Authenticated Living Loop P0 user routes."""

from __future__ import annotations

from json import JSONDecodeError
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.living_loop_service import (
    LivingLoopError,
    choose,
    get_today,
    mark_result_viewed,
)

router = APIRouter(prefix="/living-loop", tags=["living-loop"])


class ChooseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice_key: Literal[
        "public_support",
        "private_mediation",
        "collect_evidence",
    ]
    idempotency_key: UUID = Field(description="Canonical client-generated UUID4")

    @field_validator("idempotency_key")
    @classmethod
    def reserve_server_uuid_namespace(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("idempotency_key must be UUID4")
        return value


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


async def _require_user(request: Request, db: AsyncSession) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth token")
    user = await get_current_user(db, auth.removeprefix("Bearer "))
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid auth token")
    return user


def _http_error(error: LivingLoopError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    )


def _decision_uuid(value: str) -> str:
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_request"},
        ) from None
    canonical = str(parsed)
    if canonical != value:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_request"},
        )
    return canonical


async def _validated_json(request: Request, model: type[BaseModel]) -> BaseModel:
    media_type = request.headers.get("Content-Type", "").split(";", 1)[0].lower()
    if media_type != "application/json":
        raise HTTPException(status_code=415, detail={"code": "json_required"})
    try:
        return model.model_validate(await request.json())
    except (JSONDecodeError, UnicodeDecodeError, ValidationError, ValueError):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_request"},
        ) from None


@router.get("/today")
async def today(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await _require_user(request, db)
    try:
        return await get_today(db, user.id)
    except LivingLoopError as error:
        raise _http_error(error) from error


@router.post(
    "/decisions/{decision_id}/choose",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": ChooseRequest.model_json_schema()},
            },
        },
    },
)
async def choose_decision(
    decision_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await _require_user(request, db)
    canonical_id = _decision_uuid(decision_id)
    body = await _validated_json(request, ChooseRequest)
    assert isinstance(body, ChooseRequest)
    try:
        return await choose(
            db,
            user_id=user.id,
            decision_id=canonical_id,
            choice_key=body.choice_key,
            idempotency_key=str(body.idempotency_key),
        )
    except LivingLoopError as error:
        raise _http_error(error) from error


@router.post("/decisions/{decision_id}/result-viewed")
async def result_viewed(
    decision_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await _require_user(request, db)
    canonical_id = _decision_uuid(decision_id)
    raw_body = await request.body()
    if raw_body.strip():
        await _validated_json(request, EmptyRequest)
    try:
        return await mark_result_viewed(
            db,
            user_id=user.id,
            decision_id=canonical_id,
        )
    except LivingLoopError as error:
        raise _http_error(error) from error
