import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.models.resident import Resident
from app.models.memory import Memory
from app.memory.service import MemoryService


@pytest.fixture
async def resident(db_session):
    r = Resident(
        id="ext-test-res",
        slug="ext-test-res",
        name="ExtractResident",
        district="engineering",
        status="idle",
        ability_md="Python expert",
        persona_md="Thoughtful and quiet",
        soul_md="Seeks truth",
        creator_id="test-user",
        meta_json={"sbti": {"type": "THIN-K", "type_name": "思考者", "dimensions": {
            "S1": "H", "S2": "H", "S3": "L",
            "E1": "H", "E2": "M", "E3": "H",
            "A1": "M", "A2": "L", "A3": "H",
            "Ac1": "M", "Ac2": "H", "Ac3": "M",
            "So1": "L", "So2": "H", "So3": "H",
        }}},
    )
    db_session.add(r)
    await db_session.commit()
    return r


def _mock_llm_response(content: str):
    """Create a mock that simulates anthropic client.messages.create()."""
    mock_msg = MagicMock()
    mock_block = MagicMock()
    mock_block.text = content
    mock_msg.content = [mock_block]
    return mock_msg


@pytest.mark.anyio
async def test_extract_events_from_conversation(db_session, resident):
    svc = MemoryService(db_session)

    llm_response = json.dumps({
        "memories": [
            {"content": "Discussed Python async patterns", "importance": 0.6},
            {"content": "Visitor shared frustration about debugging", "importance": 0.5},
        ]
    })

    with patch("app.memory.service.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_llm_response(llm_response))
        mock_get_client.return_value = mock_client

        with patch("app.memory.service.generate_embedding", return_value=[0.1] * 1024):
            memories = await svc.extract_events(
                resident=resident,
                other_name="Player1",
                conversation_text="Player1: How do I use async?\nExtractResident: Let me explain...",
            )

    assert len(memories) == 2
    assert memories[0].type == "event"
    assert memories[0].source == "chat_player"
    assert memories[0].embedding is not None


@pytest.mark.anyio
async def test_extract_events_handles_llm_failure(db_session, resident):
    svc = MemoryService(db_session)

    with patch("app.memory.service.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("LLM down"))
        mock_get_client.return_value = mock_client

        memories = await svc.extract_events(
            resident=resident,
            other_name="Player1",
            conversation_text="Hello!",
        )

    assert memories == []


@pytest.mark.anyio
async def test_update_relationship_via_llm(db_session, resident):
    svc = MemoryService(db_session)

    llm_response = json.dumps({
        "content": "Player1 is a curious beginner interested in Python async",
        "importance": 0.6,
        "metadata": {"affinity": 0.4, "trust": 0.5, "tags": ["beginner", "curious"]},
    })

    with patch("app.memory.service.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_llm_response(llm_response))
        mock_get_client.return_value = mock_client

        rel = await svc.update_relationship_via_llm(
            resident=resident,
            other_name="Player1",
            user_id="user-1",
            event_summaries=["Discussed Python async patterns"],
        )

    assert rel.content == "Player1 is a curious beginner interested in Python async"
    assert rel.metadata_json["affinity"] == 0.4


@pytest.mark.anyio
async def test_trigger_reflection(db_session, resident):
    svc = MemoryService(db_session)

    # Seed some event and relationship memories
    for i in range(5):
        await svc.add_memory(resident.id, "event", f"Event {i}", 0.5, "chat_player")
    await svc.add_memory(
        resident.id, "relationship", "A friendly visitor",
        0.5, "chat_player", related_user_id="user-1",
    )

    llm_response = json.dumps({
        "reflections": [
            {"content": "I notice visitors often ask about async programming", "importance": 0.7},
            {"content": "People seem genuinely interested in learning", "importance": 0.6},
        ]
    })

    with patch("app.memory.service.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_llm_response(llm_response))
        mock_get_client.return_value = mock_client

        reflections = await svc.generate_reflections(resident=resident)

    assert len(reflections) == 2
    assert reflections[0].type == "reflection"
    assert reflections[0].source == "reflection"
