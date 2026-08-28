"""Privacy-safe aggregate product metrics for Living Loop P0."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import median

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.living_loop_day import LivingLoopDay
from app.models.product_event import ProductEvent
from app.models.user import User
from app.routers.admin.middleware import require_admin

router = APIRouter(prefix="/product-metrics", tags=["admin-product-metrics"])

_DEFAULT_WINDOW = timedelta(days=30)
_MAX_WINDOW = timedelta(days=90)
_RETURN_WINDOW = timedelta(hours=48)
_CHOICE_KEYS = (
    "public_support",
    "private_mediation",
    "collect_evidence",
)


def _as_utc(value: datetime) -> datetime:
    """Normalize database datetimes, including SQLite's naive UTC values."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _query_datetime(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail=f"{name} must include a UTC offset",
        )
    return value.astimezone(UTC)


def _resolve_window(
    from_value: datetime | None,
    to_value: datetime | None,
    generated_at: datetime,
) -> tuple[datetime, datetime]:
    start = _query_datetime(from_value, "from")
    end = _query_datetime(to_value, "to")

    if start is None and end is None:
        end = generated_at
        start = end - _DEFAULT_WINDOW
    elif start is None:
        assert end is not None
        start = end - _DEFAULT_WINDOW
    elif end is None:
        end = generated_at

    if start >= end:
        raise HTTPException(status_code=422, detail="from must be before to")
    if end - start > _MAX_WINDOW:
        raise HTTPException(
            status_code=422,
            detail="metrics window cannot exceed 90 days",
        )
    return start, end


def _iso_utc(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


async def _unique_event_users(
    db: AsyncSession,
    event_name: str,
    start: datetime,
    end: datetime,
) -> int:
    value = await db.scalar(
        select(func.count(func.distinct(ProductEvent.user_id))).where(
            ProductEvent.event_name == event_name,
            ProductEvent.occurred_at >= start,
            ProductEvent.occurred_at < end,
        )
    )
    return int(value or 0)


async def _event_count(
    db: AsyncSession,
    event_name: str,
    start: datetime,
    end: datetime,
) -> int:
    value = await db.scalar(
        select(func.count(ProductEvent.id)).where(
            ProductEvent.event_name == event_name,
            ProductEvent.occurred_at >= start,
            ProductEvent.occurred_at < end,
        )
    )
    return int(value or 0)


@router.get("/living-loop-p0")
async def get_living_loop_p0_metrics(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """Return the aggregate P0 funnel without identities or event payloads."""
    generated_at = datetime.now(UTC)
    start, end = _resolve_window(from_, to, generated_at)

    today_unique_users = await _unique_event_users(
        db, "living_loop_today_viewed", start, end
    )
    decision_viewed_unique_users = await _unique_event_users(
        db, "living_loop_decision_viewed", start, end
    )
    choice_confirmed_unique_users = await _unique_event_users(
        db, "living_loop_choice_confirmed", start, end
    )
    settled_result_count = await _event_count(
        db, "living_loop_result_settled", start, end
    )
    delayed_result_viewed_unique_users = await _unique_event_users(
        db, "living_loop_result_first_viewed", start, end
    )

    result = await db.execute(
        select(
            LivingLoopDay.user_id,
            LivingLoopDay.choice_key,
            LivingLoopDay.first_viewed_at,
            LivingLoopDay.choice_confirmed_at,
            LivingLoopDay.result_available_at,
            LivingLoopDay.result_viewed_at,
        ).where(
            LivingLoopDay.experiment_key == "living_loop_p0",
            LivingLoopDay.choice_confirmed_at.is_not(None),
            LivingLoopDay.choice_confirmed_at >= start,
            LivingLoopDay.choice_confirmed_at < end,
        )
    )
    confirmed_decisions = result.all()

    choice_seconds: list[float] = []
    choice_counts = {choice_key: 0 for choice_key in _CHOICE_KEYS}
    mature_decision_count = 0
    returning_decision_count = 0
    maturity_cutoff = end - _RETURN_WINDOW

    for (
        user_id,
        choice_key,
        first_viewed_at,
        choice_confirmed_at,
        result_available_at,
        result_viewed_at,
    ) in confirmed_decisions:
        if choice_key in choice_counts:
            choice_counts[choice_key] += 1

        if choice_confirmed_at is None:
            continue
        confirmed_at = _as_utc(choice_confirmed_at)

        if first_viewed_at is not None:
            seconds = (confirmed_at - _as_utc(first_viewed_at)).total_seconds()
            if seconds >= 0:
                choice_seconds.append(seconds)

        if confirmed_at > maturity_cutoff:
            continue
        mature_decision_count += 1
        if result_available_at is None or result_viewed_at is None:
            continue
        available_at = _as_utc(result_available_at)
        viewed_at = _as_utc(result_viewed_at)
        if available_at <= viewed_at <= confirmed_at + _RETURN_WINDOW:
            returning_decision_count += 1

    choice_total = sum(choice_counts.values())

    return {
        "window": {
            "from": _iso_utc(start),
            "to": _iso_utc(end),
        },
        "generated_at": _iso_utc(generated_at),
        "today_unique_users": today_unique_users,
        "decision_viewed_unique_users": decision_viewed_unique_users,
        "choice_confirmed_unique_users": choice_confirmed_unique_users,
        "choice_completion_rate": (
            choice_confirmed_unique_users / decision_viewed_unique_users
            if decision_viewed_unique_users
            else None
        ),
        "settled_result_count": settled_result_count,
        "delayed_result_viewed_unique_users": delayed_result_viewed_unique_users,
        "return_within_48h_rate": (
            returning_decision_count / mature_decision_count
            if mature_decision_count
            else None
        ),
        "median_choice_seconds": (
            float(median(choice_seconds)) if choice_seconds else None
        ),
        "choice_distribution": [
            {
                "choice_key": choice_key,
                "count": choice_counts[choice_key],
                "share": (
                    choice_counts[choice_key] / choice_total
                    if choice_total
                    else 0.0
                ),
            }
            for choice_key in _CHOICE_KEYS
        ],
    }
