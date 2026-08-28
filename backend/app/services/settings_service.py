"""
Settings business logic.

Handles deep-merging settings_json, password changes, account deletion,
and LLM connection testing.
"""
from __future__ import annotations

import copy
import json
import time
from typing import Any

import httpx

from app.http import get_client
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.resident import Resident
from app.services.auth_service import hash_password, verify_password
from app.services.url_guard import ensure_url_is_public, UnsafeURLError


# ─── settings_json Helpers ────────────────────────────────────────

def build_settings_defaults() -> dict:
    """Return the canonical default structure for User.settings_json."""
    return {
        "interaction": {
            "offline_auto_reply": False,
            "notification_chat": True,
            "notification_system": True,
        },
        "privacy": {
            "map_visible": True,
            "persona_visibility": "full",
            "allow_conversation_stats": True,
        },
        "economy": {
            "low_balance_alert": 10,
        },
        "llm": {
            "thinking_enabled": False,
            "temperature": 0.7,
        },
    }


def merge_settings_json(existing: dict, patch: dict) -> dict:
    """
    Deep-merge *patch* into a copy of *existing*.
    Only merges one level deep (group -> key): group values that are dicts
    are merged; scalar values are overwritten.
    """
    result = copy.deepcopy(existing)
    for group, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(group), dict):
            result[group].update(value)
        else:
            result[group] = value
    return result


def coerce_settings_json(raw: Any) -> dict:
    """Normalize a raw ``User.settings_json`` value into a dict.

    On real Postgres the column is physically ``text`` (historical drift from
    migration 003) while the model declares ``JSON``; under asyncpg the value
    comes back as an *unparsed* JSON string rather than a dict, so a bare
    ``.items()`` on it 500s. This only reproduces on real PG (sqlite deserializes
    it), which is why it slipped past unit tests. Parse defensively so every read
    path gets a dict regardless of the underlying column type.
    """
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return raw if isinstance(raw, dict) else {}


def get_effective_settings(user: User) -> dict:
    """Return settings_json with defaults filled in for missing keys."""
    defaults = build_settings_defaults()
    return merge_settings_json(defaults, coerce_settings_json(user.settings_json))


# ─── Account Operations ──────────────────────────────────────────

async def change_display_name(db: AsyncSession, user: User, new_name: str) -> User:
    """Update user display name."""
    if not new_name or len(new_name.strip()) == 0:
        raise HTTPException(status_code=422, detail="Display name cannot be empty")
    if len(new_name) > 100:
        raise HTTPException(status_code=422, detail="Display name too long (max 100)")
    user.name = new_name.strip()
    await db.commit()
    await db.refresh(user)
    return user


async def change_password(
    db: AsyncSession, user: User, old_password: str, new_password: str
) -> None:
    """Change password for email-registered users only."""
    if not user.hashed_password:
        raise HTTPException(
            status_code=400,
            detail="Cannot change password for OAuth-only accounts",
        )
    if not verify_password(old_password, user.hashed_password):
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    user.hashed_password = hash_password(new_password)
    await db.commit()


async def delete_account(db: AsyncSession, user: User, confirm_email: str) -> None:
    """
    Permanently delete user account.
    Requires the user to confirm by typing their email.
    Cascading: sets creator_id=NULL on owned residents (they become orphaned NPCs).

    Every table with a NOT NULL FK to users.id must be cleaned up here first,
    otherwise the final DELETE hits an IntegrityError on Postgres and the whole
    request 500s (P1 fix, 2026-07-23 production test round). SQLite dev doesn't
    enforce FKs by default, which is why this only broke in production.
    """
    if confirm_email != user.email:
        raise HTTPException(
            status_code=400,
            detail="Email confirmation does not match",
        )

    from sqlalchemy import delete as sa_delete, update as sa_update

    from app.models.conversation import Conversation, Message
    from app.models.forge_session import ForgeSession
    from app.models.living_loop_day import LivingLoopDay
    from app.models.memory import Memory
    from app.models.pending_message import PendingMessage
    from app.models.product_event import ProductEvent
    from app.models.transaction import Transaction

    # 1. Chat history: messages hang off conversations, so children first.
    conv_ids = (
        await db.execute(
            select(Conversation.id).where(Conversation.user_id == user.id)
        )
    ).scalars().all()
    if conv_ids:
        await db.execute(
            sa_delete(Message).where(Message.conversation_id.in_(conv_ids))
        )
        await db.execute(
            sa_delete(Conversation).where(Conversation.id.in_(conv_ids))
        )

    # 2. User-owned rows with NOT NULL FKs to users.id.
    await db.execute(sa_delete(Transaction).where(Transaction.user_id == user.id))
    await db.execute(sa_delete(ForgeSession).where(ForgeSession.user_id == user.id))
    # Living Loop records and analytics use stable pseudonymous user ids. Delete
    # both explicitly for privacy and for SQLite/test environments where FK
    # cascade enforcement may be disabled.
    await db.execute(sa_delete(ProductEvent).where(ProductEvent.user_id == user.id))
    await db.execute(sa_delete(LivingLoopDay).where(LivingLoopDay.user_id == user.id))
    await db.execute(
        sa_delete(PendingMessage).where(
            (PendingMessage.sender_id == user.id)
            | (PendingMessage.recipient_id == user.id)
        )
    )

    # 3. Nullable references: detach instead of delete.
    await db.execute(
        sa_update(Memory)
        .where(Memory.related_user_id == user.id)
        .values(related_user_id=None)
    )

    # 4. Orphan any residents created by this user (creator_id is nullable
    #    since migration 040; they stay in the world as ownerless NPCs).
    await db.execute(
        sa_update(Resident)
        .where(Resident.creator_id == user.id)
        .values(creator_id=None)
    )

    await db.delete(user)
    await db.commit()


# ─── Character Operations ────────────────────────────────────────

async def get_player_resident(db: AsyncSession, user: User) -> Resident | None:
    """Fetch the user's player resident, if bound."""
    if not user.player_resident_id:
        return None
    result = await db.execute(
        select(Resident).where(Resident.id == user.player_resident_id)
    )
    return result.scalar_one_or_none()


async def update_character(
    db: AsyncSession,
    resident: Resident,
    name: str | None = None,
    sprite_key: str | None = None,
) -> Resident:
    """Update character name and/or sprite."""
    if name is not None:
        if not name.strip():
            raise HTTPException(status_code=422, detail="Character name cannot be empty")
        if len(name) > 100:
            raise HTTPException(status_code=422, detail="Character name too long (max 100)")
        resident.name = name.strip()
    if sprite_key is not None:
        resident.sprite_key = sprite_key
    await db.commit()
    await db.refresh(resident)
    return resident


async def update_persona(
    db: AsyncSession,
    resident: Resident,
    ability_md: str,
    persona_md: str,
    soul_md: str,
) -> Resident:
    """Replace all 3 persona layers."""
    resident.ability_md = ability_md
    resident.persona_md = persona_md
    resident.soul_md = soul_md
    await db.commit()
    await db.refresh(resident)
    return resident


# ─── Interaction / Privacy / Economy — settings_json patches ─────

async def patch_settings_group(
    db: AsyncSession,
    user: User,
    group: str,
    updates: dict[str, Any],
) -> dict:
    """
    Patch a single group inside settings_json.
    Also handles reply_mode which lives on Resident, not settings_json.
    """
    current = coerce_settings_json(user.settings_json)
    patched = merge_settings_json(current, {group: updates})
    user.settings_json = patched
    await db.commit()
    await db.refresh(user)
    return get_effective_settings(user)


async def update_reply_mode(
    db: AsyncSession, resident: Resident, mode: str
) -> None:
    """Update reply_mode on the player's Resident record."""
    resident.reply_mode = mode
    await db.commit()


# ─── LLM Operations ──────────────────────────────────────────────

async def update_llm_settings(
    db: AsyncSession,
    user: User,
    *,
    custom_llm_enabled: bool | None = None,
    api_format: str | None = None,
    api_base_url: str | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
    thinking_enabled: bool | None = None,
    temperature: float | None = None,
) -> User:
    """Update custom LLM fields on User + advanced settings in settings_json."""
    if custom_llm_enabled is not None:
        user.custom_llm_enabled = custom_llm_enabled
    if api_format is not None:
        user.custom_llm_api_format = api_format
    if api_base_url is not None:
        if api_base_url:  # empty string clears the custom URL — always allowed
            try:
                await ensure_url_is_public(api_base_url)
            except UnsafeURLError as e:
                raise HTTPException(status_code=400, detail=f"Invalid base URL: {e}")
        user.custom_llm_base_url = api_base_url
    if api_key is not None:
        user.custom_llm_api_key = api_key
    if model_name is not None:
        user.custom_llm_model = model_name

    # Advanced settings go into settings_json.llm
    llm_patch: dict[str, Any] = {}
    if thinking_enabled is not None:
        llm_patch["thinking_enabled"] = thinking_enabled
    if temperature is not None:
        llm_patch["temperature"] = temperature
    if llm_patch:
        current = coerce_settings_json(user.settings_json)
        user.settings_json = merge_settings_json(current, {"llm": llm_patch})

    await db.commit()
    await db.refresh(user)
    return user


async def test_llm_connection(
    api_format: str,
    api_base_url: str,
    api_key: str,
    model_name: str,
) -> dict:
    """
    Test a custom LLM endpoint by sending a minimal chat completion request.
    Returns {success, latency_ms, model_response?, error?}.
    """
    try:
        await ensure_url_is_public(api_base_url)
    except UnsafeURLError as e:
        return {"success": False, "error": f"Blocked URL: {e}"}

    headers: dict[str, str] = {
        "Content-Type": "application/json",
    }

    if api_format == "openai":
        url = f"{api_base_url.rstrip('/')}/v1/chat/completions"
        headers["Authorization"] = f"Bearer {api_key}"
        body = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Say 'connection ok' in 3 words or fewer."}],
            "max_tokens": 20,
        }
    else:  # anthropic
        url = f"{api_base_url.rstrip('/')}/v1/messages"
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        body = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Say 'connection ok' in 3 words or fewer."}],
            "max_tokens": 20,
        }

    start = time.monotonic()
    try:
        resp = await get_client().post(url, json=body, headers=headers, timeout=15.0)
        latency_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code >= 400:
            return {
                "success": False,
                "latency_ms": latency_ms,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }

        data = resp.json()
        # Extract text from response
        if api_format == "openai":
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        else:
            content_blocks = data.get("content", [])
            text = content_blocks[0].get("text", "") if content_blocks else ""

        return {
            "success": True,
            "latency_ms": latency_ms,
            "model_response": text.strip(),
        }
    except httpx.TimeoutException:
        return {"success": False, "error": "Connection timed out (15s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}
