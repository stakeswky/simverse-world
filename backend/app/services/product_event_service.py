"""Transactional persistence for the privacy-bounded Product Event ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.living_loop_day import LivingLoopDay
from app.models.product_event import ProductEvent


class ProductEventIdempotencyConflict(Exception):
    """An event id was reused with a different privacy-safe binding."""


@dataclass(frozen=True, slots=True)
class ProductEventInput:
    event_id: str
    session_id: str | None
    event_name: str
    properties: dict[str, Any]
    client_occurred_at: datetime | None

    @property
    def idempotency_binding(self) -> tuple[Any, ...]:
        # client_occurred_at is deliberately diagnostic-only and is not part
        # of the frozen idempotency binding in EVENT_TAXONOMY.
        return (
            self.event_name,
            self.session_id,
            self.properties,
        )


@dataclass(frozen=True, slots=True)
class ProductEventWriteResult:
    accepted: int
    duplicates: int


def _stored_binding(row: ProductEvent) -> tuple[Any, ...]:
    return (
        row.event_name,
        row.session_id,
        row.properties_json,
    )


def _deduplicate_batch(
    events: list[ProductEventInput],
) -> tuple[dict[str, ProductEventInput], int]:
    unique: dict[str, ProductEventInput] = {}
    duplicates = 0
    for event in events:
        previous = unique.get(event.event_id)
        if previous is None:
            unique[event.event_id] = event
            continue
        if previous.idempotency_binding != event.idempotency_binding:
            raise ProductEventIdempotencyConflict
        duplicates += 1
    return unique, duplicates


async def persist_product_events(
    db: AsyncSession,
    *,
    user_id: str,
    events: list[ProductEventInput],
) -> ProductEventWriteResult:
    """Persist one validated batch atomically.

    The pre-read makes ordinary retries cheap. The unique ``event_id``
    constraint remains authoritative: if another request wins after our read,
    the transaction rolls back and the complete batch is classified again.
    Each unique-constraint race makes at least one previously missing id
    visible, so ``len(unique) + 1`` attempts is a finite convergence bound.
    """

    unique, batch_duplicates = _deduplicate_batch(events)
    event_ids = list(unique)
    last_integrity_error: IntegrityError | None = None

    for _ in range(len(unique) + 1):
        reserved_choice_keys = set((await db.execute(
            select(LivingLoopDay.choice_idempotency_key).where(
                LivingLoopDay.choice_idempotency_key.in_(event_ids)
            )
        )).scalars())
        if reserved_choice_keys:
            await db.rollback()
            raise ProductEventIdempotencyConflict

        rows = (
            await db.execute(
                select(ProductEvent).where(ProductEvent.event_id.in_(event_ids))
            )
        ).scalars().all()
        existing = {row.event_id: row for row in rows}

        for event_id, row in existing.items():
            candidate = unique[event_id]
            if (
                row.user_id != user_id
                or _stored_binding(row) != candidate.idempotency_binding
            ):
                await db.rollback()
                raise ProductEventIdempotencyConflict

        missing = [
            event for event_id, event in unique.items() if event_id not in existing
        ]
        received_at = datetime.now(UTC)
        for event in missing:
            db.add(ProductEvent(
                event_id=event.event_id,
                user_id=user_id,
                session_id=event.session_id,
                event_name=event.event_name,
                properties_json=event.properties,
                occurred_at=received_at,
                client_occurred_at=event.client_occurred_at,
                created_at=received_at,
            ))

        try:
            await db.commit()
        except IntegrityError as exc:
            last_integrity_error = exc
            await db.rollback()
            continue

        return ProductEventWriteResult(
            accepted=len(missing),
            duplicates=batch_duplicates + len(existing),
        )

    # Unexpected database constraint failures must remain server errors rather
    # than being mislabeled as an idempotency conflict.
    assert last_integrity_error is not None
    raise last_integrity_error
