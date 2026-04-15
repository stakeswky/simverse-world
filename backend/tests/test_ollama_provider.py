import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.memory.providers.ollama import OllamaProvider


@pytest.mark.anyio
async def test_ollama_embed_returns_1024_dim_vector():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embeddings": [[0.1] * 1024]}

    with patch("app.memory.providers.ollama.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__.return_value = client_instance

        provider = OllamaProvider(base_url="http://localhost:11434", model="qwen3-embedding:4b")
        result = await provider.embed("hello")

    assert result is not None
    assert len(result) == 1024
    assert result[0] == 0.1


@pytest.mark.anyio
async def test_ollama_embed_empty_text_returns_none():
    provider = OllamaProvider(base_url="http://localhost:11434", model="qwen3-embedding:4b")
    assert await provider.embed("") is None
    assert await provider.embed("   ") is None


@pytest.mark.anyio
async def test_ollama_embed_http_error_returns_none():
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "server error"

    with patch("app.memory.providers.ollama.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__.return_value = client_instance

        provider = OllamaProvider(base_url="http://localhost:11434", model="qwen3-embedding:4b")
        result = await provider.embed("test")

    assert result is None


@pytest.mark.anyio
async def test_ollama_embed_truncates_oversized_vector():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embeddings": [[0.5] * 2048]}

    with patch("app.memory.providers.ollama.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__.return_value = client_instance

        provider = OllamaProvider(base_url="http://localhost:11434", model="m", dimensions=1024)
        result = await provider.embed("test")

    assert len(result) == 1024


@pytest.mark.anyio
async def test_ollama_batch_returns_per_text_vectors():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embeddings": [[0.1] * 1024, [0.2] * 1024]}

    with patch("app.memory.providers.ollama.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__.return_value = client_instance

        provider = OllamaProvider(base_url="http://localhost:11434", model="m")
        results = await provider.embed_batch(["one", "two"])

    assert len(results) == 2
    assert results[0][0] == 0.1
    assert results[1][0] == 0.2
