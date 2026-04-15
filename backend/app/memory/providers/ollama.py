import logging
import httpx

from app.memory.providers.base import zero_vector

logger = logging.getLogger(__name__)


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, model: str, dimensions: int = 1024):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions

    async def embed(self, text: str) -> list[float] | None:
        if not text or not text.strip():
            return None
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                resp = await client.post(
                    f"{self.base_url}/api/embed",
                    json={
                        "model": self.model,
                        "input": text,
                        "truncate": True,
                        "options": {"num_ctx": 2048},
                    },
                    timeout=30.0,
                )
            if resp.status_code != 200:
                logger.warning("Ollama embedding failed: %s %s", resp.status_code, resp.text[:200])
                return None
            embeddings = resp.json().get("embeddings", [])
            if not embeddings:
                return None
            return self._fit(embeddings[0])
        except Exception as e:
            logger.warning("Ollama embedding error: %s", e)
            return None

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                resp = await client.post(
                    f"{self.base_url}/api/embed",
                    json={
                        "model": self.model,
                        "input": texts,
                        "truncate": True,
                        "options": {"num_ctx": 2048},
                    },
                    timeout=60.0,
                )
            if resp.status_code != 200:
                logger.warning("Ollama batch embedding failed: %s", resp.status_code)
                return [zero_vector(self.dimensions)] * len(texts)
            embeddings = resp.json().get("embeddings", [])
            result = [self._fit(vec) for vec in embeddings]
            while len(result) < len(texts):
                result.append(zero_vector(self.dimensions))
            return result
        except Exception as e:
            logger.warning("Ollama batch embedding error: %s", e)
            return [zero_vector(self.dimensions)] * len(texts)

    def _fit(self, vec: list[float]) -> list[float]:
        """Truncate or zero-pad vec to exactly self.dimensions length."""
        if len(vec) > self.dimensions:
            return vec[:self.dimensions]
        if len(vec) < self.dimensions:
            return vec + [0.0] * (self.dimensions - len(vec))
        return vec
