"""BasicDecidePlugin: decide next action, plan-aware with hybrid execution."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.agent.actions import ActionType, ActionResult, get_available_actions
from app.agent.prompts import build_decision_prompt
from app.agent.schemas import TickContext, parse_action_result
from app.config import settings
from app.llm.client import chat as llm_chat
from app.memory.service import MemoryService

logger = logging.getLogger(__name__)


class BasicDecidePlugin:
    def __init__(self, params: dict[str, Any] | None = None):
        params = params or {}
        self.interrupt_threshold: int = params.get("interrupt_threshold", 6)
        self.plan_adherence_hint: bool = params.get("plan_adherence_hint", True)

    async def execute(self, ctx: TickContext) -> TickContext:
        ctx.available_actions = get_available_actions(ctx.resident, ctx.nearby_residents)
        await self._load_memories(ctx)

        plan = ctx.current_plan

        # Case 1: High-importance plan -> force execute
        if plan and plan.importance >= self.interrupt_threshold:
            result = self._force_execute_plan(plan, ctx)
            if result:
                ctx.action_result = result
                ctx.plan_followed = True
                plan.status = "executing"
                return ctx

        # Case 2 & 3: Low-importance plan or no plan -> call LLM
        try:
            action_result = await self._llm_decide(ctx)
        except Exception as e:
            logger.warning("Decide LLM failed for %s: %s", ctx.resident.slug, e)
            ctx.skip_remaining = True
            return ctx

        if action_result is None:
            ctx.skip_remaining = True
            return ctx

        if action_result.action not in ctx.available_actions:
            logger.debug("Resident %s chose unavailable action %s", ctx.resident.slug, action_result.action)
            ctx.skip_remaining = True
            return ctx

        ctx.action_result = action_result

        if plan:
            try:
                planned_action = ActionType(plan.action)
                if action_result.action == planned_action:
                    ctx.plan_followed = True
                    plan.status = "executing"
                else:
                    ctx.plan_followed = False
                    plan.status = "interrupted"
            except ValueError:
                ctx.plan_followed = False

        return ctx

    def _force_execute_plan(self, plan, ctx: TickContext) -> ActionResult | None:
        try:
            action = ActionType(plan.action)
        except ValueError:
            logger.warning("Invalid action in plan: %s", plan.action)
            return None
        if action not in ctx.available_actions:
            return None
        return ActionResult(
            action=action,
            target_slug=plan.target,
            target_tile=None,
            reason=plan.reason[:100],
        )

    async def _llm_decide(self, ctx: TickContext) -> ActionResult | None:
        today_key = datetime.now().strftime("%Y-%m-%d")
        today_actions = [
            m.content for m in ctx.memories
            if m.created_at and m.created_at.strftime("%Y-%m-%d") == today_key
        ]
        ctx.today_actions = today_actions

        system_prompt, user_prompt = build_decision_prompt(
            resident=ctx.resident,
            schedule_phase=ctx.schedule_phase,
            world_time=ctx.world_time,
            nearby_residents=ctx.nearby_residents,
            memories=ctx.memories,
            today_actions=today_actions,
            available_actions=ctx.available_actions,
            max_daily_actions=settings.agent_max_daily_actions,
        )

        if ctx.current_plan and self.plan_adherence_hint:
            plan = ctx.current_plan
            hint = f"\n\n你原本计划在这个时段 {plan.action}（{plan.reason}），但你可以根据当前情况改变主意。"
            user_prompt += hint

        raw = await llm_chat(system_prompt, [{"role": "user", "content": user_prompt}], max_tokens=200)
        return parse_action_result(raw)

    async def _load_memories(self, ctx: TickContext) -> None:
        try:
            memory_svc = MemoryService(ctx.db)
            ctx.memories = await memory_svc.get_memories(ctx.resident.id, type="event", limit=10)
        except Exception as e:
            logger.warning("Memory retrieval failed for %s: %s", ctx.resident.slug, e)
            ctx.memories = []
