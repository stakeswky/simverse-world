import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select
from app.models.resident import Resident
from app.models.memory import Memory
from app.agent.chat import resident_chat, _chat_cooldowns


@pytest.fixture
async def chat_pair(db_session):
    initiator = Resident(
        id="chat-init",
        slug="chat-init",
        name="Initiator",
        district="engineering",
        status="idle",
        ability_md="Likes talking",
        persona_md="Outgoing",
        soul_md="Social",
        creator_id="c1",
        meta_json={"sbti": {"type": "GOGO", "type_name": "行者", "dimensions": {
            "So1": "H", "So2": "M", "So3": "H",
            "S1": "H", "S2": "H", "S3": "M",
            "E1": "H", "E2": "M", "E3": "H",
            "A1": "M", "A2": "M", "A3": "H",
            "Ac1": "H", "Ac2": "H", "Ac3": "H",
        }}},
    )
    target = Resident(
        id="chat-tgt",
        slug="chat-tgt",
        name="Target",
        district="engineering",
        status="idle",
        ability_md="Good listener",
        persona_md="Reflective",
        soul_md="Curious",
        creator_id="c1",
        meta_json={"sbti": {"type": "THIN-K", "type_name": "思考者", "dimensions": {
            "So1": "L", "So2": "H", "So3": "H",
            "S1": "H", "S2": "H", "S3": "L",
            "E1": "H", "E2": "M", "E3": "H",
            "A1": "M", "A2": "L", "A3": "H",
            "Ac1": "M", "Ac2": "H", "Ac3": "M",
        }}},
    )
    db_session.add(initiator)
    db_session.add(target)
    await db_session.commit()
    return initiator, target


def _mock_llm_text(text: str):
    mock_msg = MagicMock()
    mock_block = MagicMock()
    mock_block.text = text
    mock_msg.content = [mock_block]
    return mock_msg


@pytest.mark.anyio
async def test_resident_chat_creates_memories(db_session, chat_pair):
    initiator, target = chat_pair
    _chat_cooldowns.clear()

    dialog_responses = [
        "你好啊，今天天气不错！",       # turn 1: initiator opens
        "是啊，你去哪里玩了吗？",        # turn 2: target replies
        "我刚从工程区回来，很有意思。",  # turn 3: initiator
    ]
    extract_response = json.dumps({
        "memories": [{"content": "和 Target 聊了天气和工程区", "importance": 0.5}]
    })
    rel_response = json.dumps({
        "content": "Target 是个好相处的人",
        "importance": 0.5,
        "metadata": {"affinity": 0.4, "trust": 0.5, "tags": ["friendly"]},
    })
    summary_response = json.dumps({
        "summary": "Initiator 和 Target 聊了天气和工程区的趣事",
        "mood": "positive",
    })

    tgt_extract_response = json.dumps({
        "memories": [{"content": "和 Initiator 聊了天气和工程区", "importance": 0.5}]
    })

    call_idx = 0
    def side_effect(*args, **kwargs):
        nonlocal call_idx
        # Order: 3 dialog turns, initiator extract, target extract, initiator rel update, target rel update, summary
        responses = dialog_responses + [extract_response, tgt_extract_response, rel_response, rel_response, summary_response]
        resp = _mock_llm_text(responses[min(call_idx, len(responses) - 1)])
        call_idx += 1
        return resp

    with patch("app.agent.chat.get_client") as mock_get_client, \
         patch("app.memory.service.get_client") as mock_mem_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=side_effect)
        mock_get_client.return_value = mock_client
        mock_mem_client.return_value = mock_client

        result = await resident_chat(db_session, initiator, target, max_turns=3)

    assert "summary" in result
    assert len(result["summary"]) > 0
    assert "mood" in result

    # Both residents should return to idle
    await db_session.refresh(initiator)
    await db_session.refresh(target)
    assert initiator.status == "idle"
    assert target.status == "idle"

    # Memories should be created for both
    init_mems = (await db_session.execute(
        select(Memory).where(Memory.resident_id == initiator.id, Memory.type == "event")
    )).scalars().all()
    tgt_mems = (await db_session.execute(
        select(Memory).where(Memory.resident_id == target.id, Memory.type == "event")
    )).scalars().all()
    assert len(init_mems) >= 1
    assert len(tgt_mems) >= 1


@pytest.mark.anyio
async def test_resident_chat_cooldown(db_session, chat_pair):
    initiator, target = chat_pair
    _chat_cooldowns.clear()

    # Manually set a fresh cooldown for this pair
    pair_key = tuple(sorted([initiator.id, target.id]))
    import time
    _chat_cooldowns[pair_key] = time.time()  # just set, not expired

    with patch("app.agent.chat.get_client"):
        result = await resident_chat(db_session, initiator, target)

    # Should return None/empty dict if on cooldown
    assert result is None or result.get("skipped") is True


@pytest.mark.anyio
async def test_resident_chat_busy_target_skipped(db_session, chat_pair):
    initiator, target = chat_pair
    _chat_cooldowns.clear()
    target.status = "chatting"
    await db_session.commit()

    with patch("app.agent.chat.get_client"):
        result = await resident_chat(db_session, initiator, target)

    assert result is None or result.get("skipped") is True
