import pytest
from unittest.mock import AsyncMock, patch

from app.memory.embedding import generate_embedding, generate_embeddings_batch


@pytest.mark.anyio
async def test_generate_embedding_delegates_to_active_provider():
    mock_provider = AsyncMock()
    mock_provider.embed = AsyncMock(return_value=[0.42] * 1024)

    with patch("app.memory.providers.factory.get_active_provider", new=AsyncMock(return_value=mock_provider)):
        result = await generate_embedding("hello")

    assert result == [0.42] * 1024
    mock_provider.embed.assert_awaited_once_with("hello")


@pytest.mark.anyio
async def test_generate_embeddings_batch_delegates_to_active_provider():
    mock_provider = AsyncMock()
    mock_provider.embed_batch = AsyncMock(return_value=[[0.1] * 1024, [0.2] * 1024])

    with patch("app.memory.providers.factory.get_active_provider", new=AsyncMock(return_value=mock_provider)):
        results = await generate_embeddings_batch(["a", "b"])

    assert len(results) == 2
    assert results[0] == [0.1] * 1024
    mock_provider.embed_batch.assert_awaited_once_with(["a", "b"])
