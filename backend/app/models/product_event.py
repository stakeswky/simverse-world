"""Privacy-bounded first-party product events for Living Loop P0."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductEvent(Base):
    """An append-only, idempotent event with no free-text product payload."""

    __tablename__ = "product_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_product_events_event_id"),
        CheckConstraint(
            "event_name IN ("
            "'living_loop_today_viewed',"
            "'living_loop_decision_viewed',"
            "'living_loop_choice_previewed',"
            "'living_loop_immediate_result_viewed',"
            "'living_loop_delayed_result_viewed',"
            "'living_loop_enter_town_clicked',"
            "'living_loop_city_pulse_opened',"
            "'living_loop_choice_confirmed',"
            "'living_loop_result_settled',"
            "'living_loop_result_first_viewed'"
            ")",
            name="ck_product_events_name",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    event_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    properties_json: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    client_occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
