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
