from pydantic import BaseModel
from typing import Literal


class StartChat(BaseModel):
    type: Literal["start_chat"] = "start_chat"
    resident_slug: str


class ChatMsg(BaseModel):
    type: Literal["chat_msg"] = "chat_msg"
    text: str


class EndChat(BaseModel):
    type: Literal["end_chat"] = "end_chat"
