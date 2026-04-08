from datetime import datetime, UTC
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SystemConfig(Base):
    __tablename__ = "system_config"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[str] = mapped_column(String(2000))
    group: Mapped[str] = mapped_column(String(50), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    updated_by: Mapped[str] = mapped_column(String(100))
