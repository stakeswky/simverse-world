import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from app.media.model_router import ModelRouter


def _make_stream_mock(chunks: list[str]):
    """Create a mock async context manager that yields text chunks."""
    class FakeStream:
        def __init__(self):
            self.text_stream = _async_gen(chunks)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    async def _async_gen(items):
        for item in items:
            yield item

    return FakeStream()


def _mock_llm_response(text: str):
    mock_msg = MagicMock()
    mock_block = MagicMock()
    mock_block.text = text
    mock_msg.content = [mock_block]
    return mock_msg


@pytest.mark.anyio
async def test_image_routes_to_main_model_with_image_block():
    """Images are sent to the main model as an image content block."""
    system_prompt = "You are a helpful assistant."
    messages = [{"role": "user", "content": "What is in this image?"}]
    image_url = "https://example.com/photo.jpg"

    collected_chunks = []

    with patch("app.media.model_router.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _make_stream_mock(["It's ", "a cat!"])
        mock_get_client.return_value = mock_client

        router = ModelRouter()
        async for chunk in router.chat_with_media(
            system_prompt=system_prompt,
            messages=messages,
            media_url=image_url,
            media_type="image",
        ):
            collected_chunks.append(chunk)

    assert collected_chunks == ["It's ", "a cat!"]

    # Verify client.messages.stream was called with image content block
    call_kwargs = mock_client.messages.stream.call_args.kwargs
    assert call_kwargs["system"] == system_prompt
    # Last message should have content list with text + image blocks
    last_msg = call_kwargs["messages"][-1]
    assert last_msg["role"] == "user"
    content = last_msg["content"]
    # Should have text block + image block
    types = [block["type"] for block in content]
    assert "text" in types
    assert "image" in types
    # Image block should have the URL
    image_block = next(b for b in content if b["type"] == "image")
    assert image_block["source"]["type"] == "url"
    assert image_block["source"]["url"] == image_url


@pytest.mark.anyio
async def test_video_gets_summary_then_main_model():
    """Videos: kimi-k2.5 summarizes the video, then main model responds with summary injected."""
    system_prompt = "You are a helpful assistant."
    messages = [{"role": "user", "content": "What happens in this video?"}]
    video_url = "https://example.com/clip.mp4"
    video_summary = "The video shows a cat chasing a ball of yarn."

    collected_chunks = []

    with patch("app.media.model_router.get_client") as mock_get_client:
        # Both calls go to the same client instance in this setup
        mock_kimi_client = MagicMock()
        mock_kimi_client.messages.create = AsyncMock(
            return_value=_mock_llm_response(video_summary)
        )
        mock_main_client = MagicMock()
        mock_main_client.messages.stream.return_value = _make_stream_mock(["Great video!"])

        # First call returns kimi client, second returns main client
        mock_get_client.side_effect = [mock_kimi_client, mock_main_client]

        router = ModelRouter()
        async for chunk in router.chat_with_media(
            system_prompt=system_prompt,
            messages=messages,
            media_url=video_url,
            media_type="video",
        ):
            collected_chunks.append(chunk)

    assert collected_chunks == ["Great video!"]

    # First get_client call should use kimi model
    kimi_create_kwargs = mock_kimi_client.messages.create.call_args.kwargs
    assert kimi_create_kwargs["model"] == "kimi-k2.5"

    # Main model messages should include video summary in text
    main_stream_kwargs = mock_main_client.messages.stream.call_args.kwargs
    last_msg = main_stream_kwargs["messages"][-1]
    assert video_summary in str(last_msg["content"])


@pytest.mark.anyio
async def test_understand_video_calls_kimi():
    """_understand_video() calls kimi-k2.5 with the video URL."""
    video_url = "https://example.com/test.mp4"
    expected_summary = "A dog runs across a field."

    with patch("app.media.model_router.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_llm_response(expected_summary)
        )
        mock_get_client.return_value = mock_client

        router = ModelRouter()
        summary = await router._understand_video(video_url)

    assert summary == expected_summary

    create_kwargs = mock_client.messages.create.call_args.kwargs
    assert create_kwargs["model"] == "kimi-k2.5"
    # Video URL should appear somewhere in the messages
    messages_str = str(create_kwargs["messages"])
    assert video_url in messages_str


@pytest.mark.anyio
async def test_chat_with_media_no_media_falls_back_to_text():
    """If media_url is None, behaves like a regular text chat stream."""
    system_prompt = "You are helpful."
    messages = [{"role": "user", "content": "Hello"}]

    collected = []

    with patch("app.media.model_router.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _make_stream_mock(["Hi there!"])
        mock_get_client.return_value = mock_client

        router = ModelRouter()
        async for chunk in router.chat_with_media(
            system_prompt=system_prompt,
            messages=messages,
            media_url=None,
            media_type=None,
        ):
            collected.append(chunk)

    assert collected == ["Hi there!"]

    call_kwargs = mock_client.messages.stream.call_args.kwargs
    last_msg = call_kwargs["messages"][-1]
    # Content should be plain string, not list
    assert isinstance(last_msg["content"], str)
