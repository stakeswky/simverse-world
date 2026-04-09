from datetime import datetime
from pydantic import BaseModel


class MyResidentItem(BaseModel):
    id: str
    slug: str
    name: str
    district: str
    status: str
    heat: int
    star_rating: int
    total_conversations: int
    avg_rating: float
    sprite_key: str
    meta_json: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MyConversationItem(BaseModel):
    id: str
    resident_id: str
    resident_name: str
    resident_slug: str
    started_at: datetime
    ended_at: datetime | None
    turns: int
    rating: int | None


class MyTransactionItem(BaseModel):
    id: str
    amount: int
    reason: str
    created_at: datetime
