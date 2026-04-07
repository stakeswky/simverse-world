from typing import AsyncGenerator
import anthropic
from app.config import settings

_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        kwargs: dict = {"api_key": settings.effective_api_key}
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        _client = anthropic.AsyncAnthropic(**kwargs)
    return _client


async def stream_chat(
    system_prompt: str,
    messages: list[dict],
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    """Yield text chunks from LLM streaming response."""
    client = get_client()
    async with client.messages.stream(
        model=model or settings.effective_model,
        max_tokens=settings.llm_max_tokens,
        system=system_prompt,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text
