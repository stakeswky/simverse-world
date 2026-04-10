from pydantic import BaseModel, field_validator
from typing import Literal


class StartChat(BaseModel):
    type: Literal["start_chat"] = "start_chat"
    resident_slug: str
    wake: bool = False  # spend extra coins to wake a sleeping NPC


class ChatMsg(BaseModel):
    type: Literal["chat_msg"] = "chat_msg"
    text: str
    media_url: str | None = None
    media_type: str | None = None  # "image" or "video"; None means plain text


class EndChat(BaseModel):
    type: Literal["end_chat"] = "end_chat"


class RateChat(BaseModel):
    type: Literal["rate_chat"] = "rate_chat"
    rating: int  # 1-5
    conversation_id: str


# --- Player-to-Player Chat (Plan 5) ---


class PlayerChat(BaseModel):
    type: Literal["player_chat"] = "player_chat"
    target_id: str
    text: str

    @field_validator("text")
    @classmethod
    def text_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty")
        return v.strip()


class PlayerChatReply(BaseModel):
    type: Literal["player_chat_reply"] = "player_chat_reply"
    from_id: str
    text: str
    is_auto: bool = False


class SetReplyMode(BaseModel):
    type: Literal["set_reply_mode"] = "set_reply_mode"
    mode: Literal["auto", "manual"]
