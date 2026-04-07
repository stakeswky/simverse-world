import json
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}  # user_id -> ws
        self.positions: dict[str, dict] = {}    # user_id -> {x, y, direction, name}
        self.chatting: dict[str, str] = {}       # resident_id -> user_id (lock)

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active[user_id] = ws

    def disconnect(self, user_id: str):
        self.active.pop(user_id, None)
        self.positions.pop(user_id, None)
        to_remove = [rid for rid, uid in self.chatting.items() if uid == user_id]
        for rid in to_remove:
            del self.chatting[rid]

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

    def update_position(self, user_id: str, x: float, y: float, direction: str, name: str) -> None:
        self.positions[user_id] = {"x": x, "y": y, "direction": direction, "name": name}

    def get_online_players(self, exclude: str | None = None) -> list[dict]:
        return [
            {"player_id": uid, **pos}
            for uid, pos in self.positions.items()
            if uid != exclude
        ]

    def lock_resident(self, resident_id: str, user_id: str) -> bool:
        """Lock resident for chatting. Returns False if already locked by another user."""
        if resident_id in self.chatting and self.chatting[resident_id] != user_id:
            return False
        self.chatting[resident_id] = user_id
        return True

    def unlock_resident(self, resident_id: str) -> None:
        self.chatting.pop(resident_id, None)


manager = ConnectionManager()
