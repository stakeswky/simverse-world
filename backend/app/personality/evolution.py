import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.llm.client import chat as llm_chat
from app.models.resident import Resident
from app.models.memory import Memory
from app.models.personality_history import PersonalityHistory
from app.personality.guard import PersonalityGuard
from app.personality.prompts import (
    DRIFT_EVAL_SYSTEM,
    DRIFT_EVAL_USER,
    SHIFT_EVAL_SYSTEM,
    SHIFT_EVAL_USER,
    TEXT_SYNC_SYSTEM,
    TEXT_SYNC_USER,
    TEXT_SYNC_SOUL_SYSTEM,
    TEXT_SYNC_SOUL_USER,
    format_dimensions,
    format_changes_summary,
)
from app.services.sbti_service import match_type

logger = logging.getLogger(__name__)

# Soul-relevant dimensions — only these trigger soul_md update on shift
_SOUL_DIMENSIONS = {"S3", "A3"}


class EvolutionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.guard = PersonalityGuard()

    async def evaluate_drift(self, resident: Resident) -> PersonalityHistory | None:
        """Check if drift is due and evaluate which dimensions should drift.

        Returns PersonalityHistory entry if drift occurred, else None.
        Non-blocking: exceptions are caught and logged.
        """
        try:
            # Guard check: enough memories since last drift?
            if not await self.guard.can_drift(resident.id, self.db):
                return None

            # Check monthly budget
            budget = await self.guard.check_monthly_budget(resident.id, self.db)
            if budget <= 0:
                logger.info("Drift skipped for %s: monthly budget exhausted", resident.id)
                return None

            sbti = (resident.meta_json or {}).get("sbti", {})
            dimensions = sbti.get("dimensions", {})
            sbti_type = sbti.get("type", "UNKNOWN")

            # Retrieve recent event memories
            stmt = (
                select(Memory)
                .where(Memory.resident_id == resident.id, Memory.type == "event")
                .order_by(Memory.created_at.desc())
                .limit(20)
            )
            result = await self.db.execute(stmt)
            recent_mems = result.scalars().all()

            if not recent_mems:
                return None

            mem_text = "\n".join(
                f"- [{m.importance:.1f}] {m.content}" for m in recent_mems
            )

            raw = await llm_chat(
                DRIFT_EVAL_SYSTEM,
                [{
                    "role": "user",
                    "content": DRIFT_EVAL_USER.format(
                        resident_name=resident.name,
                        sbti_type=sbti_type,
                        current_dimensions=format_dimensions(dimensions),
                        recent_memories=mem_text,
                    ),
                }],
                max_tokens=400,
            )
            data = json.loads(raw)
            changes_list = data.get("changes", [])

            if not changes_list:
                return None

            # Build changes dict
            proposed = {
                item["dim"]: {"from": item["from"], "to": item["to"]}
                for item in changes_list
                if item.get("dim") and item.get("from") and item.get("to")
            }

            # Guard validation (clamp, step check)
            validated = await self.guard.validate_drift(proposed, resident.id, self.db)
            if not validated:
                return None

            # Clamp by monthly budget
            if len(validated) > budget:
                keys = list(validated.keys())[:budget]
                validated = {k: validated[k] for k in keys}

            reason = "; ".join(
                item.get("evidence", "") for item in changes_list
                if item["dim"] in validated
            )

            return await self._apply_changes(
                resident=resident,
                changes=validated,
                trigger_type="drift",
                trigger_memory_id=None,
                reason=reason,
            )

        except Exception as e:
            logger.warning("Drift evaluation failed for %s: %s", resident.id, e)
            return None

    async def evaluate_shift(
        self, resident: Resident, trigger_memory: Memory
    ) -> PersonalityHistory | None:
        """Evaluate dramatic personality shift triggered by a high-importance event.

        Returns PersonalityHistory entry if shift occurred, else None.
        Non-blocking: exceptions are caught and logged.
        """
        try:
            if not await self.guard.can_shift(resident.id, self.db):
                logger.info("Shift skipped for %s: 24h cooldown active", resident.id)
                return None

            budget = await self.guard.check_monthly_budget(resident.id, self.db)
            if budget <= 0:
                logger.info("Shift skipped for %s: monthly budget exhausted", resident.id)
                return None

            sbti = (resident.meta_json or {}).get("sbti", {})
            dimensions = sbti.get("dimensions", {})
            sbti_type = sbti.get("type", "UNKNOWN")

            raw = await llm_chat(
                SHIFT_EVAL_SYSTEM,
                [{
                    "role": "user",
                    "content": SHIFT_EVAL_USER.format(
                        resident_name=resident.name,
                        sbti_type=sbti_type,
                        current_dimensions=format_dimensions(dimensions),
                        importance=trigger_memory.importance,
                        event_content=trigger_memory.content,
                    ),
                }],
                max_tokens=500,
            )
            data = json.loads(raw)
            changes_list = data.get("changes", [])
            shift_reason = data.get("shift_reason", "")

            if not changes_list or data.get("event_type") == "none":
                return None

            proposed = {
                item["dim"]: {"from": item["from"], "to": item["to"]}
                for item in changes_list
                if item.get("dim") and item.get("from") and item.get("to")
            }

            validated = await self.guard.validate_shift(proposed, resident.id, self.db)
            if not validated:
                return None

            if len(validated) > budget:
                keys = list(validated.keys())[:budget]
                validated = {k: validated[k] for k in keys}

            return await self._apply_changes(
                resident=resident,
                changes=validated,
                trigger_type="shift",
                trigger_memory_id=trigger_memory.id,
                reason=shift_reason,
            )

        except Exception as e:
            logger.warning("Shift evaluation failed for %s: %s", resident.id, e)
            return None

    async def _apply_changes(
        self,
        resident: Resident,
        changes: dict[str, dict],
        trigger_type: str,
        trigger_memory_id: str | None,
        reason: str,
    ) -> PersonalityHistory:
        """Apply validated dimension changes, re-match type, sync text, record history."""
        sbti = dict((resident.meta_json or {}).get("sbti", {}))
        dimensions = dict(sbti.get("dimensions", {}))
        old_type = sbti.get("type", "UNKNOWN")

        # Apply dimension changes
        for dim, change in changes.items():
            dimensions[dim] = change["to"]

        # Re-match SBTI type
        new_type_result = match_type(dimensions)
        new_type = new_type_result["type"]

        # Update resident SBTI in meta_json
        updated_sbti = dict(sbti)
        updated_sbti["dimensions"] = dimensions
        updated_sbti["type"] = new_type
        updated_sbti["type_name"] = new_type_result["type_name"]
        updated_sbti["similarity"] = new_type_result["similarity"]

        updated_meta = dict(resident.meta_json or {})
        updated_meta["sbti"] = updated_sbti
        resident.meta_json = updated_meta

        # Sync text layers
        await self._sync_text(resident, changes, reason, trigger_type)

        # Record history
        history = PersonalityHistory(
            resident_id=resident.id,
            trigger_type=trigger_type,
            trigger_memory_id=trigger_memory_id,
            changes_json=changes,
            old_type=old_type,
            new_type=new_type,
            reason=reason,
        )
        self.db.add(history)
        await self.db.commit()
        await self.db.refresh(resident)
        await self.db.refresh(history)

        if old_type != new_type:
            logger.info(
                "Type migration: %s → %s for resident %s",
                old_type, new_type, resident.id,
            )

        return history

    async def _sync_text(
        self,
        resident: Resident,
        changes: dict[str, dict],
        reason: str,
        trigger_type: str,
    ) -> None:
        """LLM-rewrite affected sections of persona_md (always) and soul_md (shift only).

        Failures are silently logged — text sync is best-effort.
        """
        changes_summary = format_changes_summary(changes)

        try:
            # Always sync persona_md
            new_persona = (await llm_chat(
                TEXT_SYNC_SYSTEM,
                [{
                    "role": "user",
                    "content": TEXT_SYNC_USER.format(
                        resident_name=resident.name,
                        trigger_type=trigger_type,
                        reason=reason,
                        changes_summary=changes_summary,
                        original_text=resident.persona_md or "",
                    ),
                }],
                max_tokens=800,
            )).strip()
            if new_persona:
                resident.persona_md = new_persona

        except Exception as e:
            logger.warning("persona_md sync failed for %s: %s", resident.id, e)

        # Only sync soul_md on shift AND if soul-relevant dimensions changed
        if trigger_type == "shift":
            soul_dims_changed = set(changes.keys()) & _SOUL_DIMENSIONS
            if soul_dims_changed:
                try:
                    new_soul = (await llm_chat(
                        TEXT_SYNC_SOUL_SYSTEM,
                        [{
                            "role": "user",
                            "content": TEXT_SYNC_SOUL_USER.format(
                                resident_name=resident.name,
                                reason=reason,
                                changes_summary=changes_summary,
                                original_text=resident.soul_md or "",
                            ),
                        }],
                        max_tokens=500,
                    )).strip()
                    if new_soul:
                        resident.soul_md = new_soul

                except Exception as e:
                    logger.warning("soul_md sync failed for %s: %s", resident.id, e)

