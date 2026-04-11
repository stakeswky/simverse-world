"""BasicPlanPlugin: generate daily goal + hourly plans via LLM."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from app.agent.actions import ActionType
from app.agent.scheduler import build_schedule
from app.agent.schemas import TickContext, DailyGoal, HourlyPlan
from app.config import settings
from app.llm.client import chat as llm_chat
from app.memory.service import MemoryService
from app.ws.manager import manager

logger = logging.getLogger(__name__)

PLAN_SYSTEM_PROMPT = """\
你是一个游戏 NPC 的日程规划器。根据居民的性格和记忆，生成今天的目标和分时段行动计划。

居民信息：
- 姓名：{name}
- 人格类型（SBTI）：{sbti_type}（{sbti_name}）
- 性格描述：{persona_snippet}

活跃时段：{wake_hour}:00 - {sleep_hour}:00，共 {slot_count} 个时段

可选行动：{action_types}

约束：
- importance 1-10，大部分为 2-4，最多 {max_high_importance} 个时段 >= 6
- 社交行动（CHAT_RESIDENT/GOSSIP）最多 {max_social_slots} 个时段
- 以第一人称自然表达目标，不要生硬的开头
{preferred_actions_hint}

输出严格 JSON，不要其他文字：
{{
  "goal": {{"goal": "今日目标描述", "motivation": "动机"}},
  "plans": [
    {{"slot": 0, "hour_range": [{start_0}, {end_0}], "action": "ACTION_TYPE", "target": null, "location": "地点", "importance": 3, "reason": "原因"}},
    ...
  ]
}}
"""

PLAN_USER_PROMPT = """\
昨天做了什么：
{yesterday_summary}

最近的重要记忆：
{recent_memories}

最近的关系：
{relationships}

请生成今天的目标和 {slot_count} 个时段的计划。
"""


class BasicPlanPlugin:
    def __init__(self, params: dict[str, Any] | None = None):
        params = params or {}
        self.plan_interval_hours: int = params.get("plan_interval_hours", 24)
        self.hourly_slots: int = params.get("hourly_slots", 7)
        self.max_social_slots: int = params.get("max_social_slots", 2)
        self.max_high_importance: int = params.get("max_high_importance", 2)
        self.preferred_actions: list[str] = params.get("preferred_actions", [])

    async def execute(self, ctx: TickContext) -> TickContext:
        today = datetime.now().strftime("%Y-%m-%d")

        plans_data = ctx.resident.daily_plans_json
        is_fresh = (
            plans_data
            and isinstance(plans_data, dict)
            and plans_data.get("generated_date") == today
        )

        if not is_fresh:
            try:
                await self._generate_plan(ctx, today)
            except Exception as e:
                logger.warning("Plan generation failed for %s: %s", ctx.resident.slug, e)
                return ctx

        # Load daily goal into context
        goal_data = ctx.resident.daily_goal_json
        if goal_data:
            ctx.daily_goal = DailyGoal(
                goal=goal_data.get("goal", ""),
                motivation=goal_data.get("motivation", ""),
                created_at=goal_data.get("created_at", ""),
                status=goal_data.get("status", "active"),
            )

        # Find current time slot
        plans_data = ctx.resident.daily_plans_json
        if plans_data and "plans" in plans_data:
            for p in plans_data["plans"]:
                hr = p.get("hour_range", [0, 0])
                if hr[0] <= ctx.hour < hr[1]:
                    ctx.current_plan = HourlyPlan(
                        slot=p["slot"],
                        hour_range=tuple(hr),
                        action=p["action"],
                        target=p.get("target"),
                        location=p.get("location"),
                        importance=p["importance"],
                        reason=p.get("reason", ""),
                        status=p.get("status", "pending"),
                    )
                    break

        return ctx

    async def _generate_plan(self, ctx: TickContext, today: str) -> None:
        resident = ctx.resident
        sbti = (resident.meta_json or {}).get("sbti", {})
        schedule = build_schedule(sbti)

        # Compute time slots
        awake_hours = schedule.sleep_hour - schedule.wake_hour
        slot_duration = max(1, awake_hours // self.hourly_slots)
        slots_info = []
        for i in range(self.hourly_slots):
            start = schedule.wake_hour + i * slot_duration
            end = min(start + slot_duration, schedule.sleep_hour)
            if start >= schedule.sleep_hour:
                break
            slots_info.append((i, start, end))

        # Fetch memories for context
        memory_svc = MemoryService(ctx.db)
        recent_all = await memory_svc.get_memories(resident.id, type="event", limit=20)
        # Filter to importance > 0.5, take top 5
        recent = [m for m in recent_all if m.importance > 0.5][:5]
        if not recent:
            recent = recent_all[:3]  # fallback: at least some context
        rels = await memory_svc.get_memories(resident.id, type="relationship", limit=3)

        recent_text = "\n".join(f"- {m.content}" for m in recent) or "（无）"
        rels_text = "\n".join(f"- {m.content}" for m in rels) or "（无）"

        # Yesterday's event summary
        yesterday = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))
        yesterday_events = [
            m for m in recent_all
            if m.created_at and m.created_at.date() < yesterday.date()
        ][:5]
        yesterday_text = "\n".join(f"- {m.content}" for m in yesterday_events) if yesterday_events else "（无）"

        action_types = ", ".join(a.value for a in ActionType)

        preferred_hint = ""
        if self.preferred_actions:
            preferred_hint = "- 偏好行为权重：" + ", ".join(self.preferred_actions)

        system_prompt = PLAN_SYSTEM_PROMPT.format(
            name=resident.name,
            sbti_type=sbti.get("type", "OJBK"),
            sbti_name=sbti.get("type_name", "无所谓人"),
            persona_snippet=(resident.persona_md or "")[:200],
            wake_hour=schedule.wake_hour,
            sleep_hour=schedule.sleep_hour,
            slot_count=len(slots_info),
            action_types=action_types,
            max_high_importance=self.max_high_importance,
            max_social_slots=self.max_social_slots,
            preferred_actions_hint=preferred_hint,
            start_0=slots_info[0][1] if slots_info else 7,
            end_0=slots_info[0][2] if slots_info else 9,
        )

        user_prompt = PLAN_USER_PROMPT.format(
            yesterday_summary=yesterday_text,
            recent_memories=recent_text,
            relationships=rels_text,
            slot_count=len(slots_info),
        )

        raw = await llm_chat(system_prompt, [{"role": "user", "content": user_prompt}], max_tokens=600)

        # Parse JSON response
        start_idx = raw.find('{')
        end_idx = raw.rfind('}') + 1
        if start_idx == -1 or end_idx <= start_idx:
            raise ValueError(f"No JSON in plan response: {raw[:200]}")

        data = json.loads(raw[start_idx:end_idx])

        # Store goal
        goal = data.get("goal", {})
        resident.daily_goal_json = {
            "goal": goal.get("goal", "无目标"),
            "motivation": goal.get("motivation", ""),
            "created_at": datetime.now().isoformat(),
            "status": "active",
        }

        # Store plans with status field
        plans = data.get("plans", [])
        for p in plans:
            p["status"] = "pending"

        resident.daily_plans_json = {
            "generated_date": today,
            "plans": plans,
        }

        await ctx.db.commit()
        logger.info("Generated daily plan for %s: %s (%d slots)",
                     resident.slug, goal.get("goal", "?"), len(plans))

        # Broadcast plan generation event
        try:
            top_plan = max(plans, key=lambda p: p.get("importance", 0)) if plans else None
            await manager.broadcast({
                "type": "resident_plan_generated",
                "resident_slug": resident.slug,
                "goal": goal.get("goal", ""),
                "plan_count": len(plans),
                "top_plan": {
                    "action": top_plan["action"],
                    "importance": top_plan["importance"],
                    "hour_range": top_plan.get("hour_range", []),
                } if top_plan else None,
            })
        except Exception as e:
            logger.debug("Plan broadcast failed (non-fatal): %s", e)
