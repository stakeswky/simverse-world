"""Shared fixtures for the Living Loop P0 red-contract tests.

This module deliberately contains no tests of its own.  Keeping the data
builders here makes the API, analytics, and concurrency contracts readable
without adding production-only test hooks.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.resident import Resident
from app.models.user import User
from app.services.auth_service import create_token


async def create_user(
    db,
    label: str,
    *,
    is_admin: bool = False,
    with_resident: bool = True,
) -> tuple[User, Resident | None]:
    user = User(
        name=f"Living Loop {label}",
        email=f"living-loop-{label}@example.test",
        is_admin=is_admin,
        soul_coin_balance=137,
    )
    db.add(user)
    await db.flush()

    resident = None
    if with_resident:
        resident = Resident(
            slug=f"living-loop-{label}",
            name=f"居民 {label}",
            creator_id=user.id,
            district="harbor",
            status="idle",
            resident_type="player",
            sprite_key="伊莎贝拉",
        )
        db.add(resident)
        await db.flush()
        user.player_resident_id = resident.id

    await db.commit()
    return user, resident


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(user.id)}"}


def event_payload(
    event_id: str,
    event_name: str = "living_loop_today_viewed",
    *,
    properties: dict | None = None,
    session_id: str | None = None,
    client_occurred_at: datetime | None = None,
) -> dict:
    if properties is None:
        properties = (
            {"surface_version": 1, "entry_point": "direct"}
            if event_name == "living_loop_today_viewed"
            else {}
        )
    event = {
        "event_id": event_id,
        "session_id": session_id,
        "event_name": event_name,
        "properties": properties,
    }
    if client_occurred_at is not None:
        event["client_occurred_at"] = client_occurred_at.astimezone(UTC).isoformat()
    return {"events": [event]}


def utc_now() -> datetime:
    return datetime.now(UTC)
