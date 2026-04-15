"""Embedding facade — delegates to the active EmbeddingProvider.

Kept as a module-level API so existing callers in memory/service.py don't change.
Active provider is chosen by factory (Task 3).
"""
from app.memory.providers import EmbeddingProvider  # noqa: F401  (re-export)


async def generate_embedding(text: str) -> list[float] | None:
    from app.memory.providers.factory import get_active_provider
    provider = await get_active_provider()
    return await provider.embed(text)


async def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    from app.memory.providers.factory import get_active_provider
    provider = await get_active_provider()
    return await provider.embed_batch(texts)
