"""Provider factory — full implementation in Task 3."""
from app.memory.providers.base import EmbeddingProvider


async def get_active_provider() -> EmbeddingProvider:
    """Placeholder returning default Ollama provider. Replaced in Task 3."""
    from app.config import settings
    from app.memory.providers.ollama import OllamaProvider
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embed_model,
        dimensions=settings.ollama_embed_dimensions,
    )
