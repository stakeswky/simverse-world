import json
import re
from typing import Any


class RefinementStage:
    def __init__(self, llm_client, model: str):
        self._client = llm_client
        self._model = model

    async def run(
        self,
        character_name: str,
        ability_md: str,
        persona_md: str,
        soul_md: str,
        validation_report: dict[str, Any],
    ) -> dict[str, Any]:
        from app.forge.prompts import (
            REFINE_OPTIMIZER_SYSTEM, REFINE_CREATOR_SYSTEM,
            REFINE_APPLY_SYSTEM, REFINE_APPLY_USER,
        )

        combined = f"=== Ability ===\n{ability_md}\n\n=== Persona ===\n{persona_md}\n\n=== Soul ===\n{soul_md}"
        validation_str = json.dumps(validation_report, ensure_ascii=False)

        # Agent 1: Optimizer
        opt_resp = await self._client.messages.create(
            model=self._model, max_tokens=1000,
            system=REFINE_OPTIMIZER_SYSTEM,
            messages=[{"role": "user", "content": f"人物：{character_name}\n验证报告：{validation_str}\n\n{combined}"}],
        )
        opt_log = self._extract_json(opt_resp)

        # Agent 2: Creator perspective
        creator_resp = await self._client.messages.create(
            model=self._model, max_tokens=1000,
            system=REFINE_CREATOR_SYSTEM,
            messages=[{"role": "user", "content": f"人物：{character_name}\n\n{combined}"}],
        )
        creator_log = self._extract_json(creator_resp)

        # Merge suggestions
        all_suggestions = (
            opt_log.get("suggestions", []) + creator_log.get("suggestions", [])
        )
        suggestions_str = "\n".join(f"- {s}" for s in all_suggestions)

        # Apply refinement to each layer
        refined_ability = await self._refine_layer(
            REFINE_APPLY_SYSTEM, REFINE_APPLY_USER,
            character_name, suggestions_str, ability_md,
        )
        refined_persona = await self._refine_layer(
            REFINE_APPLY_SYSTEM, REFINE_APPLY_USER,
            character_name, suggestions_str, persona_md,
        )
        refined_soul = await self._refine_layer(
            REFINE_APPLY_SYSTEM, REFINE_APPLY_USER,
            character_name, suggestions_str, soul_md,
        )

        return {
            "ability_md": refined_ability,
            "persona_md": refined_persona,
            "soul_md": refined_soul,
            "refinement_log": [
                {"agent": "optimizer", **opt_log},
                {"agent": "creator", **creator_log},
            ],
        }

    async def _refine_layer(
        self, system: str, user_template: str,
        character_name: str, suggestions: str, layer_md: str,
    ) -> str:
        response = await self._client.messages.create(
            model=self._model, max_tokens=2500,
            system=system,
            messages=[{"role": "user", "content": user_template.format(
                character_name=character_name,
                suggestions=suggestions,
                layer_md=layer_md,
            )}],
        )
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return layer_md  # fallback to original

    def _extract_json(self, response) -> dict:
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
        return {"suggestions": [], "priority": "low"}
