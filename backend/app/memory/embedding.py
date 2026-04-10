import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


async def generate_embedding(text: str) -> list[float] | None:
    """Generate a 1024-dim embedding for a single text using local Ollama.

    Returns None if text is empty or Ollama call fails.
    """
    if not text or not text.strip():
        return None

    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/embed",
                json={
                    "model": settings.ollama_embed_model,
                    "input": text,
                    "truncate": True,
                    "options": {"num_ctx": 2048},
                },
                timeout=30.0,
            )
        if resp.status_code != 200:
            logger.warning("Ollama embedding failed: %s %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        embeddings = data.get("embeddings", [])
        if not embeddings:
            return None
        vec = embeddings[0]
        # Truncate or pad to configured dimensions
        dim = settings.ollama_embed_dimensions
        if len(vec) > dim:
            vec = vec[:dim]
        elif len(vec) < dim:
            vec = vec + [0.0] * (dim - len(vec))
        return vec
    except Exception as e:
        logger.warning("Ollama embedding error: %s", e)
        return None


async def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts in a single Ollama call.

    Returns list of vectors. Failed items are zero-vectors.
    """
    if not texts:
        return []

    dim = settings.ollama_embed_dimensions
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/embed",
                json={
                    "model": settings.ollama_embed_model,
                    "input": texts,
                    "truncate": True,
                    "options": {"num_ctx": 2048},
                },
                timeout=60.0,
            )
        if resp.status_code != 200:
            logger.warning("Ollama batch embedding failed: %s", resp.status_code)
            return [[0.0] * dim] * len(texts)
        data = resp.json()
        embeddings = data.get("embeddings", [])
        result = []
        for vec in embeddings:
            if len(vec) > dim:
                vec = vec[:dim]
            elif len(vec) < dim:
                vec = vec + [0.0] * (dim - len(vec))
            result.append(vec)
        # Pad missing entries
        while len(result) < len(texts):
            result.append([0.0] * dim)
        return result
    except Exception as e:
        logger.warning("Ollama batch embedding error: %s", e)
        return [[0.0] * dim] * len(texts)
