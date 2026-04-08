"""Tests for Plan 5: Player-to-player chat system.

Covers:
- T2: WebSocket protocol models (PlayerChat, PlayerChatReply, SetReplyMode)
- T3: PlayerChatService routing (online/offline x auto/manual) + coin charging
"""
import pytest
from unittest.mock import patch
from pydantic import ValidationError

from app.models.user import User
from app.models.resident import Resident
from app.models.pending_message import PendingMessage
from sqlalchemy import select


# ── T2: Protocol model tests ──────────────────────────────────────────


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


# ── T3: PlayerChatService routing tests ───────────────────────────────


@pytest.mark.anyio
async def test_route_to_online_manual_player(db_session):
    """Online + manual mode: message should be forwarded, not LLM-generated."""
    from app.services.player_chat_service import PlayerChatService

    sender = User(name="Alice", email="alice@test.com")
    target = User(name="Bob", email="bob@test.com")
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
    """Offline + auto mode: should still LLM-reply and queue the reply."""
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
