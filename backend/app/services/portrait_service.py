"""AI portrait generation via Gemini image model (Vertex AI proxy)."""
import base64
import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PORTRAIT_DIR = Path("static/portraits")


def build_portrait_prompt(name: str, persona_md: str) -> str:
    """Build image generation prompt from character name and persona description."""
    # Extract appearance hints from persona
    appearance_hints = ""
    if persona_md:
        lines = persona_md.split("\n")
        for line in lines:
            lower = line.lower()
            if any(kw in lower for kw in ["外貌", "appearance", "穿", "wear", "发", "hair", "眼", "eye"]):
                appearance_hints += line.strip() + " "
        appearance_hints = appearance_hints[:300]  # cap length

    if not appearance_hints:
        appearance_hints = "a cyberpunk city character with distinct personality"

    return (
        f"Generate a Q-style chibi pixel-art portrait of a character named '{name}'. "
        f"Character traits: {appearance_hints}. "
        f"Style: 2D pixel art, cyberpunk aesthetic, 128x128 pixels, "
        f"transparent background, game sprite portrait, cute chibi proportions. "
        f"Output a single character portrait, no text, no watermark."
    )


def save_portrait_image(resident_id: str, image_bytes: bytes) -> str:
    """Save portrait image to disk and return URL path."""
    PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{resident_id}.png"
    filepath = PORTRAIT_DIR / filename
    filepath.write_bytes(image_bytes)
    return f"/static/portraits/{filename}"


async def generate_portrait(
    resident_id: str,
    name: str,
    persona_md: str,
) -> str | None:
    """Generate AI portrait via Gemini. Returns URL path or None on failure."""
    prompt = build_portrait_prompt(name, persona_md)

    base_url = settings.portrait_llm_base_url or "http://100.93.72.102:3000/v1"
    api_key = settings.portrait_llm_api_key or "sk-placeholder"
    model = settings.portrait_llm_model or "gemini-3-pro-image-preview"
    timeout = settings.portrait_llm_timeout or 60

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 1,
                    "response_format": {"type": "image_url"},
                },
            )

            if response.status_code != 200:
                logger.error(
                    "Gemini API returned %d: %s",
                    response.status_code,
                    response.text[:200],
                )
                return None

            data = response.json()

            # Parse Gemini image response
            # The proxy may return in OpenAI-compatible format or Gemini native format
            image_data = None

            # Try Gemini native format (candidates -> inlineData)
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                for part in parts:
                    inline = part.get("inlineData", {})
                    if inline.get("data"):
                        image_data = base64.b64decode(inline["data"])
                        break

            # Try OpenAI chat completion format
            if not image_data:
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    # Content might be base64 encoded image
                    if content and not content.startswith("{"):
                        try:
                            image_data = base64.b64decode(content)
                        except Exception:
                            pass

            if not image_data:
                logger.error(
                    "Could not extract image from Gemini response: %s",
                    str(data)[:300],
                )
                return None

            return save_portrait_image(resident_id, image_data)

    except Exception as e:
        logger.error("Portrait generation failed for %s: %s", resident_id, e)
        return None
