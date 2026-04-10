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
from app.services.player_chat_service import PlayerChatService, deliver_pending_messages
from app.llm.prompt import assemble_system_prompt
from app.llm.client import stream_chat
from app.ws.manager import manager
from app.ws.protocol import StartChat, ChatMsg, EndChat
from app.memory.service import MemoryService
from app.media.model_router import ModelRouter


async def websocket_handler(ws: WebSocket):
    """Handle a single WebSocket connection lifecycle."""
    token = ws.query_params.get("token", "")
    user_id = verify_token(token)
    if not user_id:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(user_id, ws)

    # Fetch user name, position, and sprite from DB and cache for the session
    user_name = user_id  # fallback
    spawn_x = 76 * 32
    spawn_y = 50 * 32
    sprite_key = ""
    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user_row = result.scalar_one_or_none()
        if user_row:
            user_name = user_row.name
            # Use persisted position if user has a player resident
            if user_row.player_resident_id:
                spawn_x = user_row.last_x
                spawn_y = user_row.last_y
                # Fetch sprite_key from the player's Resident
                res_result = await db.execute(
                    select(Resident.sprite_key).where(Resident.id == user_row.player_resident_id)
                )
                sk = res_result.scalar_one_or_none()
                if sk:
                    sprite_key = sk

    # Attempt daily login reward
    async with async_session() as db:
        from app.services.daily_reward_service import claim_daily_reward
        reward_result = await claim_daily_reward(db, user_id)
        if reward_result["claimed"]:
            await manager.send(user_id, {
                "type": "daily_reward",
                "amount": reward_result["amount"],
                "new_balance": reward_result["new_balance"],
            })

    # Initialize position so other players can see us immediately
    manager.update_position(user_id, spawn_x, spawn_y, "down", user_name)

    # Send spawn position to the connecting user so the frontend can place the player correctly
    await manager.send(user_id, {"type": "spawn_position", "x": spawn_x, "y": spawn_y})

    # Send current online players and announce join
    online_players = manager.get_online_players(exclude=user_id)
    if online_players:
        await manager.send(user_id, {"type": "online_players", "players": online_players})

    # Deliver any pending (offline-queued) messages
    async with async_session() as db:
        pending = await deliver_pending_messages(db, user_id)
        for pm in pending:
            await manager.send(user_id, pm)

    # Broadcast join with position and sprite so existing players can render the new player
    pos = manager.positions.get(user_id, {})
    await manager.broadcast(
        {
            "type": "player_joined",
            "player_id": user_id,
            "name": user_name,
            "x": pos.get("x", 0),
            "y": pos.get("y", 0),
            "direction": pos.get("direction", "down"),
            "sprite_key": sprite_key,
        },
        exclude=user_id,
    )

    current_conversation: Conversation | None = None
    current_resident: Resident | None = None
    chat_messages: list[dict] = []
    memory_context = None

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")

            # Cancel queue (fast path — no DB needed)
            if msg_type == "cancel_queue":
                slug = data.get("resident_slug", "")
                # Find resident_id by slug from any active lock
                for rid, queue in list(manager.chat_queue.items()):
                    if user_id in queue:
                        queue.remove(user_id)
                continue

            # Handle move without DB (position only — fast path)
            if msg_type == "move":
                x = float(data.get("x", 0))
                y = float(data.get("y", 0))
                direction = str(data.get("direction", "down"))
                manager.update_position(user_id, x, y, direction, user_name)
                await manager.broadcast(
                    {"type": "player_moved", "player_id": user_id,
                     "name": user_name,
                     "x": x, "y": y, "direction": direction},
                    exclude=user_id,
                )
                continue

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
                    # Queue if NPC is chatting or locked by another player
                    if resident.status == "chatting" or (not manager.lock_resident(resident.id, user_id)):
                        pos = manager.enqueue(resident.id, user_id)
                        await manager.send(user_id, {
                            "type": "chat_queued",
                            "resident_slug": slug,
                            "resident_name": resident.name,
                            "position": pos,
                        })
                        continue

                    # Wake sleeping NPC — costs 3x token_cost_per_turn
                    if resident.status == "sleeping":
                        if not msg.wake:
                            wake_cost = resident.token_cost_per_turn * 3
                            await manager.send(user_id, {
                                "type": "wake_required",
                                "resident_slug": slug,
                                "resident_name": resident.name,
                                "cost": wake_cost,
                            })
                            manager.unlock_resident(resident.id)
                            continue
                        wake_cost = resident.token_cost_per_turn * 3
                        from app.services.coin_service import charge, get_balance
                        ok = await charge(db, user_id, wake_cost, f"wake:{slug}")
                        if not ok:
                            await manager.send(user_id, {"type": "error", "message": "Insufficient Soul Coins"})
                            manager.unlock_resident(resident.id)
                            continue
                        balance = await get_balance(db, user_id)
                        await manager.send(user_id, {
                            "type": "coin_update",
                            "balance": balance,
                            "delta": -wake_cost,
                            "reason": f"wake:{slug}",
                        })
                        # Keep NPC awake: bump heat and update last_conversation_at
                        # so heat_cron won't put them back to sleep for at least 7 days
                        resident.heat = max(resident.heat, 10)
                        resident.last_conversation_at = datetime.now(UTC)
                        # Broadcast wake-up to all players (including self)
                        await manager.broadcast(
                            {"type": "resident_status", "resident_slug": slug, "status": "chatting"},
                        )

                    conv = Conversation(user_id=user_id, resident_id=resident.id)
                    db.add(conv)
                    resident.status = "chatting"
                    await db.commit()
                    await db.refresh(conv)

                    current_conversation = conv
                    current_resident = resident
                    chat_messages = []

                    # Retrieve memory context for this resident+user pair
                    memory_svc = MemoryService(db)
                    memory_context = await memory_svc.retrieve_context(
                        resident_id=resident.id,
                        user_id=user_id,
                    )

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

                    media_url = data.get("media_url") or None
                    media_type = data.get("media_type") or None

                    chat_messages.append({"role": "user", "content": text})
                    system_prompt = assemble_system_prompt(current_resident, memory_context=memory_context)

                    full_reply = ""
                    model_router = ModelRouter()
                    async for chunk in model_router.chat_with_media(
                        system_prompt=system_prompt,
                        messages=chat_messages,
                        media_url=media_url,
                        media_type=media_type,
                    ):
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

                    # If media was sent, store media_summary in event memory
                    if media_url and media_type:
                        # full_reply IS the media summary from the model's perspective
                        memory_svc = MemoryService(db)
                        await memory_svc.add_memory(
                            resident_id=current_resident.id,
                            type="event",
                            content=f"玩家分享了一个{media_type}：{text or '(无文字描述)'}",
                            importance=0.6,
                            source="chat_player",
                            related_user_id=user_id,
                            media_url=media_url,
                            media_summary=full_reply[:500],  # cap summary length
                        )

                    # Reward creator (1 SC per turn) and send notification if they're online
                    from app.services.coin_service import reward_creator_passive
                    creator_notification = await reward_creator_passive(db, current_resident.creator_id, current_resident.slug)
                    if creator_notification:
                        await manager.send(current_resident.creator_id, creator_notification)

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

                    # Release the resident lock
                    manager.unlock_resident(resident_id)

                    prev_status = fresh_resident.status if fresh_resident else "idle"
                    await manager.send(user_id, {
                        "type": "chat_ended",
                        "conversation_id": fresh_conv.id if fresh_conv else "",
                    })

                    # Notify next queued user
                    next_user = manager.dequeue(resident_id)
                    if next_user:
                        await manager.send(next_user, {
                            "type": "queue_ready",
                            "resident_slug": resident_slug,
                            "resident_name": fresh_resident.name if fresh_resident else "",
                        })

                    await manager.broadcast(
                        {"type": "resident_status", "resident_slug": resident_slug, "status": prev_status},
                        exclude=user_id,
                    )
                    current_conversation = None
                    current_resident = None
                    saved_chat_messages = list(chat_messages)
                    chat_messages = []

                    # Extract memories from the conversation (non-blocking)
                    import asyncio
                    asyncio.create_task(_extract_chat_memories(
                        resident_id=resident_id,
                        user_id=user_id,
                        user_name=user_name,
                        chat_messages=list(saved_chat_messages),
                    ))

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

                elif msg_type == "player_chat":
                    target_id = data.get("target_id", "")
                    text = data.get("text", "").strip()
                    if not target_id or not text:
                        await manager.send(user_id, {"type": "error", "message": "target_id and text required"})
                        continue

                    svc = PlayerChatService(db)
                    target_online = target_id in manager.active
                    result = await svc.route_message(user_id, target_id, text, target_online)

                    action = result.get("action")

                    if action == "error":
                        await manager.send(user_id, {"type": "error", "message": result["message"]})
                    elif action == "forward":
                        # Manual mode, target online -> forward to target
                        payload = {
                            "type": "player_chat_msg",
                            "from_id": user_id,
                            "text": text,
                            "is_auto": False,
                        }
                        await manager.send(target_id, payload)
                        await manager.send(user_id, {
                            "type": "player_chat_sent",
                            "target_id": target_id,
                            "text": text,
                        })
                    elif action == "queued":
                        await manager.send(user_id, {
                            "type": "player_chat_queued",
                            "target_id": target_id,
                            "text": text,
                        })
                    elif action == "auto_reply":
                        # Send auto-reply back to the sender
                        await manager.send(user_id, {
                            "type": "player_chat_reply",
                            "from_id": target_id,
                            "text": result["text"],
                            "is_auto": True,
                        })
                        # Also notify the target if they are online
                        if target_online:
                            await manager.send(target_id, {
                                "type": "player_chat_auto_sent",
                                "from_id": user_id,
                                "reply_text": result["text"],
                                "original_text": text,
                                "is_auto": True,
                            })

                elif msg_type == "set_reply_mode":
                    mode = data.get("mode", "")
                    if mode not in ("auto", "manual"):
                        await manager.send(user_id, {"type": "error", "message": "mode must be 'auto' or 'manual'"})
                        continue

                    # Fetch the user's player Resident and update reply_mode
                    user_result = await db.execute(select(User).where(User.id == user_id))
                    u = user_result.scalar_one_or_none()
                    if not u or not u.player_resident_id:
                        await manager.send(user_id, {"type": "error", "message": "No player resident bound"})
                        continue

                    res_result = await db.execute(
                        select(Resident).where(Resident.id == u.player_resident_id)
                    )
                    resident = res_result.scalar_one_or_none()
                    if not resident:
                        await manager.send(user_id, {"type": "error", "message": "Player resident not found"})
                        continue

                    resident.reply_mode = mode
                    await db.commit()
                    await manager.send(user_id, {
                        "type": "reply_mode_updated",
                        "mode": mode,
                    })

    except WebSocketDisconnect:
        if current_conversation and current_resident:
            manager.unlock_resident(current_resident.id)
            async with async_session() as db:
                result = await db.execute(select(Resident).where(Resident.id == current_resident.id))
                r = result.scalar_one_or_none()
                if r and r.status == "chatting":
                    r.status = "popular" if r.heat >= 50 else "idle"
                    await db.commit()

        # Save current position to User.last_x / last_y for next session
        pos = manager.positions.get(user_id)
        if pos:
            async with async_session() as db:
                result = await db.execute(select(User).where(User.id == user_id))
                u = result.scalar_one_or_none()
                if u and u.player_resident_id:
                    u.last_x = int(pos.get("x", u.last_x))
                    u.last_y = int(pos.get("y", u.last_y))
                    await db.commit()

        await manager.broadcast({"type": "player_left", "player_id": user_id}, exclude=user_id)
        manager.disconnect(user_id)


async def _extract_chat_memories(
    resident_id: str,
    user_id: str,
    user_name: str,
    chat_messages: list[dict],
):
    """Background task: extract event memories and update relationship after chat ends."""
    if len(chat_messages) < 2:
        return  # Too short to extract meaningful memories

    try:
        async with async_session() as db:
            result = await db.execute(select(Resident).where(Resident.id == resident_id))
            resident = result.scalar_one_or_none()
            if not resident:
                return

            # Capture original SBTI type before memory extraction (which may trigger evolution)
            original_sbti_type = (resident.meta_json or {}).get("sbti", {}).get("type")

            # Format conversation text
            conv_text = "\n".join(
                f"{'玩家' if m['role'] == 'user' else resident.name}: {m['content']}"
                for m in chat_messages
            )

            svc = MemoryService(db)

            # 1. Extract event memories
            events = await svc.extract_events(
                resident=resident,
                other_name=user_name,
                conversation_text=conv_text,
                source="chat_player",
            )

            # 2. Update relationship memory
            if events:
                await svc.update_relationship_via_llm(
                    resident=resident,
                    other_name=user_name,
                    user_id=user_id,
                    event_summaries=[e.content for e in events],
                )

            # 3. Check if reflection is needed
            event_count = await svc.count_events_since_last_reflection(resident.id)
            if event_count >= 15:
                await svc.generate_reflections(resident=resident)

            # 4. Check for personality type change and broadcast
            await db.refresh(resident)
            new_sbti = (resident.meta_json or {}).get("sbti", {})
            new_type = new_sbti.get("type")
            old_type = original_sbti_type

            if new_type and old_type and new_type != old_type:
                await manager.broadcast(
                    {
                        "type": "resident_type_changed",
                        "resident_id": resident_id,
                        "old_type": old_type,
                        "new_type": new_type,
                        "type_name": new_sbti.get("type_name", ""),
                    },
                )

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Memory extraction failed: %s", e)
