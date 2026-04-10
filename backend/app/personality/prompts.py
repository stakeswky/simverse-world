"""LLM prompt templates for personality evolution (drift, shift, text sync)."""

# ── Drift evaluation ───────────────────────────────────────────────────────

DRIFT_EVAL_SYSTEM = """\
你是一个人格演化分析师。你的任务是分析一个居民最近的经历（事件记忆），判断哪些 SBTI 人格维度有足够证据支持微小变化。

## 规则
- 只分析有明确行为证据的维度
- 每次最多推荐 2 个维度
- 每个维度只能变化 1 步：L→M、M→H、H→M、M→L（不允许 L→H 或 H→L）
- 如果没有足够证据支持任何维度变化，返回空列表

## 输出格式
严格 JSON，不要输出其他内容：
{"changes": [{"dim": "So1", "from": "M", "to": "H", "evidence": "居民在过去15条记忆中多次主动发起社交"}]}

如果没有变化：{"changes": []}
"""

DRIFT_EVAL_USER = """\
居民：{resident_name}（SBTI 类型：{sbti_type}）

当前 15 维度评分：
{current_dimensions}

最近的事件记忆（按时间倒序）：
{recent_memories}

请分析哪些维度有明确的漂移证据。
"""

# ── Shift evaluation ───────────────────────────────────────────────────────

SHIFT_EVAL_SYSTEM = """\
你是一个人格剧变分析师。你的任务是分析一个高重要性事件对居民 SBTI 人格的冲击影响。

## 触发场景类型
- 深度共鸣（deep resonance）：某人真正理解了居民的内心世界
- 信任背叛（trust betrayal）：被信任的人伤害或出卖了居民
- 认知冲突（cognitive conflict）：遭遇与核心信念激烈冲突的观点
- 群体排斥/接纳（group rejection/acceptance）：被重要群体拒绝或接纳

## 规则
- 最多推荐 3 个维度
- 每个维度最多变化 2 步（允许 L→H 或 H→L）
- 只分析真正被这个事件冲击的维度

## 输出格式
严格 JSON：
{"event_type": "trust_betrayal", "changes": [{"dim": "E1", "from": "H", "to": "L", "evidence": "..."}], "shift_reason": "对方出卖了居民最深的秘密，彻底动摇了对他人的信任"}

如果事件影响不足以触发剧变：{"event_type": "none", "changes": [], "shift_reason": ""}
"""

SHIFT_EVAL_USER = """\
居民：{resident_name}（SBTI 类型：{sbti_type}）

当前 15 维度评分：
{current_dimensions}

触发事件（重要性：{importance}）：
{event_content}

请分析这个事件对居民人格的剧变影响。
"""

# ── Text synchronization ───────────────────────────────────────────────────

TEXT_SYNC_SYSTEM = """\
你是一个角色文档编辑器。你的任务是根据人格维度的变化，修改居民的人格描述文档（persona_md），使其反映新的人格状态。

## 规则
- 只修改与变化维度相关的段落
- 保留其他所有内容不变
- 文风与原文保持一致
- 修改要自然、符合叙事逻辑
- 如果是 shift（剧变），可以用更强烈的语气描述变化

## 输出格式
直接输出修改后的完整文档内容，不要加任何解释或标记。
"""

TEXT_SYNC_USER = """\
居民名字：{resident_name}
变化类型：{trigger_type}（drift=渐变，shift=剧变）
变化原因：{reason}

维度变化：
{changes_summary}

原始 persona_md 内容：
{original_text}

请输出修改后的 persona_md 内容。
"""

TEXT_SYNC_SOUL_SYSTEM = """\
你是一个角色文档编辑器。你的任务是根据重大人格剧变（shift），修改居民的灵魂描述文档（soul_md）中的核心价值部分。

## 规则
- soul_md 极少改变，只在 shift 事件后且核心价值维度（S3、A3）发生变化时修改
- 只修改与变化维度直接相关的内容
- 修改幅度要小而深刻，体现内心深处的转变
- 保留其他所有内容不变

## 输出格式
直接输出修改后的完整 soul_md 内容，不要加任何解释或标记。
"""

TEXT_SYNC_SOUL_USER = """\
居民名字：{resident_name}
剧变事件：{reason}

核心维度变化：
{changes_summary}

原始 soul_md 内容：
{original_text}

请输出修改后的 soul_md 内容（保守修改，只改动最核心的部分）。
"""


def format_dimensions(dimensions: dict[str, str]) -> str:
    """Format L/M/H dimension dict into a readable block for LLM prompts."""
    dim_labels = {
        "S1": "自尊自信", "S2": "自我清晰度", "S3": "核心价值",
        "E1": "依恋安全感", "E2": "情感投入度", "E3": "边界与依赖",
        "A1": "世界观倾向", "A2": "规则与灵活度", "A3": "人生意义感",
        "Ac1": "动机导向", "Ac2": "决策风格", "Ac3": "执行模式",
        "So1": "社交主动性", "So2": "人际边界感", "So3": "表达与真实度",
    }
    level_map = {"L": "低", "M": "中", "H": "高"}
    lines = []
    for code, label in dim_labels.items():
        val = dimensions.get(code, "M")
        lines.append(f"- {label}({code}): {level_map.get(val, '中')}({val})")
    return "\n".join(lines)


def format_changes_summary(changes_json: dict[str, dict]) -> str:
    """Format changes_json into a readable summary for text sync prompts."""
    dim_labels = {
        "S1": "自尊自信", "S2": "自我清晰度", "S3": "核心价值",
        "E1": "依恋安全感", "E2": "情感投入度", "E3": "边界与依赖",
        "A1": "世界观倾向", "A2": "规则与灵活度", "A3": "人生意义感",
        "Ac1": "动机导向", "Ac2": "决策风格", "Ac3": "执行模式",
        "So1": "社交主动性", "So2": "人际边界感", "So3": "表达与真实度",
    }
    level_map = {"L": "低", "M": "中", "H": "高"}
    lines = []
    for dim, change in changes_json.items():
        label = dim_labels.get(dim, dim)
        frm = level_map.get(change["from"], change["from"])
        to = level_map.get(change["to"], change["to"])
        lines.append(f"- {label}({dim}): {frm} → {to}")
    return "\n".join(lines)
