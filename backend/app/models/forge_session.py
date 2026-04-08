import uuid
from datetime import datetime, UTC
from sqlalchemy import String, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ForgeSession(Base):
    __tablename__ = "forge_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    character_name: Mapped[str] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(20))  # "quick" | "deep"
    status: Mapped[str] = mapped_column(String(20), default="routing")
    current_stage: Mapped[str] = mapped_column(String(50), default="")
    research_data: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction_data: Mapped[dict] = mapped_column(JSON, default=dict)
    build_output: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_report: Mapped[dict] = mapped_column(JSON, default=dict)
    refinement_log: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
