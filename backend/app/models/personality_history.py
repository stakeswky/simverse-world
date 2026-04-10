import uuid
from datetime import datetime, UTC
from sqlalchemy import String, Text, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PersonalityHistory(Base):
    __tablename__ = "personality_history"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    resident_id: Mapped[str] = mapped_column(
        String, ForeignKey("residents.id"), index=True, nullable=False
    )
    trigger_type: Mapped[str] = mapped_column(
        String(10), nullable=False  # "drift" or "shift"
    )
    # FK to memories.id — nullable because drift is not triggered by a single memory
    trigger_memory_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("memories.id"), nullable=True
    )
    # {"So1": {"from": "L", "to": "M"}, "E2": {"from": "M", "to": "H"}}
    changes_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    old_type: Mapped[str] = mapped_column(String(20), nullable=False)
    new_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_personality_history_resident_created", "resident_id", "created_at"),
        Index("ix_personality_history_trigger_type", "resident_id", "trigger_type"),
    )
