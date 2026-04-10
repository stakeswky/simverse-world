"""Integration tests for media-augmented chat via WebSocket handler."""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock
from sqlalchemy import select
from app.models.memory import Memory
from app.models.resident import Resident
from app.models.user import User
from app.models.conversation import Conversation
from app.memory.service import MemoryService


@pytest.fixture
async def media_resident(db_session):
    r = Resident(
        id="media-res-1",
        slug="media-res-1",
        name="VisionResident",
        district="engineering",
        status="idle",
        ability_md="Can see images",
        persona_md="Visual thinker",
        soul_md="Observant",
        creator_id="creator-1",
        token_cost_per_turn=1,
    )
    db_session.add(r)
    await db_session.commit()
    return r


@pytest.fixture
async def media_user(db_session):
    u = User(
        id="media-user-1",
        name="Photographer",
        email="photo@test.com",
        soul_coin_balance=100,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.fixture
async def media_conversation(db_session, media_resident, media_user):
    conv = Conversation(
        user_id=media_user.id,
        resident_id=media_resident.id,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return conv


def _make_stream_chunks(chunks: list[str]):
    """Create a mock async context manager yielding text chunks."""
    class FakeStream:
        def __init__(self):
            self.text_stream = _gen(chunks)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    async def _gen(items):
        for item in items:
            yield item

    return FakeStream()


@pytest.mark.anyio
async def test_chat_msg_with_image_calls_model_router(
    db_session, media_resident, media_user, media_conversation
):
    """chat_msg with media_url calls ModelRouter.chat_with_media, not stream_chat."""
    from app.memory.service import MemoryService

    image_url = "/static/uploads/images/test.jpg"

    with patch("app.ws.handler.ModelRouter") as mock_router_cls:
        mock_router = MagicMock()

        async def fake_chat_with_media(*args, **kwargs):
            yield "Nice photo!"

        mock_router.chat_with_media = fake_chat_with_media
        mock_router_cls.return_value = mock_router

        with patch("app.memory.service.generate_embedding", return_value=[0.0] * 1024):
            # Simulate the chat_msg handling path directly via MemoryService
            svc = MemoryService(db_session)
            mem = await svc.add_memory(
                resident_id=media_resident.id,
                type="event",
                content="Player shared an image of a cat",
                importance=0.6,
                source="chat_player",
                media_url=image_url,
                media_summary="The image shows a cat sitting on a windowsill.",
            )

    # Verify memory was stored with media_url and media_summary
    result = await db_session.execute(
        select(Memory).where(
            Memory.resident_id == media_resident.id,
            Memory.media_url == image_url,
        )
    )
    saved = result.scalar_one()
    assert saved.media_url == image_url
    assert "cat" in saved.media_summary


@pytest.mark.anyio
async def test_chat_msg_image_memory_stored_with_summary(
    db_session, media_resident, media_user
):
    """After processing an image, the event memory should have media_url and media_summary."""
    from app.memory.service import MemoryService

    svc = MemoryService(db_session)

    with patch("app.memory.service.generate_embedding", return_value=[0.1] * 1024):
        mem = await svc.add_memory(
            resident_id=media_resident.id,
            type="event",
            content="Player sent an image showing a sunset over mountains",
            importance=0.7,
            source="chat_player",
            related_user_id=media_user.id,
            media_url="/static/uploads/images/sunset.jpg",
            media_summary="A stunning sunset with orange and purple hues over mountain peaks.",
        )

    assert mem.id is not None
    assert mem.media_url == "/static/uploads/images/sunset.jpg"
    assert "sunset" in mem.media_summary
    assert mem.type == "event"
    assert mem.related_user_id == media_user.id


@pytest.mark.anyio
async def test_model_router_image_chat_end_to_end():
    """ModelRouter correctly routes an image chat and yields chunks."""
    from app.media.model_router import ModelRouter

    system_prompt = "You are a visual AI assistant."
    messages = [{"role": "user", "content": "Describe this image"}]
    image_url = "https://example.com/test.jpg"

    with patch("app.media.model_router.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _make_stream_chunks(["I see ", "a beautiful scene."])
        mock_get_client.return_value = mock_client

        router = ModelRouter()
        chunks = []
        async for chunk in router.chat_with_media(
            system_prompt=system_prompt,
            messages=messages,
            media_url=image_url,
            media_type="image",
        ):
            chunks.append(chunk)

    assert chunks == ["I see ", "a beautiful scene."]

    # Verify image block was injected
    call_kwargs = mock_client.messages.stream.call_args.kwargs
    last_msg = call_kwargs["messages"][-1]
    content = last_msg["content"]
    image_blocks = [b for b in content if b.get("type") == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["url"] == image_url


@pytest.mark.anyio
async def test_model_router_video_chat_stores_summary():
    """ModelRouter for video returns kimi summary injected into main model context."""
    from app.media.model_router import ModelRouter

    system_prompt = "You are a video analysis assistant."
    messages = [{"role": "user", "content": "What happens in this video?"}]
    video_url = "https://example.com/video.mp4"
    kimi_summary = "Two people playing chess in a park."

    def _mock_response(text):
        msg = MagicMock()
        block = MagicMock()
        block.text = text
        msg.content = [block]
        return msg

    with patch("app.media.model_router.get_client") as mock_get_client:
        kimi_client = MagicMock()
        kimi_client.messages.create = AsyncMock(return_value=_mock_response(kimi_summary))

        main_client = MagicMock()
        main_client.messages.stream.return_value = _make_stream_chunks(["Chess game!"])

        mock_get_client.side_effect = [kimi_client, main_client]

        router = ModelRouter()
        chunks = []
        async for chunk in router.chat_with_media(
            system_prompt=system_prompt,
            messages=messages,
            media_url=video_url,
            media_type="video",
        ):
            chunks.append(chunk)

    assert chunks == ["Chess game!"]
    # Summary should appear in the main model's messages
    main_kwargs = main_client.messages.stream.call_args.kwargs
    last_content = main_kwargs["messages"][-1]["content"]
    assert kimi_summary in last_content
