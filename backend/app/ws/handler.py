import json
from datetime import datetime, UTC
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.database import async_session
from app.models.resident import Resident
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.services.auth_service import verify_token
from app.services.coin_service import charge, reward
from app.llm.prompt import assemble_system_prompt
from app.llm.client import stream_chat
from app.ws.manager import manager


async def websocket_handler(ws: WebSocket):
    """Handle a single WebSocket connection lifecycle."""
    token = ws.query_params.get("token", "")
    user_id = verify_token(token)
    if not user_id:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(user_id, ws)

    current_conversation: Conversation | None = None
    current_resident: Resident | None = None
    chat_messages: list[dict] = []

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")

            async with async_session() as db:
                if msg_type == "start_chat":
                    slug = data.get("resident_slug", "")
                    result = await db.execute(select(Resident).where(Resident.slug == slug))
                    resident = result.scalar_one_or_none()
                    if not resident:
                        await manager.send(user_id, {"type": "error", "message": "Resident not found"})
                        continue
                    if resident.status == "chatting":
                        await manager.send(user_id, {"type": "error", "message": "Resident is busy"})
                        continue
                    if resident.status == "sleeping":
                        resident.status = "idle"

                    conv = Conversation(user_id=user_id, resident_id=resident.id)
                    db.add(conv)
                    resident.status = "chatting"
                    await db.commit()
                    await db.refresh(conv)

                    current_conversation = conv
                    current_resident = resident
                    chat_messages = []

                    await manager.send(user_id, {"type": "chat_started", "resident_slug": slug})
                    await manager.broadcast(
                        {"type": "resident_status", "resident_slug": slug, "status": "chatting"},
                        exclude=user_id,
                    )

                elif msg_type == "chat_msg" and current_conversation and current_resident:
                    text = data.get("text", "")
                    cost = current_resident.token_cost_per_turn

                    ok = await charge(db, user_id, cost, f"chat:{current_resident.slug}")
                    if not ok:
                        await manager.send(user_id, {"type": "error", "message": "Insufficient Soul Coins"})
                        continue

                    db.add(Message(
                        conversation_id=current_conversation.id,
                        role="user",
                        content=text,
                    ))
                    current_conversation.turns += 1
                    await db.commit()

                    # Get updated balance and notify client
                    result = await db.execute(
                        select(User.soul_coin_balance).where(User.id == user_id)
                    )
                    balance = result.scalar_one()
                    await manager.send(user_id, {
                        "type": "coin_update",
                        "balance": balance,
                        "delta": -cost,
                        "reason": "chat",
                    })

                    chat_messages.append({"role": "user", "content": text})
                    system_prompt = assemble_system_prompt(current_resident)

                    full_reply = ""
                    async for chunk in stream_chat(system_prompt, chat_messages):
                        full_reply += chunk
                        await manager.send(user_id, {
                            "type": "chat_reply",
                            "text": chunk,
                            "done": False,
                        })
                    await manager.send(user_id, {"type": "chat_reply", "text": "", "done": True})

                    chat_messages.append({"role": "assistant", "content": full_reply})
                    db.add(Message(
                        conversation_id=current_conversation.id,
                        role="assistant",
                        content=full_reply,
                    ))
                    current_conversation.tokens_used += len(full_reply.split())
                    await db.commit()

                    # Reward creator (1 SC per turn)
                    await reward(db, current_resident.creator_id, 1, f"chat_reward:{current_resident.slug}")

                elif msg_type == "end_chat" and current_conversation and current_resident:
                    current_conversation.ended_at = datetime.now(UTC)
                    prev_status = "popular" if current_resident.heat >= 50 else "idle"
                    current_resident.status = prev_status
                    current_resident.total_conversations += 1
                    current_resident.last_conversation_at = datetime.now(UTC)
                    await db.commit()

                    slug = current_resident.slug
                    await manager.send(user_id, {"type": "chat_ended"})
                    await manager.broadcast(
                        {"type": "resident_status", "resident_slug": slug, "status": prev_status},
                        exclude=user_id,
                    )
                    current_conversation = None
                    current_resident = None
                    chat_messages = []

    except WebSocketDisconnect:
        if current_conversation and current_resident:
            async with async_session() as db:
                result = await db.execute(select(Resident).where(Resident.id == current_resident.id))
                r = result.scalar_one_or_none()
                if r and r.status == "chatting":
                    r.status = "popular" if r.heat >= 50 else "idle"
                    await db.commit()
        manager.disconnect(user_id)
