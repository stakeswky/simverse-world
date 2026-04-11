"""Base protocol for all agent phase plugins."""
from __future__ import annotations
from typing import Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.schemas import TickContext


@runtime_checkable
class PhasePlugin(Protocol):
    """All phase plugins implement this interface."""

    async def execute(self, ctx: TickContext) -> TickContext:
        """Execute this phase, read/write TickContext and return it."""
        ...
