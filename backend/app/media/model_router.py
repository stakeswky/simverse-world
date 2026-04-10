"""Model router for multimodal chat: routes image/video to appropriate vision models.

- Images  → main model (settings.effective_model) with Anthropic image content blocks.
- Videos  → kimi-k2.5 first (for summary), then main model with summary injected into text.
- No media → falls through to regular streaming, same as stream_chat().
"""
import copy
import logging
from typing import AsyncGenerator

from app.config import settings
from app.llm.client import get_client

logger = logging.getLogger(__name__)


class ModelRouter:
    """Routes chat messages to the appropriate model based on media type."""

    async def chat_with_media(
        self,
        system_prompt: str,
        messages: list[dict],
        media_url: str | None,
        media_type: str | None,
        *,
        owner: str = "user",
        user_config: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a response, injecting media context as appropriate.

        For images: the last user message is augmented with an image content block.
        For videos: kimi-k2.5 summarizes the video first; the summary is injected
                    as additional text in the last user message, then the main model streams.
        For no media: plain streaming, identical to stream_chat().

        Yields text chunks.
        """
        augmented_messages = copy.deepcopy(messages)

        if media_type == "image" and media_url:
            augmented_messages = self._inject_image(augmented_messages, media_url)
            async for chunk in self._stream(system_prompt, augmented_messages, owner=owner, user_config=user_config):
                yield chunk

        elif media_type == "video" and media_url:
            video_summary = await self._understand_video(media_url)
            augmented_messages = self._inject_video_summary(augmented_messages, media_url, video_summary)
            async for chunk in self._stream(system_prompt, augmented_messages, owner=owner, user_config=user_config):
                yield chunk

        else:
            # No media — plain text stream (same path as stream_chat)
            async for chunk in self._stream(system_prompt, messages, owner=owner, user_config=user_config):
                yield chunk

    def _inject_image(self, messages: list[dict], image_url: str) -> list[dict]:
        """Augment the last user message with an image content block.

        Converts the last user message content from a plain string to a list of
        content blocks: [text block, image block]. This matches the Anthropic
        messages API multimodal format.
        """
        if not messages:
            return messages

        last_msg = messages[-1]
        if last_msg.get("role") != "user":
            return messages

        original_text = last_msg.get("content", "")
        if isinstance(original_text, str):
            text_block = {"type": "text", "text": original_text}
        else:
            # Already a list — wrap as-is; append image after
            messages[-1]["content"] = list(original_text) + [
                {
                    "type": "image",
                    "source": {"type": "url", "url": image_url},
                }
            ]
            return messages

        messages[-1]["content"] = [
            text_block,
            {
                "type": "image",
                "source": {"type": "url", "url": image_url},
            },
        ]
        return messages

    def _inject_video_summary(
        self,
        messages: list[dict],
        video_url: str,
        summary: str,
    ) -> list[dict]:
        """Append video summary as text to the last user message.

        Since videos cannot be sent directly as content blocks to the main model,
        we inject the summary from kimi-k2.5 as additional context text.
        """
        if not messages:
            return messages

        last_msg = messages[-1]
        if last_msg.get("role") != "user":
            return messages

        original_text = last_msg.get("content", "")
        if isinstance(original_text, str):
            injected = (
                f"{original_text}\n\n"
                f"[视频内容摘要 by AI: {summary}]"
            )
            messages[-1]["content"] = injected
        return messages

    async def _understand_video(self, video_url: str) -> str:
        """Call kimi-k2.5 to understand the video and return a text summary.

        Uses the same DashScope Anthropic-compatible endpoint as the main model,
        but switches to kimi-k2.5 for video understanding capability.
        """
        client = get_client("system")
        try:
            resp = await client.messages.create(
                model=settings.video_llm_model,
                max_tokens=512,
                system="你是一个视频理解助手。请用中文简洁描述视频的主要内容，不超过200字。",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"请描述这个视频的内容：{video_url}",
                            }
                        ],
                    }
                ],
            )
            return resp.content[0].text
        except Exception as exc:
            logger.warning("Video understanding failed for %s: %s", video_url, exc)
            return f"（视频理解失败，原始链接：{video_url}）"

    async def _stream(
        self,
        system_prompt: str,
        messages: list[dict],
        *,
        owner: str = "user",
        user_config: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream text from the main model. Internal helper."""
        client = get_client(owner, user_config=user_config)
        kwargs: dict = {
            "model": settings.effective_model,
            "max_tokens": settings.llm_max_tokens,
            "system": system_prompt,
            "messages": messages,
        }
        if not settings.llm_thinking:
            kwargs["thinking"] = {"type": "disabled"}
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
