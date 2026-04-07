import json
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}  # user_id -> ws

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active[user_id] = ws

    def disconnect(self, user_id: str):
        self.active.pop(user_id, None)

    async def send(self, user_id: str, data: dict):
        ws = self.active.get(user_id)
        if ws:
            await ws.send_json(data)

    async def broadcast(self, data: dict, exclude: str | None = None):
        for uid, ws in list(self.active.items()):
            if uid != exclude:
                try:
                    await ws.send_json(data)
                except Exception:
                    self.disconnect(uid)


manager = ConnectionManager()
