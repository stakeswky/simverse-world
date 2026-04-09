# Chat service: orchestrates coin charging and LLM interaction for chat turns.
# Primary chat logic lives in app/ws/handler.py (WebSocket handler).
# This module provides shared helpers if needed by non-WebSocket consumers.

from sqlalchemy.ext.asyncio import AsyncSession
from app.services.coin_service import charge, reward, get_balance

__all__ = ["charge", "reward", "get_balance"]
