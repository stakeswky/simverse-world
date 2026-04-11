import uuid
from datetime import datetime, UTC
from sqlalchemy import String, Integer, Float, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Resident(Base):
    __tablename__ = "residents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    district: Mapped[str] = mapped_column(String(50), default="free")
    status: Mapped[str] = mapped_column(String(20), default="idle")
    heat: Mapped[int] = mapped_column(Integer, default=0)
    model_tier: Mapped[str] = mapped_column(String(20), default="standard")
    token_cost_per_turn: Mapped[int] = mapped_column(Integer, default=1)
    creator_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    ability_md: Mapped[str] = mapped_column(Text, default="")
    persona_md: Mapped[str] = mapped_column(Text, default="")
    soul_md: Mapped[str] = mapped_column(Text, default="")
    meta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    versions_json: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    sprite_key: Mapped[str] = mapped_column(String(100), default="伊莎贝拉")
    tile_x: Mapped[int] = mapped_column(Integer, default=76)  # Default spawn: Central Plaza
    tile_y: Mapped[int] = mapped_column(Integer, default=50)
    star_rating: Mapped[int] = mapped_column(Integer, default=1)
    total_conversations: Mapped[int] = mapped_column(Integer, default=0)
    avg_rating: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_conversation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_vector: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- New fields (Plan 1: Foundation) ---
    resident_type: Mapped[str] = mapped_column(String(20), default="npc")
    reply_mode: Mapped[str] = mapped_column(String(20), default="manual")
    portrait_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Agent fields (P3: Agent Loop) ---
    home_tile_x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_tile_y: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Agent Planning (Plugin System) ---
    daily_goal_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    daily_plans_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
