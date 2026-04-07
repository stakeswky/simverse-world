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
from app.ws.protocol import StartChat, ChatMsg, EndChat


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
                    try:
                        msg = StartChat(**data)
                    except Exception:
                        await manager.send(user_id, {"type": "error", "message": "Invalid message format"})
                        continue
                    slug = msg.resident_slug
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
                    try:
                        ChatMsg(**data)
                    except Exception:
                        await manager.send(user_id, {"type": "error", "message": "Invalid message format"})
                        continue
                    # Re-fetch conversation to avoid detached mutation being dropped
                    conv_result = await db.execute(
                        select(Conversation).where(Conversation.id == current_conversation.id)
                    )
                    fresh_conv = conv_result.scalar_one_or_none()
                    if not fresh_conv:
                        await manager.send(user_id, {"type": "error", "message": "Conversation not found"})
                        continue

                    text = data.get("text", "").strip()
                    if not text:
                        await manager.send(user_id, {"type": "error", "message": "Empty message"})
                        continue

                    cost = current_resident.token_cost_per_turn

                    ok = await charge(db, user_id, cost, f"chat:{current_resident.slug}")
                    if not ok:
                        await manager.send(user_id, {"type": "error", "message": "Insufficient Soul Coins"})
                        continue

                    db.add(Message(
                        conversation_id=fresh_conv.id,
                        role="user",
                        content=text,
                    ))
                    fresh_conv.turns += 1
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
                        conversation_id=fresh_conv.id,
                        role="assistant",
                        content=full_reply,
                    ))
                    fresh_conv.tokens_used += len(full_reply)  # character count proxy
                    await db.commit()

                    # Reward creator (1 SC per turn)
                    await reward(db, current_resident.creator_id, 1, f"chat_reward:{current_resident.slug}")

                elif msg_type == "end_chat" and current_conversation and current_resident:
                    try:
                        EndChat(**data)
                    except Exception:
                        await manager.send(user_id, {"type": "error", "message": "Invalid message format"})
                        continue
                    resident_id = current_resident.id
                    resident_slug = current_resident.slug
                    # Re-fetch in the current session to avoid detached-object mutation being dropped
                    res_result = await db.execute(select(Resident).where(Resident.id == resident_id))
                    fresh_resident = res_result.scalar_one_or_none()
                    if fresh_resident:
                        fresh_resident.status = "popular" if fresh_resident.heat >= 50 else "idle"
                        fresh_resident.total_conversations += 1
                        fresh_resident.last_conversation_at = datetime.now(UTC)

                    # Also re-fetch conversation in current session
                    conv_result = await db.execute(
                        select(Conversation).where(Conversation.id == current_conversation.id)
                    )
                    fresh_conv = conv_result.scalar_one_or_none()
                    if fresh_conv:
                        fresh_conv.ended_at = datetime.now(UTC)

                    await db.commit()

                    prev_status = fresh_resident.status if fresh_resident else "idle"
                    await manager.send(user_id, {
                        "type": "chat_ended",
                        "conversation_id": fresh_conv.id if fresh_conv else "",
                    })
                    await manager.broadcast(
                        {"type": "resident_status", "resident_slug": resident_slug, "status": prev_status},
                        exclude=user_id,
                    )
                    current_conversation = None
                    current_resident = None
                    chat_messages = []

                elif msg_type == "rate_chat":
                    from sqlalchemy import func
                    conv_id = data.get("conversation_id", "")
                    rating_value = int(data.get("rating", 0))

                    if not (1 <= rating_value <= 5):
                        await manager.send(user_id, {"type": "error", "message": "Rating must be 1-5"})
                        continue

                    conv_result = await db.execute(
                        select(Conversation).where(
                            Conversation.id == conv_id,
                            Conversation.user_id == user_id,
                        )
                    )
                    conv = conv_result.scalar_one_or_none()
                    if not conv:
                        await manager.send(user_id, {"type": "error", "message": "Conversation not found"})
                        continue

                    conv.rating = rating_value
                    await db.commit()

                    # Recalculate resident avg_rating
                    avg_result = await db.execute(
                        select(func.avg(Conversation.rating)).where(
                            Conversation.resident_id == conv.resident_id,
                            Conversation.rating.is_not(None),
                        )
                    )
                    avg = avg_result.scalar()
                    if avg is not None:
                        res_result = await db.execute(
                            select(Resident).where(Resident.id == conv.resident_id)
                        )
                        resident = res_result.scalar_one_or_none()
                        if resident:
                            resident.avg_rating = round(float(avg), 2)
                            from app.services.scoring_service import compute_star_rating
                            resident.star_rating = compute_star_rating(resident)
                            await db.commit()

                    # Reward creator 5 SC for 4+ star rating
                    if rating_value >= 4 and conv.resident_id:
                        res_result = await db.execute(
                            select(Resident).where(Resident.id == conv.resident_id)
                        )
                        resident = res_result.scalar_one_or_none()
                        if resident:
                            from app.services.coin_service import reward
                            await reward(db, resident.creator_id, 5, f"good_rating:{resident.slug}")

                    await manager.send(user_id, {
                        "type": "rating_saved",
                        "conversation_id": conv_id,
                        "rating": rating_value,
                    })

    except WebSocketDisconnect:
        if current_conversation and current_resident:
            async with async_session() as db:
                result = await db.execute(select(Resident).where(Resident.id == current_resident.id))
                r = result.scalar_one_or_none()
                if r and r.status == "chatting":
                    r.status = "popular" if r.heat >= 50 else "idle"
                    await db.commit()
        manager.disconnect(user_id)
