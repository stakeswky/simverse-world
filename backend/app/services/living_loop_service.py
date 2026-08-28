"""Deterministic, durable Living Loop P0 user-domain service.

This module deliberately owns no economy, relationship, challenge, notification,
or digest writes.  The only mutable records are ``living_loop_days`` and the
three server-authoritative ``product_events`` written with their state changes.
"""

from __future__ import annotations

import logging
import re
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import case, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.digest import Digest
from app.models.living_loop_day import LivingLoopDay
from app.models.notification import Notification
from app.models.product_event import ProductEvent
from app.models.resident import Resident
from app.services.digest_service import has_real_digest_body

logger = logging.getLogger(__name__)

EXPERIMENT_KEY = "living_loop_p0"
SCENARIO_KEY = "harbor_wage_dispute_v1"
SCENARIO_VERSION = 1
JOURNEY = {"town_path": "/play", "profile_path": "/profile"}

STATE_PENDING = "pending"
STATE_CHOSEN = "chosen"
STATE_RESULT_READY = "result_ready"
STATE_RESULT_VIEWED = "result_viewed"

EVENT_CHOICE_CONFIRMED = "living_loop_choice_confirmed"
EVENT_RESULT_SETTLED = "living_loop_result_settled"
EVENT_RESULT_FIRST_VIEWED = "living_loop_result_first_viewed"

_FALLBACK_PULSE = {
    "title": "今日村落脉搏",
    "summary": "港口与广场仍在按自己的节奏运转。进入小镇，看看今天正在发生什么。",
}

# Registry v1 is intentionally plain, deterministic data.  The request path
# must never call an LLM, and clients never get to provide effects or prose.
_SCENARIO_V1: dict[str, Any] = {
    "scenario_key": SCENARIO_KEY,
    "scenario_version": SCENARIO_VERSION,
    "title": "港口欠薪风波",
    "context_template": (
        "{player_resident_name} 在港口发现三名工人连续两周没有拿到完整工资。"
        "港口不能停摆，但工人的耐心也接近极限。你需要决定今天先做什么。"
    ),
    "stakes": ["港口不能停摆", "工人耐心接近极限"],
    "choices": {
        "public_support": {
            "key": "public_support",
            "label": "公开站出来支持工人",
            "summary": "直接表明立场，立即回应工人的诉求。",
            "risk": "公开对立可能让谈判更困难",
            "tradeoffs": ["工人信任 +8", "管理方信任 -5", "城市信用 +2"],
            "immediate_result": {
                "title": "决定已经保存",
                "summary": "你公开表明支持工人，他们知道自己的诉求已经被听见。",
                "effects": {
                    "worker_trust_delta": 8,
                    "management_trust_delta": -5,
                    "city_credit_delta": 2,
                },
            },
            "delayed_result": {
                "title": "港口传来新进展",
                "summary": (
                    "工人代表同意出席谈判，但管理方暂时限制了部分港口访问权限。"
                ),
            },
        },
        "private_mediation": {
            "key": "private_mediation",
            "label": "先组织一场私下调解",
            "summary": "先让双方在不公开升级冲突的情况下谈判。",
            "risk": "双方都可能把调解视为拖延",
            "tradeoffs": ["工人信任 +3", "管理方信任 +3", "城市信用 +1"],
            "immediate_result": {
                "title": "决定已经保存",
                "summary": "你组织了一场私下调解，双方暂时回到了谈判桌前。",
                "effects": {
                    "worker_trust_delta": 3,
                    "management_trust_delta": 3,
                    "city_credit_delta": 1,
                },
            },
            "delayed_result": {
                "title": "港口传来新进展",
                "summary": "双方同意建立临时发薪时间表，但历史欠款仍未解决。",
            },
        },
        "collect_evidence": {
            "key": "collect_evidence",
            "label": "先核实排班和欠薪证据",
            "summary": "先建立能够支持后续行动的事实基础。",
            "risk": "短期内工人仍得不到补偿",
            "tradeoffs": ["工人信任 +2", "管理方信任 0", "城市信用 +4"],
            "immediate_result": {
                "title": "决定已经保存",
                "summary": "你开始核对排班、工时与发薪记录，先把事实固定下来。",
                "effects": {
                    "worker_trust_delta": 2,
                    "management_trust_delta": 0,
                    "city_credit_delta": 4,
                },
            },
            "delayed_result": {
                "title": "港口传来新进展",
                "summary": (
                    "核查发现账本与实际排班不符，下一阶段获得“完整审计证据”记录。"
                ),
            },
        },
    },
}


class LivingLoopError(RuntimeError):
    """A safe, structured business error for the HTTP adapter."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def utc_now() -> datetime:
    """Single server-authoritative clock seam for tests and all transitions."""

    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    normalized = _as_utc(value)
    if normalized is None:
        return None
    return normalized.isoformat().replace("+00:00", "Z")


def _scenario_snapshot(resident_name: str) -> dict[str, Any]:
    choices = []
    for choice in _SCENARIO_V1["choices"].values():
        choices.append({
            "key": choice["key"],
            "label": choice["label"],
            "summary": choice["summary"],
            "risk": choice["risk"],
            "tradeoffs": list(choice["tradeoffs"]),
        })
    return {
        "scenario_key": SCENARIO_KEY,
        "scenario_version": SCENARIO_VERSION,
        "title": _SCENARIO_V1["title"],
        "context": _SCENARIO_V1["context_template"].format(
            player_resident_name=resident_name,
        ),
        "stakes": list(_SCENARIO_V1["stakes"]),
        "choices": choices,
    }


def _registry_choice(day: LivingLoopDay, choice_key: str) -> dict[str, Any]:
    if day.scenario_key != SCENARIO_KEY or day.scenario_version != SCENARIO_VERSION:
        raise LivingLoopError(
            500,
            "scenario_registry_missing",
            "The persisted Living Loop scenario version is unavailable.",
        )
    choice = _SCENARIO_V1["choices"].get(choice_key)
    if choice is None:
        raise LivingLoopError(422, "invalid_choice", "Unknown Living Loop choice.")
    return choice


def serialize_decision(day: LivingLoopDay) -> dict[str, Any]:
    """Project only persisted snapshots, with a hard delayed-content gate."""

    snapshot = day.scenario_snapshot_json or {}
    delayed_visible = day.state in {STATE_RESULT_READY, STATE_RESULT_VIEWED}
    return {
        "id": day.id,
        "scenario_key": day.scenario_key,
        "scenario_version": day.scenario_version,
        "state": day.state,
        "title": snapshot.get("title", ""),
        "context": snapshot.get("context", ""),
        "stakes": deepcopy(snapshot.get("stakes") or []),
        "choices": deepcopy(snapshot.get("choices") or []),
        "selected_choice": day.choice_key,
        "immediate_result": deepcopy(day.immediate_result_json)
        if day.choice_key is not None
        else None,
        "result_available_at": _iso(day.result_available_at),
        "delayed_result": deepcopy(day.delayed_result_json)
        if delayed_visible
        else None,
    }


def _player_projection(resident: Resident) -> dict[str, Any]:
    return {
        "id": resident.id,
        "slug": resident.slug,
        "name": resident.name,
        "district": resident.district,
        "sprite_key": resident.sprite_key,
    }


def _base_today(now: datetime, *, enabled: bool, status: str) -> dict[str, Any]:
    return {
        "experiment": {"key": EXPERIMENT_KEY, "enabled": enabled},
        "server_now": _iso(now),
        "status": status,
        "player_resident": None,
        "since_you_left": [],
        "city_pulse": None,
        "decision": None,
        "journey": dict(JOURNEY),
    }


def _dialect_insert(db: AsyncSession, model: type, values: dict[str, Any]):
    name = db.get_bind().dialect.name
    if name == "postgresql":
        return postgresql_insert(model).values(**values)
    if name == "sqlite":
        return sqlite_insert(model).values(**values)
    raise RuntimeError(f"Unsupported Living Loop database dialect: {name}")


async def _insert_day_if_absent(
    db: AsyncSession,
    *,
    user_id: str,
    day_key,
    snapshot: dict[str, Any],
    now: datetime,
) -> None:
    values = {
        "id": str(uuid4()),
        "user_id": user_id,
        "experiment_key": EXPERIMENT_KEY,
        "day_key": day_key,
        "scenario_key": SCENARIO_KEY,
        "scenario_version": SCENARIO_VERSION,
        "state": STATE_PENDING,
        "scenario_snapshot_json": snapshot,
        "choice_key": None,
        "immediate_result_json": None,
        "delayed_result_json": None,
        "first_viewed_at": None,
        "choice_confirmed_at": None,
        "result_available_at": None,
        "result_settled_at": None,
        "result_viewed_at": None,
        "created_at": now,
        "updated_at": now,
    }
    statement = _dialect_insert(db, LivingLoopDay, values).on_conflict_do_nothing(
        index_elements=["user_id", "experiment_key", "day_key"],
    )
    await db.execute(statement)


async def _load_day(
    db: AsyncSession,
    *,
    decision_id: str | None = None,
    user_id: str,
    day_key=None,
) -> LivingLoopDay | None:
    statement = select(LivingLoopDay).where(LivingLoopDay.user_id == user_id)
    if decision_id is not None:
        statement = statement.where(LivingLoopDay.id == decision_id)
    if day_key is not None:
        statement = statement.where(
            LivingLoopDay.experiment_key == EXPERIMENT_KEY,
            LivingLoopDay.day_key == day_key,
        )
    return (await db.execute(
        statement.execution_options(populate_existing=True)
    )).scalar_one_or_none()


def _event_properties(day: LivingLoopDay, choice_key: str | None = None) -> dict[str, Any]:
    return {
        "decision_id": day.id,
        "scenario_key": day.scenario_key,
        "scenario_version": day.scenario_version,
        "choice_key": choice_key if choice_key is not None else day.choice_key,
    }


async def _insert_product_event(
    db: AsyncSession,
    *,
    event_id: str,
    user_id: str,
    event_name: str,
    properties: dict[str, Any],
    occurred_at: datetime,
) -> bool:
    values = {
        "id": str(uuid4()),
        "event_id": event_id,
        "user_id": user_id,
        "session_id": None,
        "event_name": event_name,
        "properties_json": properties,
        "occurred_at": occurred_at,
        "client_occurred_at": None,
        "created_at": occurred_at,
    }
    statement = _dialect_insert(db, ProductEvent, values).on_conflict_do_nothing(
        index_elements=["event_id"],
    )
    result = await db.execute(statement)
    return bool(result.rowcount)


def _stable_event_id(event_name: str, decision_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"simverse-world:{event_name}:{decision_id}"))


async def _write_authoritative_event(
    db: AsyncSession,
    *,
    day: LivingLoopDay,
    event_name: str,
    occurred_at: datetime,
) -> None:
    """Insert or verify a stable server event without permitting split state."""

    event_id = _stable_event_id(event_name, day.id)
    properties = _event_properties(day)
    inserted = await _insert_product_event(
        db,
        event_id=event_id,
        user_id=day.user_id,
        event_name=event_name,
        properties=properties,
        occurred_at=occurred_at,
    )
    if inserted:
        return

    existing = await _load_event(db, event_id)
    if existing is not None and (
        existing.user_id == day.user_id
        and existing.session_id is None
        and existing.event_name == event_name
        and existing.properties_json == properties
    ):
        return

    # The caller's CAS transition is in this same transaction. Roll it back
    # before surfacing a generic conflict so state can never advance without
    # its corresponding authoritative event.
    await db.rollback()
    raise LivingLoopError(
        409,
        "authoritative_event_conflict",
        "The authoritative event identity is unavailable.",
    )


async def _settle_one(
    db: AsyncSession,
    day: LivingLoopDay,
    now: datetime,
) -> bool:
    available = _as_utc(day.result_available_at)
    if day.state != STATE_CHOSEN or available is None or available > now:
        return False
    result = await db.execute(
        update(LivingLoopDay)
        .where(
            LivingLoopDay.id == day.id,
            LivingLoopDay.user_id == day.user_id,
            LivingLoopDay.state == STATE_CHOSEN,
        )
        .values(
            state=STATE_RESULT_READY,
            result_settled_at=now,
            updated_at=now,
        )
    )
    if not result.rowcount:
        return False
    await _write_authoritative_event(
        db,
        day=day,
        event_name=EVENT_RESULT_SETTLED,
        occurred_at=now,
    )
    return True


async def _settle_due_days(db: AsyncSession, user_id: str, now: datetime) -> None:
    # Compare in Python after normalising SQLite's naive DateTime values.  The
    # state transition itself remains a database CAS, so concurrent processes
    # still produce exactly one settlement and one event.
    rows = list((await db.execute(
        select(LivingLoopDay).where(
            LivingLoopDay.user_id == user_id,
            LivingLoopDay.state == STATE_CHOSEN,
            LivingLoopDay.result_available_at.is_not(None),
        )
    )).scalars().all())
    for row in rows:
        await _settle_one(db, row, now)


async def _previous_result_item(
    db: AsyncSession,
    *,
    user_id: str,
    current_id: str,
) -> dict[str, Any] | None:
    row = (await db.execute(
        select(LivingLoopDay)
        .where(
            LivingLoopDay.user_id == user_id,
            LivingLoopDay.id != current_id,
            LivingLoopDay.state.in_([STATE_RESULT_READY, STATE_RESULT_VIEWED]),
            LivingLoopDay.delayed_result_json.is_not(None),
        )
        .order_by(LivingLoopDay.result_settled_at.desc(), LivingLoopDay.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        return None
    delayed = row.delayed_result_json or {}
    return {
        "id": row.id,
        "kind": "previous_result",
        "title": delayed.get("title") or "上一次选择有了结果",
        "summary": delayed.get("summary") or "上一次选择已经出现新的进展。",
        "occurred_at": _iso(row.result_settled_at or row.result_available_at),
        "deep_link": None,
    }


async def _notification_items(db: AsyncSession, user_id: str) -> list[dict[str, Any]]:
    unread_first = case((Notification.read_at.is_(None), 0), else_=1)
    rows = list((await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(unread_first, Notification.created_at.desc(), Notification.id.desc())
        .limit(2)
    )).scalars().all())
    items: list[dict[str, Any]] = []
    for row in rows:
        payload = row.payload_json or {}
        deep_link = payload.get("deep_link")
        if not isinstance(deep_link, str) or not deep_link.startswith("/"):
            deep_link = None
        items.append({
            "id": row.id,
            "kind": "notification",
            "title": row.title,
            "summary": row.body or row.title,
            "occurred_at": _iso(row.created_at),
            "deep_link": deep_link,
        })
    return items


def _digest_summary(content: str, *, limit: int = 220) -> str:
    text = content.strip()
    if text.startswith("#"):
        text = "\n".join(text.splitlines()[1:]).strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


async def _latest_digest(db: AsyncSession) -> Digest | None:
    rows = list((await db.execute(
        select(Digest)
        .where(Digest.scope == "village", Digest.user_id == "")
        .order_by(Digest.date.desc(), Digest.created_at.desc())
        .limit(30)
    )).scalars().all())
    return next(
        (row for row in rows if has_real_digest_body(row.content_md or "")),
        None,
    )


def _digest_item(row: Digest) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": "digest",
        "title": row.title,
        "summary": _digest_summary(row.content_md or ""),
        "occurred_at": _iso(row.created_at),
        "deep_link": "/capsules",
    }


def _city_pulse(row: Digest | None, now: datetime) -> dict[str, Any]:
    if row is None:
        return {
            **_FALLBACK_PULSE,
            "date": now.date().isoformat(),
            "deep_link": "/capsules",
            "is_fallback": True,
        }
    return {
        "title": row.title,
        "summary": _digest_summary(row.content_md or ""),
        "date": row.date.isoformat(),
        "deep_link": "/capsules",
        "is_fallback": False,
    }


async def get_today(db: AsyncSession, user_id: str) -> dict[str, Any]:
    now = utc_now()
    if not settings.living_loop_p0_enabled:
        return _base_today(now, enabled=False, status="feature_disabled")

    # The explicit player binding, not creator ownership, defines the avatar.
    from app.models.user import User

    player_resident_id = (await db.execute(
        select(User.player_resident_id).where(User.id == user_id)
    )).scalar_one_or_none()
    resident = None
    if player_resident_id:
        resident = (await db.execute(
            select(Resident).where(Resident.id == player_resident_id)
        )).scalar_one_or_none()
    if resident is None:
        return _base_today(now, enabled=True, status="setup_required")

    # Authentication and binding reads begin an implicit transaction.  End it
    # before the first SQLite write so concurrent readers do not all try to
    # upgrade the same read transaction into a writer.
    await db.commit()

    day_key = now.date()
    await _insert_day_if_absent(
        db,
        user_id=user_id,
        day_key=day_key,
        snapshot=_scenario_snapshot(resident.name),
        now=now,
    )
    await db.execute(
        update(LivingLoopDay)
        .where(
            LivingLoopDay.user_id == user_id,
            LivingLoopDay.experiment_key == EXPERIMENT_KEY,
            LivingLoopDay.day_key == day_key,
            LivingLoopDay.first_viewed_at.is_(None),
        )
        .values(first_viewed_at=now, updated_at=now)
    )
    await _settle_due_days(db, user_id, now)
    await db.commit()

    day = await _load_day(db, user_id=user_id, day_key=day_key)
    if day is None:  # pragma: no cover - database invariant failure
        raise LivingLoopError(500, "day_unavailable", "Living Loop day is unavailable.")

    result = _base_today(now, enabled=True, status="ready")
    result["player_resident"] = _player_projection(resident)
    result["decision"] = serialize_decision(day)

    # Serialize the core and previous-result data before querying optional
    # sources.  A missing optional table can abort a PostgreSQL transaction;
    # rolling it back must never roll back or hide the already-committed day.
    previous = await _previous_result_item(
        db,
        user_id=user_id,
        current_id=day.id,
    )
    if previous is not None:
        result["since_you_left"].append(previous)

    try:
        result["since_you_left"].extend(
            await _notification_items(db, user_id)
        )
    except Exception:
        await db.rollback()
        logger.warning("Living Loop notification aggregation failed", exc_info=True)

    digest: Digest | None = None
    try:
        digest = await _latest_digest(db)
    except Exception:
        await db.rollback()
        logger.warning("Living Loop digest aggregation failed", exc_info=True)
    if digest is not None:
        result["since_you_left"].append(_digest_item(digest))
    result["city_pulse"] = _city_pulse(digest, now)
    return result


def _event_binding_matches(
    event: ProductEvent,
    *,
    user_id: str,
    decision_id: str,
    choice_key: str,
) -> bool:
    return (
        event.user_id == user_id
        and event.event_name == EVENT_CHOICE_CONFIRMED
        and event.properties_json == {
            "decision_id": decision_id,
            "scenario_key": SCENARIO_KEY,
            "scenario_version": SCENARIO_VERSION,
            "choice_key": choice_key,
        }
    )


async def _load_event(db: AsyncSession, event_id: str) -> ProductEvent | None:
    return (await db.execute(
        select(ProductEvent).where(ProductEvent.event_id == event_id)
    )).scalar_one_or_none()


async def _load_day_by_idempotency_key(
    db: AsyncSession,
    idempotency_key: str,
) -> LivingLoopDay | None:
    return (await db.execute(
        select(LivingLoopDay).where(
            LivingLoopDay.choice_idempotency_key == idempotency_key
        )
    )).scalar_one_or_none()


def _day_idempotency_binding_matches(
    day: LivingLoopDay,
    *,
    user_id: str,
    decision_id: str,
    choice_key: str,
) -> bool:
    return (
        day.user_id == user_id
        and day.id == decision_id
        and day.choice_key == choice_key
    )


async def choose(
    db: AsyncSession,
    *,
    user_id: str,
    decision_id: str,
    choice_key: str,
    idempotency_key: str,
) -> dict[str, Any]:
    if not settings.living_loop_p0_enabled:
        raise LivingLoopError(409, "feature_disabled", "Living Loop is disabled.")

    # Clear the authentication SELECT transaction before the CAS write path.
    await db.commit()
    existing_event = await _load_event(db, idempotency_key)
    if existing_event is not None:
        if not _event_binding_matches(
            existing_event,
            user_id=user_id,
            decision_id=decision_id,
            choice_key=choice_key,
        ):
            raise LivingLoopError(
                409,
                "idempotency_conflict",
                "The idempotency key is already bound to another request.",
            )
        day = await _load_day(db, decision_id=decision_id, user_id=user_id)
        if day is None:
            raise LivingLoopError(404, "decision_not_found", "Decision not found.")
        return {"decision": serialize_decision(day)}

    durable_binding = await _load_day_by_idempotency_key(db, idempotency_key)
    if durable_binding is not None:
        if not _day_idempotency_binding_matches(
            durable_binding,
            user_id=user_id,
            decision_id=decision_id,
            choice_key=choice_key,
        ):
            raise LivingLoopError(
                409,
                "idempotency_conflict",
                "The idempotency key is already bound to another request.",
            )
        return {"decision": serialize_decision(durable_binding)}

    day = await _load_day(db, decision_id=decision_id, user_id=user_id)
    if day is None:
        raise LivingLoopError(404, "decision_not_found", "Decision not found.")
    choice = _registry_choice(day, choice_key)

    if day.state != STATE_PENDING:
        if day.choice_key == choice_key:
            return {"decision": serialize_decision(day)}
        raise LivingLoopError(
            409,
            "choice_conflict",
            "This decision already has a different choice.",
        )

    now = utc_now()
    available_at = now + timedelta(
        seconds=settings.living_loop_p0_delay_seconds,
    )
    immediate = deepcopy(choice["immediate_result"])
    delayed = deepcopy(choice["delayed_result"])
    try:
        changed = await db.execute(
            update(LivingLoopDay)
            .where(
                LivingLoopDay.id == decision_id,
                LivingLoopDay.user_id == user_id,
                LivingLoopDay.state == STATE_PENDING,
                LivingLoopDay.choice_key.is_(None),
            )
            .values(
                state=STATE_CHOSEN,
                choice_key=choice_key,
                choice_idempotency_key=idempotency_key,
                immediate_result_json=immediate,
                delayed_result_json=delayed,
                choice_confirmed_at=now,
                result_available_at=available_at,
                updated_at=now,
            )
        )
    except IntegrityError:
        # A globally unique durable idempotency binding won concurrently.
        await db.rollback()
        changed = None
    if changed is not None and changed.rowcount:
        inserted = await _insert_product_event(
            db,
            event_id=idempotency_key,
            user_id=user_id,
            event_name=EVENT_CHOICE_CONFIRMED,
            properties=_event_properties(day, choice_key),
            occurred_at=now,
        )
        if inserted:
            await db.commit()
            persisted = await _load_day(
                db,
                decision_id=decision_id,
                user_id=user_id,
            )
            if persisted is None:  # pragma: no cover - impossible after CAS
                raise LivingLoopError(500, "decision_unavailable", "Decision unavailable.")
            return {"decision": serialize_decision(persisted)}
        # A concurrent/global event-id collision must undo the day transition.
        await db.rollback()
    else:
        await db.rollback()

    # Re-read after the competing transaction has completed.  Compare the
    # complete persisted event binding before considering same-choice replay.
    existing_event = await _load_event(db, idempotency_key)
    if existing_event is not None and not _event_binding_matches(
        existing_event,
        user_id=user_id,
        decision_id=decision_id,
        choice_key=choice_key,
    ):
        raise LivingLoopError(
            409,
            "idempotency_conflict",
            "The idempotency key is already bound to another request.",
        )
    durable_binding = await _load_day_by_idempotency_key(db, idempotency_key)
    if durable_binding is not None and not _day_idempotency_binding_matches(
        durable_binding,
        user_id=user_id,
        decision_id=decision_id,
        choice_key=choice_key,
    ):
        raise LivingLoopError(
            409,
            "idempotency_conflict",
            "The idempotency key is already bound to another request.",
        )
    persisted = await _load_day(db, decision_id=decision_id, user_id=user_id)
    if persisted is None:
        raise LivingLoopError(404, "decision_not_found", "Decision not found.")
    if persisted.choice_key == choice_key:
        return {"decision": serialize_decision(persisted)}
    raise LivingLoopError(
        409,
        "choice_conflict",
        "This decision already has a different choice.",
    )


async def mark_result_viewed(
    db: AsyncSession,
    *,
    user_id: str,
    decision_id: str,
) -> dict[str, Any]:
    if not settings.living_loop_p0_enabled:
        raise LivingLoopError(409, "feature_disabled", "Living Loop is disabled.")

    await db.commit()
    day = await _load_day(db, decision_id=decision_id, user_id=user_id)
    if day is None:
        raise LivingLoopError(404, "decision_not_found", "Decision not found.")

    now = utc_now()
    if day.state == STATE_PENDING:
        raise LivingLoopError(
            409,
            "result_not_available",
            "The delayed result is not available yet.",
        )
    if day.state == STATE_CHOSEN:
        available = _as_utc(day.result_available_at)
        if available is None or available > now:
            raise LivingLoopError(
                409,
                "result_not_available",
                "The delayed result is not available yet.",
            )
        await _settle_one(db, day, now)
        day = await _load_day(db, decision_id=decision_id, user_id=user_id)
        if day is None:  # pragma: no cover - protected by ownership predicate
            raise LivingLoopError(404, "decision_not_found", "Decision not found.")

    if day.state == STATE_RESULT_VIEWED:
        await db.commit()
        return {"decision": serialize_decision(day)}
    if day.state != STATE_RESULT_READY:
        raise LivingLoopError(
            409,
            "result_not_available",
            "The delayed result is not available yet.",
        )

    viewed = await db.execute(
        update(LivingLoopDay)
        .where(
            LivingLoopDay.id == decision_id,
            LivingLoopDay.user_id == user_id,
            LivingLoopDay.state == STATE_RESULT_READY,
            LivingLoopDay.result_viewed_at.is_(None),
        )
        .values(
            state=STATE_RESULT_VIEWED,
            result_viewed_at=now,
            updated_at=now,
        )
    )
    if viewed.rowcount:
        await _write_authoritative_event(
            db,
            day=day,
            event_name=EVENT_RESULT_FIRST_VIEWED,
            occurred_at=now,
        )
        await db.commit()
    else:
        await db.rollback()

    persisted = await _load_day(db, decision_id=decision_id, user_id=user_id)
    if persisted is None:
        raise LivingLoopError(404, "decision_not_found", "Decision not found.")
    return {"decision": serialize_decision(persisted)}
