"""Durable daily decisions for the Living Loop P0 product experiment."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LivingLoopDay(Base):
    """One immutable, versioned decision per user and UTC calendar day."""

    __tablename__ = "living_loop_days"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "experiment_key",
            "day_key",
            name="uq_living_loop_day_user_experiment_day",
        ),
        CheckConstraint(
            "experiment_key = 'living_loop_p0'",
            name="ck_living_loop_days_experiment",
        ),
        CheckConstraint(
            "scenario_version = 1",
            name="ck_living_loop_days_scenario_version",
        ),
        CheckConstraint(
            "state IN ('pending','chosen','result_ready','result_viewed')",
            name="ck_living_loop_days_state",
        ),
        CheckConstraint(
            "choice_key IS NULL OR choice_key IN "
            "('public_support','private_mediation','collect_evidence')",
            name="ck_living_loop_days_choice",
        ),
        CheckConstraint(
            "choice_idempotency_key IS NULL OR choice_key IS NOT NULL",
            name="ck_living_loop_days_choice_idempotency",
        ),
        UniqueConstraint(
            "choice_idempotency_key",
            name="uq_living_loop_days_choice_idempotency_key",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    experiment_key: Mapped[str] = mapped_column(
        String(64), nullable=False, default="living_loop_p0"
    )
    day_key: Mapped[date] = mapped_column(Date, nullable=False)
    scenario_key: Mapped[str] = mapped_column(String(100), nullable=False)
    scenario_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    scenario_snapshot_json: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    choice_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    choice_idempotency_key: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    immediate_result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    delayed_result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    first_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    choice_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
