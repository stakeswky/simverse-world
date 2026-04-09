import json
from typing import Any


class BuildStage:
    def __init__(self, llm_client, model: str, max_tokens: int = 2000):
        self._client = llm_client
        self._model = model
        self._max_tokens = max_tokens

    async def run(
        self,
        character_name: str,
        research_text: str,
        extraction_data: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        from app.forge.prompts import (
            BUILD_ABILITY_SYSTEM, BUILD_ABILITY_USER,
            BUILD_PERSONA_SYSTEM, BUILD_PERSONA_USER,
            BUILD_SOUL_SYSTEM, BUILD_SOUL_USER,
        )

        extraction_str = json.dumps(extraction_data or {}, ensure_ascii=False, indent=2)

        ability_md = await self._call(
            BUILD_ABILITY_SYSTEM,
            BUILD_ABILITY_USER.format(
                character_name=character_name,
                research_text=research_text,
                extraction_data=extraction_str,
            ),
        )

        persona_md = await self._call(
            BUILD_PERSONA_SYSTEM,
            BUILD_PERSONA_USER.format(
                character_name=character_name,
                research_text=research_text,
            ),
        )

        soul_md = await self._call(
            BUILD_SOUL_SYSTEM,
            BUILD_SOUL_USER.format(
                character_name=character_name,
                research_text=research_text,
            ),
        )

        return {
            "ability_md": ability_md,
            "persona_md": persona_md,
            "soul_md": soul_md,
        }

    async def _call(self, system: str, user_msg: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""
