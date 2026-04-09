"""Pydantic schemas for all admin panel endpoints."""
from datetime import datetime
from pydantic import BaseModel


# ── Dashboard ──────────────────────────────────────────────
class DashboardStatsResponse(BaseModel):
    online_users: int
    today_registrations: int
    active_chats: int
    soul_coin_net_flow: int  # today's total issued - total consumed


class DashboardTrendPoint(BaseModel):
    date: str  # "2026-04-07"
    users: int
    conversations: int


class TopResidentItem(BaseModel):
    id: str
    name: str
    slug: str
    heat: int
    district: str
    star_rating: int

    model_config = {"from_attributes": True}


class ServiceHealthItem(BaseModel):
    service: str  # "searxng", "llm_api"
    status: str  # "ok", "error", "timeout"
    latency_ms: int | None = None
    detail: str | None = None


# ── User Management ────────────────────────────────────────
class AdminUserListItem(BaseModel):
    id: str
    name: str
    email: str
    avatar: str | None
    soul_coin_balance: int
    is_admin: bool
    is_banned: bool
    github_id: str | None
    linuxdo_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserDetail(AdminUserListItem):
    linuxdo_trust_level: int | None
    player_resident_id: str | None
    last_x: int
    last_y: int
    settings_json: dict
    custom_llm_enabled: bool
    custom_llm_api_format: str
    custom_llm_base_url: str | None
    custom_llm_model: str | None
    resident_count: int  # number of created residents
    conversation_count: int  # total conversations
    transaction_count: int  # total transactions


class BalanceAdjustRequest(BaseModel):
    amount: int  # positive = add, negative = deduct
    reason: str


class SetAdminRequest(BaseModel):
    is_admin: bool


class SetBanRequest(BaseModel):
    is_banned: bool


class UserPatchRequest(BaseModel):
    """PATCH body for ban/unban and admin toggle."""
    is_banned: bool | None = None
    is_admin: bool | None = None


# ── Resident Management ────────────────────────────────────
class AdminResidentListItem(BaseModel):
    id: str
    slug: str
    name: str
    district: str
    status: str
    heat: int
    star_rating: int
    resident_type: str
    reply_mode: str
    creator_id: str
    total_conversations: int
    avg_rating: float
    created_at: datetime

    model_config = {"from_attributes": True}


class ResidentPersonaEditRequest(BaseModel):
    """Admin can edit any resident's persona layers."""
    ability_md: str | None = None
    persona_md: str | None = None
    soul_md: str | None = None
    district: str | None = None
    status: str | None = None
    resident_type: str | None = None
    reply_mode: str | None = None


class PresetResidentRequest(BaseModel):
    """CRUD for preset characters."""
    slug: str
    name: str
    district: str = "free"
    ability_md: str = ""
    persona_md: str = ""
    soul_md: str = ""
    sprite_key: str = "伊莎贝拉"
    tile_x: int = 76
    tile_y: int = 50
    resident_type: str = "preset"
    reply_mode: str = "auto"
    meta_json: dict | None = None


class BatchDistrictRequest(BaseModel):
    resident_ids: list[str]
    district: str


class BatchStatusResetRequest(BaseModel):
    resident_ids: list[str]
    status: str = "idle"


# ── Forge Monitor ──────────────────────────────────────────
class ForgeSessionListItem(BaseModel):
    id: str
    user_id: str
    character_name: str
    mode: str
    status: str
    current_stage: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ForgeSessionDetail(ForgeSessionListItem):
    research_data: dict
    extraction_data: dict
    build_output: dict
    validation_report: dict
    refinement_log: dict


# ── Economy ────────────────────────────────────────────────
class EconomyStatsResponse(BaseModel):
    total_issued: int  # sum of positive transactions
    total_consumed: int  # sum of negative transactions (absolute value)
    net_circulation: int  # total_issued - total_consumed
    avg_balance: float
    total_users: int


class TransactionLogItem(BaseModel):
    id: str
    user_id: str
    amount: int
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


class EconomyConfigUpdate(BaseModel):
    """Update one or more economy parameters."""
    signup_bonus: int | None = None
    daily_reward: int | None = None
    chat_cost_per_turn: int | None = None
    creator_reward: int | None = None
    rating_bonus: int | None = None


# ── System Config ──────────────────────────────────────────
class ConfigEntry(BaseModel):
    key: str
    value: str  # JSON-serialized
    group: str
    updated_at: datetime
    updated_by: str

    model_config = {"from_attributes": True}


class ConfigGroupResponse(BaseModel):
    group: str
    entries: dict[str, object]  # key -> typed value


class ConfigUpdateRequest(BaseModel):
    """Update a single config key."""
    key: str
    value: object  # will be JSON-serialized
    group: str


class ConfigBatchUpdateRequest(BaseModel):
    """Update multiple config keys at once."""
    updates: list[ConfigUpdateRequest]
