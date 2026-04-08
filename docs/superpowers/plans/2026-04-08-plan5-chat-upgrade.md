# Plan 5: Chat System Upgrade -- Player-to-Player Chat

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the WebSocket chat system to support player-to-player messaging with auto-reply (LLM + target's persona), manual relay, offline message queue, and reply mode switching. NPC chat remains unchanged.

**Architecture:** New `player_chat` message type routes through `PlayerChatService` which inspects the target's `resident_type` and `reply_mode`. If target is online + manual mode, the message is forwarded via WebSocket. If auto mode (online or offline), the target's 3-layer persona is loaded and LLM generates a reply in their voice (`is_auto=true`). Offline + manual mode stores messages in `PendingMessage` table, delivered on reconnect. Token cost is charged to the initiator for all LLM calls.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Anthropic SDK, pytest + pytest-asyncio

**Working directory:** `/Users/jimmy/Downloads/Skills-World/.worktrees/mvp-implementation/backend/`

**Depends on:** Plan 4 (Character + Visual) -- User.player_resident_id binding, Resident.resident_type ("npc"/"player"), Resident.reply_mode ("auto"/"manual") fields

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/models/pending_message.py` | Create | PendingMessage model for offline message queue |
| `app/services/player_chat_service.py` | Create | Player-to-player chat routing, auto-reply LLM calls, offline queue |
| `app/ws/protocol.py` | Modify | Add PlayerChat, PlayerChatReply, SetReplyMode protocol models |
| `app/ws/manager.py` | Modify | Add `is_online()`, `get_user_ws()` helpers; pending message delivery on connect |
| `app/ws/handler.py` | Modify | Add `player_chat`, `set_reply_mode` message handlers; deliver pending messages on connect |
| `tests/test_player_chat.py` | Create | Player chat routing tests (auto/manual, online/offline) |
| `tests/test_offline_queue.py` | Create | Offline message queue tests |

---

## Task 1: PendingMessage Model

**Files:**
- Create: `app/models/pending_message.py`
- Test: `tests/test_offline_queue.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_offline_queue.py
import pytest
from app.models.pending_message import PendingMessage


@pytest.mark.anyio
async def test_pending_message_creation(db_session):
    """PendingMessage should persist with all required fields."""
    msg = PendingMessage(
        sender_id="user-sender-1",
        recipient_id="user-recipient-1",
        text="Hello, are you there?",
        is_auto_reply=False,
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)

    assert msg.id is not None
    assert msg.sender_id == "user-sender-1"
    assert msg.recipient_id == "user-recipient-1"
    assert msg.text == "Hello, are you there?"
    assert msg.is_auto_reply is False
    assert msg.delivered is False
    assert msg.created_at is not None


@pytest.mark.anyio
async def test_pending_message_defaults(db_session):
    """PendingMessage should have correct defaults for delivered and is_auto_reply."""
    msg = PendingMessage(
        sender_id="a",
        recipient_id="b",
        text="test",
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)

    assert msg.delivered is False
    assert msg.is_auto_reply is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_offline_queue.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.pending_message'`

- [ ] **Step 3: Write implementation**

```python
# app/models/pending_message.py
"""Offline message queue for player-to-player chat."""
import uuid
from datetime import datetime, UTC
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PendingMessage(Base):
    __tablename__ = "pending_messages"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    sender_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), index=True
    )
    recipient_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    is_auto_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_offline_queue.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/models/pending_message.py tests/test_offline_queue.py
git commit -m "feat: PendingMessage model for offline player chat queue"
```

---

## Task 2: WebSocket Protocol Extensions

**Files:**
- Modify: `app/ws/protocol.py`
- Test: `tests/test_player_chat.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_player_chat.py
import pytest
from pydantic import ValidationError


def test_player_chat_protocol_valid():
    """PlayerChat should accept valid player_chat messages."""
    from app.ws.protocol import PlayerChat
    msg = PlayerChat(target_id="user-123", text="Hello!")
    assert msg.type == "player_chat"
    assert msg.target_id == "user-123"
    assert msg.text == "Hello!"


def test_player_chat_protocol_rejects_empty_text():
    """PlayerChat should reject empty text."""
    from app.ws.protocol import PlayerChat
    with pytest.raises(ValidationError):
        PlayerChat(target_id="user-123", text="")


def test_player_chat_reply_protocol():
    """PlayerChatReply should carry from_id, text, is_auto."""
    from app.ws.protocol import PlayerChatReply
    msg = PlayerChatReply(from_id="user-456", text="Hi back!", is_auto=True)
    assert msg.type == "player_chat_reply"
    assert msg.from_id == "user-456"
    assert msg.is_auto is True


def test_set_reply_mode_protocol_valid():
    """SetReplyMode should accept 'auto' and 'manual'."""
    from app.ws.protocol import SetReplyMode
    msg = SetReplyMode(mode="auto")
    assert msg.mode == "auto"
    msg2 = SetReplyMode(mode="manual")
    assert msg2.mode == "manual"


def test_set_reply_mode_protocol_rejects_invalid():
    """SetReplyMode should reject invalid mode values."""
    from app.ws.protocol import SetReplyMode
    with pytest.raises(ValidationError):
        SetReplyMode(mode="unknown")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_player_chat.py -v`
Expected: FAIL with `ImportError` (PlayerChat does not exist)

- [ ] **Step 3: Write implementation**

```python
# app/ws/protocol.py — replace entire file
from pydantic import BaseModel, field_validator
from typing import Literal


class StartChat(BaseModel):
    type: Literal["start_chat"] = "start_chat"
    resident_slug: str


class ChatMsg(BaseModel):
    type: Literal["chat_msg"] = "chat_msg"
    text: str


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_player_chat.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/ws/protocol.py tests/test_player_chat.py
git commit -m "feat: PlayerChat, PlayerChatReply, SetReplyMode WebSocket protocol models"
```

---

## Task 3: PlayerChatService -- Routing + Auto-Reply

**Files:**
- Create: `app/services/player_chat_service.py`
- Test: `tests/test_player_chat.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_player_chat.py
from unittest.mock import AsyncMock, patch, MagicMock
from app.models.user import User
from app.models.resident import Resident


@pytest.mark.anyio
async def test_route_to_online_manual_player(db_session):
    """Online + manual mode: message should be forwarded, not LLM-generated."""
    from app.services.player_chat_service import PlayerChatService

    # Create sender and target users
    sender = User(name="Alice", email="alice@test.com")
    target = User(name="Bob", email="bob@test.com")
    db_session.add_all([sender, target])
    await db_session.commit()
    await db_session.refresh(sender)
    await db_session.refresh(target)

    # Create target's player resident with manual mode
    resident = Resident(
        slug=f"player-{target.id[:8]}",
        name="Bob",
        creator_id=target.id,
        resident_type="player",
        reply_mode="manual",
    )
    db_session.add(resident)
    await db_session.commit()
    await db_session.refresh(resident)

    target.player_resident_id = resident.id
    await db_session.commit()

    service = PlayerChatService(db=db_session)

    result = await service.route_message(
        sender_id=sender.id,
        target_user_id=target.id,
        text="Hey Bob!",
        target_online=True,
    )

    assert result["action"] == "forward"
    assert result["text"] == "Hey Bob!"
    assert result["is_auto"] is False


@pytest.mark.anyio
async def test_route_to_online_auto_player(db_session):
    """Online + auto mode: should call LLM with target's persona."""
    from app.services.player_chat_service import PlayerChatService

    sender = User(name="Alice", email="alice-auto@test.com")
    target = User(name="Bob", email="bob-auto@test.com")
    db_session.add_all([sender, target])
    await db_session.commit()
    await db_session.refresh(sender)
    await db_session.refresh(target)

    resident = Resident(
        slug=f"player-{target.id[:8]}",
        name="Bob",
        creator_id=target.id,
        resident_type="player",
        reply_mode="auto",
        ability_md="# Ability\n- Expert coder",
        persona_md="# Persona\n## 身份卡\nI'm Bob, a developer.\n## 表达 DNA\nCasual, uses tech jargon.",
        soul_md="# Soul\n## Layer 0\n- Loves open source",
    )
    db_session.add(resident)
    await db_session.commit()
    await db_session.refresh(resident)

    target.player_resident_id = resident.id
    await db_session.commit()

    service = PlayerChatService(db=db_session)

    with patch("app.services.player_chat_service.stream_chat") as mock_stream:
        async def fake_stream(*args, **kwargs):
            yield "Hey Alice, "
            yield "what's up?"
        mock_stream.side_effect = fake_stream

        result = await service.route_message(
            sender_id=sender.id,
            target_user_id=target.id,
            text="Hi Bob!",
            target_online=True,
        )

    assert result["action"] == "auto_reply"
    assert result["is_auto"] is True
    assert "Hey Alice" in result["text"]


@pytest.mark.anyio
async def test_route_to_offline_manual_player(db_session):
    """Offline + manual mode: message should be queued."""
    from app.services.player_chat_service import PlayerChatService
    from app.models.pending_message import PendingMessage
    from sqlalchemy import select

    sender = User(name="Alice", email="alice-off@test.com")
    target = User(name="Bob", email="bob-off@test.com")
    db_session.add_all([sender, target])
    await db_session.commit()
    await db_session.refresh(sender)
    await db_session.refresh(target)

    resident = Resident(
        slug=f"player-{target.id[:8]}",
        name="Bob",
        creator_id=target.id,
        resident_type="player",
        reply_mode="manual",
    )
    db_session.add(resident)
    await db_session.commit()
    await db_session.refresh(resident)

    target.player_resident_id = resident.id
    await db_session.commit()

    service = PlayerChatService(db=db_session)

    result = await service.route_message(
        sender_id=sender.id,
        target_user_id=target.id,
        text="Are you there?",
        target_online=False,
    )

    assert result["action"] == "queued"

    # Verify message was stored in DB
    q = await db_session.execute(
        select(PendingMessage).where(
            PendingMessage.recipient_id == target.id,
            PendingMessage.delivered == False,
        )
    )
    pending = q.scalars().all()
    assert len(pending) == 1
    assert pending[0].text == "Are you there?"
    assert pending[0].sender_id == sender.id


@pytest.mark.anyio
async def test_route_to_offline_auto_player(db_session):
    """Offline + auto mode: should still LLM-reply (async) and queue the reply."""
    from app.services.player_chat_service import PlayerChatService

    sender = User(name="Alice", email="alice-offauto@test.com")
    target = User(name="Bot", email="bot-offauto@test.com")
    db_session.add_all([sender, target])
    await db_session.commit()
    await db_session.refresh(sender)
    await db_session.refresh(target)

    resident = Resident(
        slug=f"player-{target.id[:8]}",
        name="Bot",
        creator_id=target.id,
        resident_type="player",
        reply_mode="auto",
        ability_md="# Ability\n- Knows everything",
        persona_md="# Persona\n## 身份卡\nI'm Bot.\n## 表达 DNA\nFriendly.",
        soul_md="# Soul\n## Layer 0\n- Helpful",
    )
    db_session.add(resident)
    await db_session.commit()
    await db_session.refresh(resident)

    target.player_resident_id = resident.id
    await db_session.commit()

    service = PlayerChatService(db=db_session)

    with patch("app.services.player_chat_service.stream_chat") as mock_stream:
        async def fake_stream(*args, **kwargs):
            yield "I'm not online "
            yield "but my AI says hi!"
        mock_stream.side_effect = fake_stream

        result = await service.route_message(
            sender_id=sender.id,
            target_user_id=target.id,
            text="Hello?",
            target_online=False,
        )

    assert result["action"] == "auto_reply"
    assert result["is_auto"] is True


@pytest.mark.anyio
async def test_charge_initiator_for_auto_reply(db_session):
    """Auto-reply should charge the initiator (sender), not the target."""
    from app.services.player_chat_service import PlayerChatService

    sender = User(name="Alice", email="alice-coin@test.com", soul_coin_balance=50)
    target = User(name="Bot", email="bot-coin@test.com", soul_coin_balance=100)
    db_session.add_all([sender, target])
    await db_session.commit()
    await db_session.refresh(sender)
    await db_session.refresh(target)

    resident = Resident(
        slug=f"player-{target.id[:8]}",
        name="Bot",
        creator_id=target.id,
        resident_type="player",
        reply_mode="auto",
        token_cost_per_turn=2,
        persona_md="# Persona\n## 身份卡\nBot",
        soul_md="# Soul",
        ability_md="# Ability",
    )
    db_session.add(resident)
    await db_session.commit()
    await db_session.refresh(resident)

    target.player_resident_id = resident.id
    await db_session.commit()

    service = PlayerChatService(db=db_session)

    with patch("app.services.player_chat_service.stream_chat") as mock_stream:
        async def fake_stream(*args, **kwargs):
            yield "Reply"
        mock_stream.side_effect = fake_stream

        result = await service.route_message(
            sender_id=sender.id,
            target_user_id=target.id,
            text="Hi",
            target_online=True,
        )

    await db_session.refresh(sender)
    await db_session.refresh(target)

    assert sender.soul_coin_balance == 48  # charged 2
    assert target.soul_coin_balance == 100  # unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_player_chat.py::test_route_to_online_manual_player -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.player_chat_service'`

- [ ] **Step 3: Write implementation**

```python
# app/services/player_chat_service.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_player_chat.py -v`
Expected: All 10 tests PASS (5 protocol + 5 service)

- [ ] **Step 5: Commit**

```bash
git add app/services/player_chat_service.py tests/test_player_chat.py
git commit -m "feat: PlayerChatService with auto-reply, manual forward, offline queue"
```

---

## Task 4: Offline Message Delivery

**Files:**
- Test: `tests/test_offline_queue.py`
- Uses: `app/services/player_chat_service.py` (deliver_pending_messages)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_offline_queue.py
from app.services.player_chat_service import deliver_pending_messages
from app.models.user import User
from sqlalchemy import select


@pytest.mark.anyio
async def test_deliver_pending_messages_returns_all_queued(db_session):
    """Should return all undelivered messages in chronological order."""
    sender = User(name="A", email="a@test.com")
    recipient = User(name="B", email="b@test.com")
    db_session.add_all([sender, recipient])
    await db_session.commit()
    await db_session.refresh(sender)
    await db_session.refresh(recipient)

    # Queue 3 messages
    for i in range(3):
        msg = PendingMessage(
            sender_id=sender.id,
            recipient_id=recipient.id,
            text=f"Message {i}",
        )
        db_session.add(msg)
    await db_session.commit()

    payloads = await deliver_pending_messages(db_session, recipient.id)

    assert len(payloads) == 3
    assert payloads[0]["text"] == "Message 0"
    assert payloads[2]["text"] == "Message 2"
    for p in payloads:
        assert p["type"] == "player_chat_reply"
        assert "queued_at" in p


@pytest.mark.anyio
async def test_deliver_marks_messages_as_delivered(db_session):
    """After delivery, messages should be marked delivered and not returned again."""
    sender = User(name="C", email="c@test.com")
    recipient = User(name="D", email="d@test.com")
    db_session.add_all([sender, recipient])
    await db_session.commit()
    await db_session.refresh(sender)
    await db_session.refresh(recipient)

    db_session.add(PendingMessage(
        sender_id=sender.id,
        recipient_id=recipient.id,
        text="Hello",
    ))
    await db_session.commit()

    # First delivery
    payloads1 = await deliver_pending_messages(db_session, recipient.id)
    assert len(payloads1) == 1

    # Second delivery should return nothing
    payloads2 = await deliver_pending_messages(db_session, recipient.id)
    assert len(payloads2) == 0


@pytest.mark.anyio
async def test_deliver_empty_when_no_messages(db_session):
    """Should return empty list when no pending messages exist."""
    payloads = await deliver_pending_messages(db_session, "nonexistent-user")
    assert payloads == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_offline_queue.py -v`
Expected: FAIL (first 2 tests pass from Task 1, new tests fail because deliver function not yet tested)

Actually, the implementation was already written in Task 3. Let's verify:

- [ ] **Step 3: Run all offline queue tests**

Run: `python -m pytest tests/test_offline_queue.py -v`
Expected: All 5 tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_offline_queue.py
git commit -m "test: offline message delivery (deliver, mark delivered, empty case)"
```

---

## Task 5: ConnectionManager Upgrades

**Files:**
- Modify: `app/ws/manager.py`
- Test: `tests/test_player_chat.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_player_chat.py

def test_manager_is_online():
    """ConnectionManager.is_online should reflect connected users."""
    from app.ws.manager import ConnectionManager
    mgr = ConnectionManager()

    assert mgr.is_online("user-1") is False

    # Simulate connection (we can't use a real WebSocket here, just set the dict)
    mgr.active["user-1"] = MagicMock()  # fake ws
    assert mgr.is_online("user-1") is True

    mgr.disconnect("user-1")
    assert mgr.is_online("user-1") is False


def test_manager_get_reply_mode_default():
    """Default reply mode should be 'manual'."""
    from app.ws.manager import ConnectionManager
    mgr = ConnectionManager()

    assert mgr.get_reply_mode("user-1") == "manual"


def test_manager_set_reply_mode():
    """Should store and retrieve reply mode per user."""
    from app.ws.manager import ConnectionManager
    mgr = ConnectionManager()

    mgr.set_reply_mode("user-1", "auto")
    assert mgr.get_reply_mode("user-1") == "auto"

    mgr.set_reply_mode("user-1", "manual")
    assert mgr.get_reply_mode("user-1") == "manual"


def test_manager_disconnect_clears_reply_mode():
    """Disconnecting should clean up reply mode."""
    from app.ws.manager import ConnectionManager
    mgr = ConnectionManager()

    mgr.active["user-1"] = MagicMock()
    mgr.set_reply_mode("user-1", "auto")
    assert mgr.get_reply_mode("user-1") == "auto"

    mgr.disconnect("user-1")
    assert mgr.get_reply_mode("user-1") == "manual"  # back to default
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_player_chat.py::test_manager_is_online -v`
Expected: FAIL with `AttributeError: 'ConnectionManager' object has no attribute 'is_online'`

- [ ] **Step 3: Write implementation**

```python
# app/ws/manager.py — replace entire file
import json
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}       # user_id -> ws
        self.positions: dict[str, dict] = {}          # user_id -> {x, y, direction, name}
        self.chatting: dict[str, str] = {}            # resident_id -> user_id (lock)
        self._reply_modes: dict[str, str] = {}        # user_id -> "auto" | "manual"

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active[user_id] = ws

    def disconnect(self, user_id: str):
        self.active.pop(user_id, None)
        self.positions.pop(user_id, None)
        self._reply_modes.pop(user_id, None)
        to_remove = [rid for rid, uid in self.chatting.items() if uid == user_id]
        for rid in to_remove:
            del self.chatting[rid]

    def is_online(self, user_id: str) -> bool:
        """Check if a user is currently connected."""
        return user_id in self.active

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

    # --- Reply mode (Plan 5) ---

    def get_reply_mode(self, user_id: str) -> str:
        """Get user's current reply mode. Defaults to 'manual'."""
        return self._reply_modes.get(user_id, "manual")

    def set_reply_mode(self, user_id: str, mode: str) -> None:
        """Set user's reply mode ('auto' or 'manual')."""
        if mode not in ("auto", "manual"):
            raise ValueError(f"Invalid reply mode: {mode}")
        self._reply_modes[user_id] = mode


manager = ConnectionManager()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_player_chat.py -v`
Expected: All 14 tests PASS (5 protocol + 5 service + 4 manager)

- [ ] **Step 5: Commit**

```bash
git add app/ws/manager.py tests/test_player_chat.py
git commit -m "feat: ConnectionManager upgrades (is_online, reply_mode tracking)"
```

---

## Task 6: WebSocket Handler Integration

**Files:**
- Modify: `app/ws/handler.py`
- Test: `tests/test_player_chat.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_player_chat.py

@pytest.mark.anyio
async def test_handler_player_chat_forward(db_session):
    """Handler should forward player_chat to manual-mode online target."""
    from app.services.player_chat_service import PlayerChatService

    # This is an integration-level test verifying the routing decision
    sender = User(name="Sender", email="sender-int@test.com", soul_coin_balance=100)
    target = User(name="Target", email="target-int@test.com", soul_coin_balance=100)
    db_session.add_all([sender, target])
    await db_session.commit()
    await db_session.refresh(sender)
    await db_session.refresh(target)

    resident = Resident(
        slug=f"player-{target.id[:8]}",
        name="Target",
        creator_id=target.id,
        resident_type="player",
        reply_mode="manual",
        persona_md="# Persona",
        soul_md="# Soul",
        ability_md="# Ability",
    )
    db_session.add(resident)
    await db_session.commit()
    await db_session.refresh(resident)

    target.player_resident_id = resident.id
    await db_session.commit()

    service = PlayerChatService(db=db_session)
    result = await service.route_message(
        sender_id=sender.id,
        target_user_id=target.id,
        text="Can you hear me?",
        target_online=True,
    )

    assert result["action"] == "forward"
    # Sender balance unchanged (no LLM call)
    await db_session.refresh(sender)
    assert sender.soul_coin_balance == 100


@pytest.mark.anyio
async def test_handler_set_reply_mode():
    """set_reply_mode message should update the manager's reply mode."""
    from app.ws.manager import ConnectionManager

    mgr = ConnectionManager()
    mgr.active["user-x"] = MagicMock()

    # Simulate processing set_reply_mode
    mgr.set_reply_mode("user-x", "auto")
    assert mgr.get_reply_mode("user-x") == "auto"

    mgr.set_reply_mode("user-x", "manual")
    assert mgr.get_reply_mode("user-x") == "manual"
```

- [ ] **Step 2: Run tests to verify they pass** (these test existing service + manager code)

Run: `python -m pytest tests/test_player_chat.py -v`
Expected: All tests PASS

- [ ] **Step 3: Write handler integration**

Add the following message handlers inside the `while True` loop in `app/ws/handler.py`, after the `rate_chat` handler block, inside the `async with async_session() as db:` block:

```python
# Add these imports at top of app/ws/handler.py
from app.ws.protocol import PlayerChat, SetReplyMode
from app.services.player_chat_service import PlayerChatService, deliver_pending_messages

# --- Inside websocket_handler(), after manager.connect() and before the main loop ---
# Deliver pending offline messages on connect
async with async_session() as db:
    pending_payloads = await deliver_pending_messages(db, user_id)
    for payload in pending_payloads:
        await manager.send(user_id, payload)

# --- Inside the main while-True loop, within the `async with async_session() as db:` block ---
# Add these handlers after the existing rate_chat handler:

                elif msg_type == "player_chat":
                    try:
                        pc_msg = PlayerChat(**data)
                    except Exception:
                        await manager.send(user_id, {"type": "error", "message": "Invalid player_chat format"})
                        continue

                    target_id = pc_msg.target_id
                    target_online = manager.is_online(target_id)

                    service = PlayerChatService(db=db)
                    result = await service.route_message(
                        sender_id=user_id,
                        target_user_id=target_id,
                        text=pc_msg.text,
                        target_online=target_online,
                    )

                    if result["action"] == "error":
                        await manager.send(user_id, {"type": "error", "message": result["message"]})

                    elif result["action"] == "forward":
                        # Forward to target player via WebSocket
                        await manager.send(target_id, {
                            "type": "player_chat_reply",
                            "from_id": user_id,
                            "text": result["text"],
                            "is_auto": False,
                        })
                        # Confirm to sender
                        await manager.send(user_id, {
                            "type": "player_chat_sent",
                            "target_id": target_id,
                            "delivered": True,
                        })

                    elif result["action"] == "auto_reply":
                        # Send LLM auto-reply back to sender
                        await manager.send(user_id, {
                            "type": "player_chat_reply",
                            "from_id": target_id,
                            "text": result["text"],
                            "is_auto": True,
                        })
                        # Update sender coin balance
                        balance_result = await db.execute(
                            select(User.soul_coin_balance).where(User.id == user_id)
                        )
                        balance = balance_result.scalar_one()
                        await manager.send(user_id, {
                            "type": "coin_update",
                            "balance": balance,
                            "delta": -1,
                            "reason": "player_chat_auto",
                        })

                    elif result["action"] == "queued":
                        # Notify sender that message is queued
                        await manager.send(user_id, {
                            "type": "player_chat_sent",
                            "target_id": target_id,
                            "delivered": False,
                            "queued": True,
                        })

                elif msg_type == "set_reply_mode":
                    try:
                        mode_msg = SetReplyMode(**data)
                    except Exception:
                        await manager.send(user_id, {"type": "error", "message": "Invalid set_reply_mode format"})
                        continue

                    manager.set_reply_mode(user_id, mode_msg.mode)

                    # Also persist to DB (update the player's Resident.reply_mode)
                    user_result = await db.execute(select(User).where(User.id == user_id))
                    user_obj = user_result.scalar_one_or_none()
                    if user_obj and user_obj.player_resident_id:
                        res_result = await db.execute(
                            select(Resident).where(Resident.id == user_obj.player_resident_id)
                        )
                        player_resident = res_result.scalar_one_or_none()
                        if player_resident:
                            player_resident.reply_mode = mode_msg.mode
                            await db.commit()

                    await manager.send(user_id, {
                        "type": "reply_mode_changed",
                        "mode": mode_msg.mode,
                    })
```

Also add this block right after the `manager.connect(user_id, ws)` call and the user name lookup, **before** the main `while True` loop:

```python
    # Deliver pending offline messages on connect
    async with async_session() as db:
        pending_payloads = await deliver_pending_messages(db, user_id)
        for payload in pending_payloads:
            await manager.send(user_id, payload)

    # Load user's reply mode from their player resident
    async with async_session() as db:
        user_result = await db.execute(select(User).where(User.id == user_id))
        user_obj = user_result.scalar_one_or_none()
        if user_obj and hasattr(user_obj, "player_resident_id") and user_obj.player_resident_id:
            res_result = await db.execute(
                select(Resident).where(Resident.id == user_obj.player_resident_id)
            )
            player_res = res_result.scalar_one_or_none()
            if player_res and hasattr(player_res, "reply_mode"):
                manager.set_reply_mode(user_id, player_res.reply_mode or "manual")
```

- [ ] **Step 4: Run all tests to verify no regressions**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/ws/handler.py
git commit -m "feat: player_chat + set_reply_mode WS handlers, pending message delivery on connect"
```

---

## Task 7: Full Integration Test + Smoke Test

**Files:**
- No new files

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify all new modules import correctly**

```bash
python -c "
from app.models.pending_message import PendingMessage
from app.ws.protocol import PlayerChat, PlayerChatReply, SetReplyMode
from app.services.player_chat_service import PlayerChatService, deliver_pending_messages
from app.ws.manager import ConnectionManager
mgr = ConnectionManager()
assert hasattr(mgr, 'is_online')
assert hasattr(mgr, 'get_reply_mode')
assert hasattr(mgr, 'set_reply_mode')
print('All Plan 5 modules OK')
"
```

- [ ] **Step 3: Manual smoke test (with 2 browser tabs)**

```bash
# Start server
cd /Users/jimmy/Downloads/Skills-World/.worktrees/mvp-implementation/backend
uvicorn app.main:app --reload

# In browser console (tab 1 - Alice):
ws1 = new WebSocket('ws://localhost:8000/ws?token=ALICE_TOKEN')
ws1.onmessage = e => console.log('Alice:', JSON.parse(e.data))

# In browser console (tab 2 - Bob):
ws2 = new WebSocket('ws://localhost:8000/ws?token=BOB_TOKEN')
ws2.onmessage = e => console.log('Bob:', JSON.parse(e.data))

# Alice sends to Bob (manual mode):
ws1.send(JSON.stringify({type: "player_chat", target_id: "BOB_USER_ID", text: "Hey Bob!"}))
# Expected: Bob receives {type: "player_chat_reply", from_id: "ALICE_ID", text: "Hey Bob!", is_auto: false}

# Bob switches to auto mode:
ws2.send(JSON.stringify({type: "set_reply_mode", mode: "auto"}))
# Expected: Bob receives {type: "reply_mode_changed", mode: "auto"}

# Alice sends again (auto mode):
ws1.send(JSON.stringify({type: "player_chat", target_id: "BOB_USER_ID", text: "What do you think about AI?"}))
# Expected: Alice receives {type: "player_chat_reply", from_id: "BOB_ID", text: "...", is_auto: true}
```

- [ ] **Step 4: Commit if any fixes needed**

```bash
git add -A
git commit -m "chore: Plan 5 chat system upgrade integration fixes"
```

---

## Summary

| Task | What it does | Key Files |
|------|-------------|-----------|
| 1 | PendingMessage model for offline queue | pending_message.py |
| 2 | WebSocket protocol extensions (PlayerChat, PlayerChatReply, SetReplyMode) | protocol.py |
| 3 | PlayerChatService routing (auto/manual, online/offline) + coin charging | player_chat_service.py |
| 4 | Offline message delivery + mark-as-delivered tests | player_chat_service.py |
| 5 | ConnectionManager upgrades (is_online, reply_mode tracking) | manager.py |
| 6 | WebSocket handler integration (player_chat, set_reply_mode, pending delivery) | handler.py |
| 7 | Full integration test + smoke test | -- |
