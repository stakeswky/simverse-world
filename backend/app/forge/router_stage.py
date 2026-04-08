import json
import re
from typing import Any


class InputRouter:
    def __init__(self, llm_client, model: str):
        self._client = llm_client
        self._model = model

    async def run(
        self, character_name: str, raw_text: str, user_material: str
    ) -> dict[str, Any]:
        from app.forge.prompts import ROUTER_SYSTEM_PROMPT, ROUTER_USER_TEMPLATE

        has_material = bool(user_material and user_material.strip())

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=200,
            system=ROUTER_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": ROUTER_USER_TEMPLATE.format(
                    character_name=character_name,
                    raw_text=raw_text or "(无描述)",
                    has_material="是" if has_material else "否",
                ),
            }],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text
                break

        mode = "quick"  # default fallback
        match = re.search(r'\{[^}]+\}', text)
        if match:
            try:
                data = json.loads(match.group())
                route = data.get("route", "quick")
                if route in ("deep", "quick"):
                    mode = route
            except json.JSONDecodeError:
                pass

        return {
            "mode": mode,
            "has_user_material": has_material,
            "character_name": character_name,
            "raw_text": raw_text,
            "user_material": user_material,
        }
