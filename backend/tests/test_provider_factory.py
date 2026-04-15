import pytest
from unittest.mock import AsyncMock, patch

from app.memory.providers.factory import (
    get_active_provider,
    invalidate_provider_cache,
)
from app.memory.providers.ollama import OllamaProvider
from app.memory.providers.siliconflow import SiliconFlowProvider


@pytest.fixture(autouse=True)
async def _clear_cache():
    invalidate_provider_cache()
    yield
    invalidate_provider_cache()


@pytest.mark.anyio
async def test_factory_returns_ollama_when_config_says_ollama():
    fake_group = {
        "embedding.provider": "ollama",
        "embedding.dimensions": 1024,
        "embedding.ollama.base_url": "http://ollama.local:11434",
        "embedding.ollama.model": "qwen3-embedding:4b",
    }
    with patch("app.memory.providers.factory._read_embedding_config", new=AsyncMock(return_value=fake_group)):
        provider = await get_active_provider()

    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://ollama.local:11434"
    assert provider.model == "qwen3-embedding:4b"
    assert provider.dimensions == 1024


@pytest.mark.anyio
async def test_factory_returns_siliconflow_when_config_says_siliconflow():
    fake_group = {
        "embedding.provider": "siliconflow",
        "embedding.dimensions": 1024,
        "embedding.siliconflow.api_key": "sk-abc",
        "embedding.siliconflow.base_url": "https://api.siliconflow.cn/v1",
        "embedding.siliconflow.model": "Qwen/Qwen3-Embedding-8B",
    }
    with patch("app.memory.providers.factory._read_embedding_config", new=AsyncMock(return_value=fake_group)):
        provider = await get_active_provider()

    assert isinstance(provider, SiliconFlowProvider)
    assert provider.api_key == "sk-abc"
    assert provider.model == "Qwen/Qwen3-Embedding-8B"


@pytest.mark.anyio
async def test_factory_caches_provider_within_ttl():
    fake_group = {
        "embedding.provider": "ollama",
        "embedding.dimensions": 1024,
        "embedding.ollama.base_url": "http://a",
        "embedding.ollama.model": "m",
    }
    reader = AsyncMock(return_value=fake_group)
    with patch("app.memory.providers.factory._read_embedding_config", new=reader):
        p1 = await get_active_provider()
        p2 = await get_active_provider()

    assert p1 is p2
    assert reader.await_count == 1


@pytest.mark.anyio
async def test_invalidate_cache_forces_rebuild():
    fake_group = {
        "embedding.provider": "ollama",
        "embedding.dimensions": 1024,
        "embedding.ollama.base_url": "http://a",
        "embedding.ollama.model": "m",
    }
    reader = AsyncMock(return_value=fake_group)
    with patch("app.memory.providers.factory._read_embedding_config", new=reader):
        await get_active_provider()
        invalidate_provider_cache()
        await get_active_provider()

    assert reader.await_count == 2


@pytest.mark.anyio
async def test_factory_falls_back_to_ollama_if_provider_unknown():
    fake_group = {
        "embedding.provider": "martian",  # bogus value
        "embedding.dimensions": 1024,
        "embedding.ollama.base_url": "http://a",
        "embedding.ollama.model": "m",
    }
    with patch("app.memory.providers.factory._read_embedding_config", new=AsyncMock(return_value=fake_group)):
        provider = await get_active_provider()

    assert isinstance(provider, OllamaProvider)
