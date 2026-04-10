from typing import AsyncGenerator
import anthropic
from app.config import settings

_system_client: anthropic.AsyncAnthropic | None = None
_default_user_client: anthropic.AsyncAnthropic | None = None


def _reset_factory():
    """Reset all cached clients. Used in tests."""
    global _system_client, _default_user_client
    _system_client = None
    _default_user_client = None


class LLMClientFactory:
    """Not instantiated — just a namespace for documentation."""
    pass


def _make_anthropic_client(api_key: str, base_url: str | None = None) -> anthropic.AsyncAnthropic:
    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return anthropic.AsyncAnthropic(**kwargs)


def get_client(owner: str = "system", *, user_config: dict | None = None) -> anthropic.AsyncAnthropic:
    """
    Get an LLM client by owner type.

    owner: "system" or "user"
    user_config: optional dict with keys: api_key, base_url, api_format
                 If provided and owner="user", creates a client with user's credentials.
                 If not provided, falls back to system defaults.
    """
    global _system_client, _default_user_client

    if owner == "system":
        if _system_client is None:
            _system_client = _make_anthropic_client(
                api_key=settings.effective_api_key,
                base_url=settings.llm_base_url or None,
            )
        return _system_client

    if owner == "user":
        if user_config and user_config.get("api_key"):
            # User has custom config — create a fresh client (not cached)
            return _make_anthropic_client(
                api_key=user_config["api_key"],
                base_url=user_config.get("base_url") or settings.llm_base_url or None,
            )
        # No custom config — fall back to system defaults
        if _default_user_client is None:
            _default_user_client = _make_anthropic_client(
                api_key=settings.effective_api_key,
                base_url=settings.llm_base_url or None,
            )
        return _default_user_client

    raise ValueError("owner must be 'system' or 'user'")


async def stream_chat(
    system_prompt: str,
    messages: list[dict],
    model: str | None = None,
    *,
    owner: str = "user",
    user_config: dict | None = None,
) -> AsyncGenerator[str, None]:
    """Yield text chunks from LLM streaming response."""
    client = get_client(owner, user_config=user_config)
    kwargs: dict = {
        "model": model or settings.effective_model,
        "max_tokens": settings.llm_max_tokens,
        "system": system_prompt,
        "messages": messages,
    }
    if not settings.llm_thinking:
        kwargs["thinking"] = {"type": "disabled"}
    async with client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield text
