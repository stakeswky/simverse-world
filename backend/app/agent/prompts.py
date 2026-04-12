"""LLM prompt templates for the agent decision loop and inter-resident chat."""
from app.agent.actions import ActionType

DECISION_SYSTEM = """\
你是一个游戏 NPC 居民的自主决策引擎。你的任务是根据居民当前的状态、周围环境和记忆，选择最符合角色人格的下一个行动。

居民信息：
- 姓名：{name}
- 当前位置：{current_location}
- 人格类型（SBTI）：{sbti_type}（{sbti_name}）
- 当前状态：{status}

输出严格 JSON 格式，不要输出其他内容：
{{
  "action": "<ACTION_TYPE>",
  "target_slug": "<居民slug或null>",
  "target_tile": [x, y] 或 null,
  "reason": "<一句话理由，15字以内>"
}}

可用的 action 类型：{available_actions}

规则：
- CHAT_RESIDENT 需要在 nearby_residents 中选一个空闲居民，填入 target_slug
- WANDER/VISIT_DISTRICT 填入 target_tile（使用地点入口坐标），其余为 null
- GO_HOME 不需要 target_tile（自动导航到你的家）
- GOSSIP 需要 target_slug，内容由后续流程生成
- 社交类型低（So1=L）的居民，倾向于选择 REFLECT/JOURNAL/OBSERVE
- 行动力高（Ac3=H）的居民，倾向于 WORK/STUDY/WANDER
- 当天已执行 {today_action_count} 个行动，上限 {max_daily_actions}
{location_boost_hint}
"""

DECISION_USER = """\
当前游戏世界时间：{world_time}（{schedule_phase}）

附近的居民：
{nearby_residents_text}

最近的记忆：
{recent_memories_text}

今天已做的事：
{today_actions_text}

请选择下一个行动。
"""


def build_decision_prompt(
    resident,
    schedule_phase: str,
    world_time: str,
    nearby_residents: list,
    memories: list,
    today_actions: list[str],
    available_actions: list[ActionType],
    max_daily_actions: int,
) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for the resident decision step."""
    from app.agent.map_data import get_location_at

    sbti = (resident.meta_json or {}).get("sbti", {})
    sbti_type = sbti.get("type", "OJBK")
    sbti_name = sbti.get("type_name", "无所谓人")

    # Resolve current location
    loc = get_location_at(resident.tile_x, resident.tile_y)
    if loc:
        current_location = f"{loc['name']}（{loc.get('description', '')}）"
        boosted = loc.get("boosted_actions", [])
        location_boost_hint = f"\n你在{loc['name']}里，这里特别适合：{', '.join(boosted)}" if boosted else ""
    else:
        current_location = f"户外 ({resident.tile_x}, {resident.tile_y})"
        location_boost_hint = ""

    nearby_text = "\n".join(
        f"- {r.name}（{r.slug}）：{r.status}，距离约 {_tile_dist(resident, r)} 格"
        for r in nearby_residents
    ) or "（附近没有其他居民）"

    memory_text = "\n".join(
        f"- [{m.source}] {m.content}" for m in memories[:8]
    ) or "（无相关记忆）"

    today_text = "\n".join(f"- {a}" for a in today_actions[-10:]) or "（今天还没有任何行动）"

    action_list = ", ".join(a.value for a in available_actions)

    system = DECISION_SYSTEM.format(
        name=resident.name,
        current_location=current_location,
        sbti_type=sbti_type,
        sbti_name=sbti_name,
        status=resident.status,
        available_actions=action_list,
        today_action_count=len(today_actions),
        max_daily_actions=max_daily_actions,
        location_boost_hint=location_boost_hint,
    )
    user = DECISION_USER.format(
        world_time=world_time,
        schedule_phase=schedule_phase,
        nearby_residents_text=nearby_text,
        recent_memories_text=memory_text,
        today_actions_text=today_text,
    )
    return system, user


def _tile_dist(a, b) -> int:
    return abs(a.tile_x - b.tile_x) + abs(a.tile_y - b.tile_y)


# ── Inter-Resident Chat Prompts ────────────────────────────────────────

CHAT_INITIATE_SYSTEM = """\
你是 {initiator_name}，一个 Simverse World 的居民（SBTI：{sbti_type} {sbti_name}）。
你主动走向 {target_name} 并开始对话。

你的人格：
{persona_md}

你对 {target_name} 的记忆：
{relationship_memory}

请用中文，以符合你人格的方式开场白。保持简短（30字以内）。
"""

CHAT_REPLY_SYSTEM = """\
你是 {responder_name}，一个 Simverse World 的居民（SBTI：{sbti_type} {sbti_name}）。
{initiator_name} 正在和你对话。

你的人格：
{persona_md}

你对 {initiator_name} 的记忆：
{relationship_memory}

对话历史：
{history}

请用中文，以符合你人格的方式回应。保持简短（50字以内）。
"""

CHAT_SUMMARY_SYSTEM = """\
请将以下居民间的对话总结成 1-2 句话，供玩家看到时理解发生了什么。
用第三人称描述，例如"小明和小红讨论了..."。
不要透露完整对话内容，只概括核心事件和情感变化。

输出格式：
{{"summary": "...", "mood": "positive/neutral/negative"}}
"""

CHAT_SUMMARY_USER = """\
{initiator_name} 和 {target_name} 的对话：

{dialog_text}
"""
