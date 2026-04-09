import json
import re
from typing import Any


class ExtractionStage:
    def __init__(self, llm_client, model: str):
        self._client = llm_client
        self._model = model

    async def run(self, research_text: str, character_name: str) -> dict[str, Any]:
        from app.forge.prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_TEMPLATE

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3000,
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": EXTRACTION_USER_TEMPLATE.format(
                    character_name=character_name,
                    research_text=research_text,
                ),
            }],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text
                break

        return self._parse(text)

    def _parse(self, text: str) -> dict[str, Any]:
        match = re.search(r'\{[\s\S]+\}', text)
        if not match:
            return {"core_models": [], "heuristics": [], "discarded": []}

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return {"core_models": [], "heuristics": [], "discarded": []}

        core_models = []
        heuristics = []
        discarded = []

        for model in data.get("mental_models", []):
            verdict = model.get("verdict", "discard")
            if verdict == "core_model":
                core_models.append(model)
            elif verdict == "heuristic":
                heuristics.append(model)
            else:
                discarded.append(model)

        # Also include explicit heuristics from LLM
        for h in data.get("decision_heuristics", []):
            heuristics.append(h)

        return {
            "core_models": core_models,
            "heuristics": heuristics,
            "discarded": discarded,
        }
