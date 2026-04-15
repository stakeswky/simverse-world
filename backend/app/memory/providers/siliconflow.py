import asyncio
import logging
import httpx

from app.memory.providers.base import zero_vector

logger = logging.getLogger(__name__)

_RETRY_DELAYS_SECONDS = (1.0, 2.0)  # 2 retries after initial attempt


class SiliconFlowProvider:
    name = "siliconflow"

    def __init__(
        self,
        api_key: str,
        model: str = "Qwen/Qwen3-Embedding-8B",
        base_url: str = "https://api.siliconflow.cn/v1",
        dimensions: int = 1024,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions

    async def embed(self, text: str) -> list[float] | None:
        if not text or not text.strip():
            return None
        data = await self._request(text)
        if not data:
            return None
        items = data.get("data") or []
        if not items:
            return None
        vec = items[0].get("embedding") or []
        return self._fit(vec) if vec else None

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        data = await self._request(texts)
        if not data:
            return [zero_vector(self.dimensions)] * len(texts)
        items = data.get("data") or []
        # SiliconFlow returns results with index; sort by index to be safe
        items = sorted(items, key=lambda x: x.get("index", 0))
        result = [self._fit(item.get("embedding") or []) for item in items]
        while len(result) < len(texts):
            result.append(zero_vector(self.dimensions))
        return result

    async def _request(self, payload_input) -> dict | None:
        """POST to /embeddings with retry; returns parsed JSON or None."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "input": payload_input,
            "dimensions": self.dimensions,
        }
        url = f"{self.base_url}/embeddings"

        last_error = ""
        for attempt in range(1 + len(_RETRY_DELAYS_SECONDS)):
            try:
                async with httpx.AsyncClient(trust_env=False) as client:
                    resp = await client.post(url, json=body, headers=headers, timeout=60.0)
                if resp.status_code == 200:
                    return resp.json()
                last_error = f"{resp.status_code} {resp.text[:200]}"
                # Retry only on 5xx
                if 500 <= resp.status_code < 600 and attempt < len(_RETRY_DELAYS_SECONDS):
                    await asyncio.sleep(_RETRY_DELAYS_SECONDS[attempt])
                    continue
                break
            except Exception as e:
                last_error = str(e)
                if attempt < len(_RETRY_DELAYS_SECONDS):
                    await asyncio.sleep(_RETRY_DELAYS_SECONDS[attempt])
                    continue
                break
        logger.warning("SiliconFlow embedding failed after retries: %s", last_error)
        return None

    def _fit(self, vec: list[float]) -> list[float]:
        if len(vec) > self.dimensions:
            return vec[:self.dimensions]
        if len(vec) < self.dimensions:
            return vec + [0.0] * (self.dimensions - len(vec))
        return vec
