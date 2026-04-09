import json
import re
from typing import Any


class ValidationStage:
    def __init__(self, llm_client, model: str):
        self._client = llm_client
        self._model = model

    async def run(
        self,
        character_name: str,
        ability_md: str,
        persona_md: str,
        soul_md: str,
    ) -> dict[str, Any]:
        from app.forge.prompts import VALIDATION_SYSTEM_PROMPT, VALIDATION_USER_TEMPLATE

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=VALIDATION_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": VALIDATION_USER_TEMPLATE.format(
                    character_name=character_name,
                    ability_md=ability_md,
                    persona_md=persona_md,
                    soul_md=soul_md,
                ),
            }],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text
                break

        match = re.search(r'\{[\s\S]+\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return {
            "known_answers": [],
            "edge_case": {},
            "style_check": {},
            "overall_score": 0.0,
            "suggestions": ["Validation parsing failed"],
        }
