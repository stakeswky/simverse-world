from typing import Protocol


class EmbeddingProvider(Protocol):
    """Interface for an embedding backend.

    All implementations MUST return vectors of exactly `dimensions` length.
    Return None from embed() for empty/invalid input or on irrecoverable error.
    """

    name: str
    dimensions: int

    async def embed(self, text: str) -> list[float] | None: ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


def zero_vector(dim: int) -> list[float]:
    """Shared utility — used as failure-case filler in batch responses."""
    return [0.0] * dim
