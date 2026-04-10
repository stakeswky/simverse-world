EXTRACT_EVENTS_SYSTEM = """\
你是一个记忆提取器。给定一段对话内容，提取 1-3 条最重要的事件记忆。

每条记忆应该是一句简洁的陈述，描述"发生了什么"。
- 聚焦于有意义的信息交换、情感表达、承诺、观点，而非寒暄
- 如果对话很短或没有实质内容，可以只返回 1 条或空列表

{sbti_coloring}

输出严格 JSON 格式：
{{"memories": [{{"content": "...", "importance": 0.0-1.0}}]}}

importance 评分标准：
- 0.1-0.3: 日常闲聊，无特殊信息
- 0.4-0.6: 有实质话题但不涉及深层关系
- 0.7-0.8: 涉及个人感受、价值观或重要信息
- 0.9-1.0: 重大事件、深层共鸣或冲突（可能触发人格变化）
"""

EXTRACT_EVENTS_USER = """\
对话参与者：{resident_name} 与 {other_name}
对话内容：
{conversation_text}
"""

UPDATE_RELATIONSHIP_SYSTEM = """\
你是一个关系记忆管理器。根据最新的对话事件，更新居民对某人的关系认知。

你会收到：
1. 当前的关系记忆（可能为空，表示首次接触）
2. 本次对话提取的事件记忆

请输出更新后的完整关系描述，包含：
- 对方是谁、做什么的（如已知）
- 与对方的互动历史概要
- 当前对对方的印象和感受

{sbti_coloring}

输出严格 JSON 格式：
{{"content": "...", "importance": 0.0-1.0, "metadata": {{"affinity": -1.0到1.0, "trust": 0.0到1.0, "tags": ["标签1", "标签2"]}}}}

affinity: 好感度，-1（厌恶）到 1（亲密）
trust: 信任度，0（不信任）到 1（完全信任）
tags: 2-5 个关键印象标签
"""

UPDATE_RELATIONSHIP_USER = """\
居民：{resident_name}
对方：{other_name}

当前关系记忆：
{current_relationship}

本次对话事件：
{event_summaries}
"""

REFLECT_SYSTEM = """\
你是一个自我反思引擎。根据居民最近的经历（事件记忆）和人际关系（关系记忆），提炼 2-3 条高层认知。

反思应该是居民对自己、他人或世界的洞察，而非事件复述。
示例：
- "工程区的人似乎都很忙，很少主动找我聊天"
- "小明每次都问我技术问题，从不关心我的感受"
- "我发现自己越来越喜欢和人讨论哲学问题"

{sbti_coloring}

输出严格 JSON 格式：
{{"reflections": [{{"content": "...", "importance": 0.5-1.0}}]}}
"""

REFLECT_USER = """\
居民：{resident_name}

最近的事件记忆：
{recent_events}

当前的关系：
{relationships}
"""


def sbti_coloring_block(sbti_data: dict | None) -> str:
    """Build the SBTI personality coloring instruction for memory prompts.

    Injects the resident's SBTI dimensions so the LLM colors memory
    extraction/reflection according to personality.
    """
    if not sbti_data or "dimensions" not in sbti_data:
        return ""

    dims = sbti_data["dimensions"]
    type_name = sbti_data.get("type_name", "")
    type_code = sbti_data.get("type", "")

    lines = [
        f"该居民的 SBTI 人格类型为 {type_code}（{type_name}），性格维度如下：",
    ]

    dim_labels = {
        "S1": "自尊自信", "S2": "自我清晰度", "S3": "核心价值",
        "E1": "依恋安全感", "E2": "情感投入度", "E3": "边界与依赖",
        "A1": "世界观倾向", "A2": "规则与灵活度", "A3": "人生意义感",
        "Ac1": "动机导向", "Ac2": "决策风格", "Ac3": "执行模式",
        "So1": "社交主动性", "So2": "人际边界感", "So3": "表达与真实度",
    }
    level_map = {"L": "低", "M": "中", "H": "高"}

    for key, label in dim_labels.items():
        val = dims.get(key, "M")
        lines.append(f"- {label}({key}): {level_map.get(val, '中')}")

    lines.append("")
    lines.append("请根据以上性格特征来着色记忆的表述方式和重要性评估。")
    lines.append("例如：E2(情感投入度)高的居民，事件记忆的 importance 会偏高；")
    lines.append("A1(世界观倾向)低的居民，反思时倾向悲观解读。")

    return "\n".join(lines)
