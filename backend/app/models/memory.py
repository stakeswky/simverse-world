import uuid
from datetime import datetime, UTC
from sqlalchemy import String, Text, Float, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    resident_id: Mapped[str] = mapped_column(String, ForeignKey("residents.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # "event", "relationship", "reflection"
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    source: Mapped[str] = mapped_column(String(20))  # "chat_player", "chat_resident", "observation", "reflection", "media"

    # Relationship pointers (nullable)
    related_resident_id: Mapped[str | None] = mapped_column(String, ForeignKey("residents.id"), nullable=True)
    related_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)

    # Media (nullable, for P2 multimodal)
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Embedding (nullable — only event memories get embeddings)
    # pgvector column is added via migration; in SQLite tests this is just None
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)

    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_memories_resident_type", "resident_id", "type"),
        Index("ix_memories_resident_related_resident", "resident_id", "related_resident_id"),
        Index("ix_memories_resident_related_user", "resident_id", "related_user_id"),
    )
