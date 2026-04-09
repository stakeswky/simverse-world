"""
Settings business logic.

Handles deep-merging settings_json, password changes, account deletion,
and LLM connection testing.
"""
from __future__ import annotations

import copy
import time
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.resident import Resident
from app.services.auth_service import pwd_context


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


def get_effective_settings(user: User) -> dict:
    """Return settings_json with defaults filled in for missing keys."""
    defaults = build_settings_defaults()
    return merge_settings_json(defaults, user.settings_json or {})


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
    if not pwd_context.verify(old_password, user.hashed_password):
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    user.hashed_password = pwd_context.hash(new_password)
    await db.commit()


async def delete_account(db: AsyncSession, user: User, confirm_email: str) -> None:
    """
    Permanently delete user account.
    Requires the user to confirm by typing their email.
    Cascading: sets creator_id=NULL on owned residents (they become orphaned NPCs).
    """
    if confirm_email != user.email:
        raise HTTPException(
            status_code=400,
            detail="Email confirmation does not match",
        )
    # Orphan any residents created by this user
    result = await db.execute(
        select(Resident).where(Resident.creator_id == user.id)
    )
    for resident in result.scalars().all():
        resident.creator_id = None  # type: ignore[assignment]

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
    current = user.settings_json or {}
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
        current = user.settings_json or {}
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
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=body, headers=headers)
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
