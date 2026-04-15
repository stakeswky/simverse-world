"""Embedding provider factory with TTL cache.

Reads `group="embedding"` from SystemConfig; falls back to settings defaults.
Cache is invalidated either by TTL expiry (60s) or by explicit call.
"""
import logging
import time
from typing import Any

from app.config import settings
from app.database import async_session
from app.memory.providers.base import EmbeddingProvider
from app.memory.providers.ollama import OllamaProvider
from app.memory.providers.siliconflow import SiliconFlowProvider
from app.services.config_service import ConfigService

logger = logging.getLogger(__name__)

_TTL_SECONDS = 60.0

_cached_provider: EmbeddingProvider | None = None
_cached_at: float = 0.0


async def _read_embedding_config() -> dict[str, Any]:
    """Load embedding config from DB merged with env defaults.

    Returns a dict with keys like `embedding.provider`, `embedding.dimensions`, etc.
    """
    defaults = {
        "embedding.provider": "ollama",
        "embedding.dimensions": settings.ollama_embed_dimensions,
        "embedding.ollama.base_url": settings.ollama_base_url,
        "embedding.ollama.model": settings.ollama_embed_model,
        "embedding.siliconflow.api_key": "",
        "embedding.siliconflow.base_url": "https://api.siliconflow.cn/v1",
        "embedding.siliconflow.model": "Qwen/Qwen3-Embedding-8B",
    }
    try:
        async with async_session() as session:
            svc = ConfigService(session)
            db_values = await svc.get_group("embedding")
    except Exception as e:
        logger.warning("Failed to read embedding config from DB, using defaults: %s", e)
        return defaults
    merged = {**defaults, **db_values}
    return merged


def _build_provider(cfg: dict[str, Any]) -> EmbeddingProvider:
    name = str(cfg.get("embedding.provider", "ollama")).lower()
    dim = int(cfg.get("embedding.dimensions", 1024))

    if name == "siliconflow":
        api_key = str(cfg.get("embedding.siliconflow.api_key") or "")
        if not api_key:
            logger.warning("SiliconFlow selected but api_key empty; falling back to Ollama")
        else:
            return SiliconFlowProvider(
                api_key=api_key,
                model=str(cfg.get("embedding.siliconflow.model") or "Qwen/Qwen3-Embedding-8B"),
                base_url=str(cfg.get("embedding.siliconflow.base_url") or "https://api.siliconflow.cn/v1"),
                dimensions=dim,
            )
    # Default / ollama / unknown → Ollama
    if name not in ("ollama", "siliconflow"):
        logger.warning("Unknown provider '%s', falling back to ollama", name)

    return OllamaProvider(
        base_url=str(cfg.get("embedding.ollama.base_url") or settings.ollama_base_url),
        model=str(cfg.get("embedding.ollama.model") or settings.ollama_embed_model),
        dimensions=dim,
    )


async def get_active_provider() -> EmbeddingProvider:
    """Return the active embedding provider (cached for _TTL_SECONDS)."""
    global _cached_provider, _cached_at
    now = time.monotonic()
    if _cached_provider is not None and (now - _cached_at) < _TTL_SECONDS:
        return _cached_provider
    cfg = await _read_embedding_config()
    _cached_provider = _build_provider(cfg)
    _cached_at = now
    return _cached_provider


def invalidate_provider_cache() -> None:
    """Force the next get_active_provider() to rebuild from latest config."""
    global _cached_provider, _cached_at
    _cached_provider = None
    _cached_at = 0.0
