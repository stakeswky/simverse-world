import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select
from app.models.memory import Memory
from app.models.resident import Resident
from app.models.user import User
from app.memory.service import MemoryService


@pytest.fixture
async def chat_resident(db_session):
    r = Resident(
        id="chat-mem-res",
        slug="chat-mem-res",
        name="ChatResident",
        district="engineering",
        status="idle",
        ability_md="Can chat",
        persona_md="Friendly",
        soul_md="Helpful",
        creator_id="test-creator",
        meta_json={"sbti": {"type": "GOGO", "type_name": "行者", "dimensions": {
            "S1": "H", "S2": "H", "S3": "M",
            "E1": "H", "E2": "M", "E3": "H",
            "A1": "M", "A2": "M", "A3": "H",
            "Ac1": "H", "Ac2": "H", "Ac3": "H",
            "So1": "M", "So2": "H", "So3": "M",
        }}},
    )
    db_session.add(r)
    await db_session.commit()
    return r


@pytest.fixture
async def chat_user(db_session):
    u = User(id="chat-mem-user", name="TestPlayer", email="test@chat.com", soul_coin_balance=100)
    db_session.add(u)
    await db_session.commit()
    return u


def _mock_llm_response(content: str):
    mock_msg = MagicMock()
    mock_block = MagicMock()
    mock_block.text = content
    mock_msg.content = [mock_block]
    return mock_msg


@pytest.mark.anyio
async def test_process_chat_end_creates_memories(db_session, chat_resident, chat_user):
    """After chat ends, event memories and relationship should be created."""
    svc = MemoryService(db_session)

    llm_extract_response = json.dumps({
        "memories": [
            {"content": "Discussed Python best practices", "importance": 0.6},
        ]
    })
    llm_relationship_response = json.dumps({
        "content": "TestPlayer is interested in Python",
        "importance": 0.5,
        "metadata": {"affinity": 0.3, "trust": 0.4, "tags": ["python-learner"]},
    })

    with patch("app.memory.service.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _mock_llm_response(llm_extract_response),
                _mock_llm_response(llm_relationship_response),
            ]
        )
        mock_get_client.return_value = mock_client

        with patch("app.memory.service.generate_embedding", return_value=[0.1] * 1024):
            events = await svc.extract_events(
                resident=chat_resident,
                other_name=chat_user.name,
                conversation_text="TestPlayer: How do I write clean Python?\nChatResident: Follow PEP 8...",
            )
            rel = await svc.update_relationship_via_llm(
                resident=chat_resident,
                other_name=chat_user.name,
                user_id=chat_user.id,
                event_summaries=[e.content for e in events],
            )

    # Verify event memories
    result = await db_session.execute(
        select(Memory).where(Memory.resident_id == chat_resident.id, Memory.type == "event")
    )
    event_memories = result.scalars().all()
    assert len(event_memories) == 1
    assert event_memories[0].content == "Discussed Python best practices"
    assert event_memories[0].embedding is not None

    # Verify relationship memory
    result = await db_session.execute(
        select(Memory).where(
            Memory.resident_id == chat_resident.id,
            Memory.type == "relationship",
            Memory.related_user_id == chat_user.id,
        )
    )
    rel_memory = result.scalar_one()
    assert "Python" in rel_memory.content
