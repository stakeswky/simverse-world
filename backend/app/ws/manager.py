import json
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}  # user_id -> ws
        self.positions: dict[str, dict] = {}    # user_id -> {x, y, direction, name}
        self.chatting: dict[str, str] = {}       # resident_id -> user_id (lock)
        self.chat_queue: dict[str, list[str]] = {}  # resident_id -> [user_ids waiting]

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active[user_id] = ws

    def disconnect(self, user_id: str):
        self.active.pop(user_id, None)
        self.positions.pop(user_id, None)
        to_remove = [rid for rid, uid in self.chatting.items() if uid == user_id]
        for rid in to_remove:
            del self.chatting[rid]
        # Remove from any queues
        for queue in self.chat_queue.values():
            if user_id in queue:
                queue.remove(user_id)

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

    def enqueue(self, resident_id: str, user_id: str) -> int:
        """Add user to the chat queue for a resident. Returns queue position (1-based)."""
        if resident_id not in self.chat_queue:
            self.chat_queue[resident_id] = []
        queue = self.chat_queue[resident_id]
        if user_id not in queue:
            queue.append(user_id)
        return queue.index(user_id) + 1

    def dequeue(self, resident_id: str) -> str | None:
        """Pop the next waiting user from the queue. Returns user_id or None."""
        queue = self.chat_queue.get(resident_id, [])
        while queue:
            user_id = queue.pop(0)
            if user_id in self.active:  # still connected
                return user_id
        return None

    def remove_from_queue(self, resident_id: str, user_id: str) -> None:
        queue = self.chat_queue.get(resident_id, [])
        if user_id in queue:
            queue.remove(user_id)


manager = ConnectionManager()
