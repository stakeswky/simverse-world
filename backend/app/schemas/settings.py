"""Pydantic schemas for all 6 user settings groups."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


# ─── Account (9.1) ───────────────────────────────────────────────

class AccountUpdateRequest(BaseModel):
    display_name: str | None = None


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)


class AccountSettingsResponse(BaseModel):
    display_name: str
    email: str
    has_password: bool
    github_bound: bool
    linuxdo_bound: bool
    linuxdo_trust_level: int | None


# ─── Character (9.2) ─────────────────────────────────────────────

class CharacterUpdateRequest(BaseModel):
    name: str | None = None
    sprite_key: str | None = None


class PersonaUpdateRequest(BaseModel):
    ability_md: str
    persona_md: str
    soul_md: str


class CharacterSettingsResponse(BaseModel):
    resident_id: str
    name: str
    sprite_key: str
    portrait_url: str | None
    ability_md: str
    persona_md: str
    soul_md: str

    model_config = {"from_attributes": True}


# ─── Interaction (9.3) ───────────────────────────────────────────

class InteractionUpdateRequest(BaseModel):
    reply_mode: Literal["manual", "auto"] | None = None
    offline_auto_reply: bool | None = None
    notification_chat: bool | None = None
    notification_system: bool | None = None


# ─── Privacy (9.4) ───────────────────────────────────────────────

class PrivacyUpdateRequest(BaseModel):
    map_visible: bool | None = None
    persona_visibility: Literal["full", "identity_card_only", "hidden"] | None = None
    allow_conversation_stats: bool | None = None


# ─── LLM (9.5) ───────────────────────────────────────────────────

class LLMUpdateRequest(BaseModel):
    custom_llm_enabled: bool | None = None
    api_format: Literal["openai", "anthropic"] | None = None
    api_base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    thinking_enabled: bool | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class LLMTestRequest(BaseModel):
    api_format: Literal["openai", "anthropic"]
    api_base_url: str
    api_key: str
    model_name: str


class LLMTestResponse(BaseModel):
    success: bool
    latency_ms: int | None = None
    model_response: str | None = None
    error: str | None = None


# ─── Economy (9.6) ───────────────────────────────────────────────

class EconomyUpdateRequest(BaseModel):
    low_balance_alert: int | None = Field(default=None, ge=0)


# ─── Composite ───────────────────────────────────────────────────

class AllSettingsResponse(BaseModel):
    account: AccountSettingsResponse
    character: CharacterSettingsResponse | None
    interaction: dict
    privacy: dict
    llm: dict
    economy: dict
