"""Player-to-player chat routing service.

Routing matrix:
  Target online  + manual mode  -> forward message via WebSocket
  Target online  + auto mode    -> LLM + target persona -> reply (is_auto=True)
  Target offline + manual mode  -> queue in PendingMessage, deliver on reconnect
  Target offline + auto mode    -> LLM + target persona -> reply (is_auto=True)

Token cost: initiator (sender) always pays for LLM auto-reply calls.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.resident import Resident
from app.models.pending_message import PendingMessage
from app.services.coin_service import charge
from app.llm.prompt import assemble_system_prompt
from app.llm.client import stream_chat


class PlayerChatService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def route_message(
        self,
        sender_id: str,
        target_user_id: str,
        text: str,
        target_online: bool,
    ) -> dict:
        """Route a player chat message. Returns result dict with action taken."""
        # Load target user and their player resident
        target_user = await self._get_user(target_user_id)
        if not target_user:
            return {"action": "error", "message": "Target user not found"}

        target_resident = await self._get_player_resident(target_user)
        if not target_resident:
            return {"action": "error", "message": "Target has no player resident"}

        reply_mode = target_resident.reply_mode or "manual"

        # --- Manual mode ---
        if reply_mode == "manual":
            if target_online:
                return {
                    "action": "forward",
                    "target_user_id": target_user_id,
                    "sender_id": sender_id,
                    "text": text,
                    "is_auto": False,
                }
            else:
                # Queue for delivery when target comes online
                await self._queue_message(sender_id, target_user_id, text, is_auto_reply=False)
                return {
                    "action": "queued",
                    "target_user_id": target_user_id,
                    "text": text,
                }

        # --- Auto mode (online or offline) ---
        # Charge initiator
        cost = target_resident.token_cost_per_turn
        charged = await charge(self._db, sender_id, cost, f"player_chat:{target_user_id}")
        if not charged:
            return {"action": "error", "message": "Insufficient Soul Coins"}

        # Generate auto-reply using target's persona
        reply_text = await self._generate_auto_reply(target_resident, text)

        return {
            "action": "auto_reply",
            "target_user_id": target_user_id,
            "sender_id": sender_id,
            "text": reply_text,
            "is_auto": True,
        }

    async def _generate_auto_reply(self, resident: Resident, user_text: str) -> str:
        """Call LLM with target's 3-layer persona to generate reply."""
        system_prompt = assemble_system_prompt(resident)
        messages = [{"role": "user", "content": user_text}]

        full_reply = ""
        async for chunk in stream_chat(system_prompt, messages):
            full_reply += chunk

        return full_reply

    async def _queue_message(
        self, sender_id: str, recipient_id: str, text: str, is_auto_reply: bool
    ) -> PendingMessage:
        """Store a message in the offline queue."""
        msg = PendingMessage(
            sender_id=sender_id,
            recipient_id=recipient_id,
            text=text,
            is_auto_reply=is_auto_reply,
        )
        self._db.add(msg)
        await self._db.commit()
        return msg

    async def _get_user(self, user_id: str) -> User | None:
        result = await self._db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def _get_player_resident(self, user: User) -> Resident | None:
        """Load the player's bound Resident (from user.player_resident_id)."""
        resident_id = getattr(user, "player_resident_id", None)
        if not resident_id:
            return None
        result = await self._db.execute(
            select(Resident).where(Resident.id == resident_id)
        )
        return result.scalar_one_or_none()


async def deliver_pending_messages(db: AsyncSession, user_id: str) -> list[dict]:
    """Fetch all undelivered messages for a user. Returns list of message payloads.
    Marks them as delivered."""
    result = await db.execute(
        select(PendingMessage)
        .where(
            PendingMessage.recipient_id == user_id,
            PendingMessage.delivered == False,
        )
        .order_by(PendingMessage.created_at.asc())
    )
    messages = result.scalars().all()

    payloads: list[dict] = []
    for msg in messages:
        payloads.append({
            "type": "player_chat_reply",
            "from_id": msg.sender_id,
            "text": msg.text,
            "is_auto": msg.is_auto_reply,
            "queued_at": msg.created_at.isoformat(),
        })
        msg.delivered = True

    if payloads:
        await db.commit()

    return payloads
