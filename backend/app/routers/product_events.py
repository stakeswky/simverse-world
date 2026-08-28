"""Strict first-party Product Event ingestion for Living Loop P0."""

from copy import deepcopy
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    ValidationError,
    field_validator,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.rate_limit import limiter
from app.services.auth_service import get_current_user
from app.services.product_event_service import (
    ProductEventIdempotencyConflict,
    ProductEventInput,
    persist_product_events,
)


PRODUCT_EVENTS_MAX_BODY_BYTES = 32_768
PRODUCT_EVENTS_RATE_LIMIT_PER_MINUTE = 30

router = APIRouter(prefix="/product-events", tags=["product-events"])

CanonicalUUID = Annotated[
    str,
    StringConstraints(
        pattern=(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{4}-[0-9a-f]{12}$"
        )
    ),
]
ScenarioKey = Literal["harbor_wage_dispute_v1"]
ContractVersion = Annotated[StrictInt, Field(ge=1, le=1)]
ChoiceKey = Literal["public_support", "private_mediation", "collect_evidence"]
DecisionState = Literal["pending", "chosen", "result_ready", "result_viewed"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _SurfaceProperties(_StrictModel):
    surface_version: ContractVersion


class TodayViewedProperties(_SurfaceProperties):
    entry_point: Literal["root", "direct", "return"]


class DecisionViewedProperties(_SurfaceProperties):
    decision_id: CanonicalUUID
    scenario_key: ScenarioKey
    scenario_version: ContractVersion
    decision_state: DecisionState


class ChoiceProperties(_SurfaceProperties):
    decision_id: CanonicalUUID
    scenario_key: ScenarioKey
    scenario_version: ContractVersion
    choice_key: ChoiceKey


class EnterTownProperties(_SurfaceProperties):
    source: Literal["header", "secondary", "fallback"]


class CityPulseProperties(_SurfaceProperties):
    source: Literal["card", "since_you_left"]
    target: Literal["capsules"]


class _ClientEventEnvelope(_StrictModel):
    event_id: CanonicalUUID
    session_id: CanonicalUUID | None = None
    client_occurred_at: AwareDatetime | None = None

    @field_validator("event_id")
    @classmethod
    def reserve_server_uuid_namespace(cls, value: str) -> str:
        if UUID(value).version != 4:
            raise ValueError("client event_id must be UUID4")
        return value

    @field_validator("client_occurred_at", mode="before")
    @classmethod
    def parse_client_time(cls, value):
        # FastAPI validates an already-decoded JSON object, so strict mode
        # would otherwise reject the ISO-8601 string used on the wire.
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return value
        return value

    @field_validator("client_occurred_at")
    @classmethod
    def normalize_client_time(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None


class TodayViewedEvent(_ClientEventEnvelope):
    event_name: Literal["living_loop_today_viewed"]
    properties: TodayViewedProperties


class DecisionViewedEvent(_ClientEventEnvelope):
    event_name: Literal["living_loop_decision_viewed"]
    properties: DecisionViewedProperties


class ChoicePreviewedEvent(_ClientEventEnvelope):
    event_name: Literal["living_loop_choice_previewed"]
    properties: ChoiceProperties


class ImmediateResultViewedEvent(_ClientEventEnvelope):
    event_name: Literal["living_loop_immediate_result_viewed"]
    properties: ChoiceProperties


class DelayedResultViewedEvent(_ClientEventEnvelope):
    event_name: Literal["living_loop_delayed_result_viewed"]
    properties: ChoiceProperties


class EnterTownClickedEvent(_ClientEventEnvelope):
    event_name: Literal["living_loop_enter_town_clicked"]
    properties: EnterTownProperties


class CityPulseOpenedEvent(_ClientEventEnvelope):
    event_name: Literal["living_loop_city_pulse_opened"]
    properties: CityPulseProperties


ClientProductEvent = Annotated[
    TodayViewedEvent
    | DecisionViewedEvent
    | ChoicePreviewedEvent
    | ImmediateResultViewedEvent
    | DelayedResultViewedEvent
    | EnterTownClickedEvent
    | CityPulseOpenedEvent,
    Field(discriminator="event_name"),
]


class ProductEventBatchRequest(_StrictModel):
    events: list[ClientProductEvent] = Field(min_length=1, max_length=20)


class ProductEventBatchResponse(_StrictModel):
    accepted: int
    duplicates: int


def _inline_openapi_schema(model: type[BaseModel]) -> dict:
    """Inline Pydantic ``$defs`` so operation-local OpenAPI refs resolve."""

    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def resolve(node, stack: frozenset[str] = frozenset()):
        if isinstance(node, list):
            return [resolve(item, stack) for item in node]
        if not isinstance(node, dict):
            return node
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            name = reference.removeprefix("#/$defs/")
            if name in stack or name not in definitions:
                raise RuntimeError(f"Unresolvable Product Event schema ref: {reference}")
            replacement = deepcopy(definitions[name])
            replacement.update({key: value for key, value in node.items() if key != "$ref"})
            return resolve(replacement, stack | {name})
        resolved = {key: resolve(value, stack) for key, value in node.items()}
        discriminator = resolved.get("discriminator")
        if isinstance(discriminator, dict):
            # The mapping values are URI strings and cannot point into an
            # operation-local $defs block after inlining. ``propertyName`` plus
            # the const discriminator in each oneOf branch is sufficient.
            discriminator.pop("mapping", None)
        return resolved

    return resolve(schema)


def _as_service_input(event: ClientProductEvent) -> ProductEventInput:
    return ProductEventInput(
        event_id=event.event_id,
        session_id=event.session_id,
        event_name=event.event_name,
        properties=event.properties.model_dump(mode="json"),
        client_occurred_at=event.client_occurred_at,
    )


@router.post(
    "/batch",
    response_model=ProductEventBatchResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": _inline_openapi_schema(ProductEventBatchRequest),
                },
            },
        },
    },
)
@limiter.limit(f"{PRODUCT_EVENTS_RATE_LIMIT_PER_MINUTE}/minute")
async def ingest_product_events(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ProductEventBatchResponse:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")
    user = await get_current_user(db, auth.removeprefix("Bearer ").strip())
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if not settings.living_loop_p0_enabled:
        raise HTTPException(status_code=404, detail="feature_disabled")

    media_type = request.headers.get("Content-Type", "").split(";", 1)[0].lower()
    if media_type != "application/json":
        raise HTTPException(status_code=415, detail="application/json required")
    try:
        body = ProductEventBatchRequest.model_validate(await request.json())
    except (JSONDecodeError, UnicodeDecodeError, ValidationError, ValueError):
        # Pydantic's default error includes the rejected input. Product Event
        # bodies may contain forbidden secrets, so this boundary intentionally
        # emits a stable error code without echoing any request value.
        raise HTTPException(
            status_code=422,
            detail="invalid_product_event_batch",
        ) from None

    try:
        result = await persist_product_events(
            db,
            user_id=user.id,
            events=[_as_service_input(event) for event in body.events],
        )
    except ProductEventIdempotencyConflict:
        raise HTTPException(status_code=409, detail="idempotency_conflict") from None

    return ProductEventBatchResponse(
        accepted=result.accepted,
        duplicates=result.duplicates,
    )
