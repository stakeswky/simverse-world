"""Offline message queue for player-to-player chat."""
import uuid
from datetime import datetime, UTC
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PendingMessage(Base):
    __tablename__ = "pending_messages"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    sender_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), index=True
    )
    recipient_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    is_auto_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
