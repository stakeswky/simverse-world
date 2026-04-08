#!/usr/bin/env python3
"""
最小 MVP: SearXNG 自动调研 + LLM 炼化
测试人物: 萧炎（《斗破苍穹》主角）
"""

import asyncio
import json
import time
import httpx
from anthropic import AsyncAnthropic

# ─── 配置 ───────────────────────────────────────────
SEARXNG_URL = "http://100.93.72.102:58080/search"
LLM_API_KEY = "sk-sp-2f8527503ce241b28914942ebf6bd0b2"
LLM_BASE_URL = "https://coding.dashscope.aliyuncs.com/apps/anthropic"
LLM_MODEL = "MiniMax-M2.5"

# ─── 6 路调研维度 ──────────────────────────────────────
RESEARCH_DIMENSIONS = {
    "abilities": {
        "queries": [
            "萧炎 斗技 功法 异火",
            "斗破苍穹 萧炎 实力 等级 进阶",
        ],
        "instruction": "提取萧炎的核心能力：斗技、功法、异火、炼药术等战斗和专业能力。",
    },
    "personality": {
        "queries": [
            "萧炎 性格特点 为人处世",
            "斗破苍穹 萧炎 语录 经典台词",
        ],
        "instruction": "提取萧炎的性格特点、说话风格、行为模式、人际关系处理方式。",
    },
    "decisions": {
        "queries": [
            "萧炎 关键决策 转折点",
            "斗破苍穹 萧炎 重要选择 剧情",
        ],
        "instruction": "提取萧炎人生中的关键决策和转折点，分析其决策逻辑。",
    },
    "values": {
        "queries": [
            "萧炎 价值观 信念 精神",
            "斗破苍穹 萧炎 三十年河东三十年河西",
        ],
        "instruction": "提取萧炎的核心价值观、人生信条、精神内核。",
    },
    "relationships": {
        "queries": [
            "萧炎 薰儿 药老 萧家",
            "斗破苍穹 萧炎 师徒 兄弟 感情",
        ],
        "instruction": "提取萧炎的重要人际关系：师徒、爱情、友情、家族。",
    },
    "timeline": {
        "queries": [
            "斗破苍穹 萧炎 成长历程 剧情线",
            "萧炎 从废柴到斗帝 经历",
        ],
        "instruction": "提取萧炎的成长时间线：从乌坦城到成为斗帝的关键阶段。",
    },
}


async def search(client: httpx.AsyncClient, query: str) -> list[dict]:
    """调用 SearXNG 搜索"""
    try:
        resp = await client.get(
            SEARXNG_URL,
            params={"q": query, "format": "json", "language": "zh"},
            timeout=30,
        )
        data = resp.json()
        results = []
        for r in data.get("results", [])[:5]:
            results.append({
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "url": r.get("url", ""),
            })
        return results
    except Exception as e:
        print(f"  ⚠ 搜索失败 [{query}]: {e}")
        return []


async def research_dimension(
    client: httpx.AsyncClient, dim_name: str, dim_config: dict
) -> dict:
    """对单个维度执行多查询搜索"""
    print(f"  🔍 调研维度: {dim_name}")
    all_results = []
    for query in dim_config["queries"]:
        results = await search(client, query)
        all_results.extend(results)
        print(f"     [{query}] → {len(results)} 条结果")
    return {
        "dimension": dim_name,
        "instruction": dim_config["instruction"],
        "results": all_results,
    }


async def run_research(character: str) -> dict[str, dict]:
    """6 路并行调研"""
    print(f"\n{'='*60}")
    print(f"Phase 1: 6 路并行调研 — {character}")
    print(f"{'='*60}")
    start = time.time()

    async with httpx.AsyncClient(trust_env=False) as client:
        # 串行执行避免并发压垮 SearXNG
        results = []
        for name, config in RESEARCH_DIMENSIONS.items():
            r = await research_dimension(client, name, config)
            results.append(r)
            await asyncio.sleep(1)  # 间隔 1 秒避免限流

    research = {r["dimension"]: r for r in results}
    elapsed = time.time() - start
    total = sum(len(r["results"]) for r in results)
    print(f"\n✅ 调研完成: {total} 条结果, 耗时 {elapsed:.1f}s")
    return research


def format_research_for_llm(research: dict) -> str:
    """将调研结果格式化为 LLM 可消费的文本"""
    parts = []
    for dim_name, dim_data in research.items():
        parts.append(f"## {dim_name} — {dim_data['instruction']}")
        for r in dim_data["results"]:
            if r["content"]:
                parts.append(f"- [{r['title']}]({r['url']})")
                parts.append(f"  {r['content']}")
        parts.append("")
    return "\n".join(parts)


async def forge_character(research: dict, character: str) -> dict:
    """用 LLM 基于调研结果生成三层人设"""
    print(f"\n{'='*60}")
    print(f"Phase 2: LLM 炼化 — 生成三层人设")
    print(f"{'='*60}")

    research_text = format_research_for_llm(research)
    print(f"  📝 调研素材: {len(research_text)} 字符")

    http_client = httpx.AsyncClient(trust_env=False)
    client = AsyncAnthropic(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, http_client=http_client)

    system_prompt = """你是一个角色炼化专家。基于提供的调研资料，为指定人物生成结构化的三层人设文档。

输出格式要求（严格使用 Markdown）：

# Ability Layer（能力层）
## 核心心智模型
列出 3-5 个该人物的核心思维模型，每个包含：名称、一句话描述、跨场景证据
## 决策启发式
列出 5-8 条 "if X then Y" 的决策规则，附具体案例
## 专业技能
该人物的核心能力清单

# Persona Layer（人格层）
## 身份卡
50字第一人称自我介绍
## 表达DNA
说话风格、口头禅、语气特征、句式偏好
## Layer 0: 核心性格
不可改变的底层性格特征
## Layer 1: 身份认同
如何定义自己
## Layer 2: 表达风格
具体的语言模式和习惯
## Layer 3: 决策与判断
面对选择时的行为模式
## Layer 4: 人际行为
与他人互动的模式

# Soul Layer（灵魂层）
## Layer 0: 核心价值观
最底层的信念，不可动摇
## Layer 1: 人生经历与背景
关键经历如何塑造了这个人
## Layer 2: 兴趣与审美
偏好和品味
## Layer 3: 情感模式
情感表达和依恋风格
## Layer 4: 适应性与成长
面对困境时的应对方式

# Meta
## 诚实边界
该角色扮演的局限性说明
## 调研来源摘要
关键信息来源

要求：
- 基于调研资料生成，不要臆造资料中没有的信息
- 保持人物的原始特色和魅力
- 心智模型和决策启发式要具体，不要泛泛而谈
- 表达DNA要能让人一读就感受到是这个人在说话"""

    user_prompt = f"""请为以下人物生成三层人设：

**人物**: {character}（《斗破苍穹》主角）

**调研资料**:
{research_text}

请基于以上资料，生成完整的三层人设文档。"""

    print("  🔮 调用 LLM 生成中...")
    start = time.time()

    response = await client.messages.create(
        model=LLM_MODEL,
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    elapsed = time.time() - start
    # 过滤 ThinkingBlock，取 TextBlock
    output = ""
    for block in response.content:
        if hasattr(block, "text"):
            output += block.text
    print(f"  ✅ 生成完成: {len(output)} 字符, 耗时 {elapsed:.1f}s")
    print(f"  📊 Token 用量: input={response.usage.input_tokens}, output={response.usage.output_tokens}")

    return {
        "character": character,
        "output": output,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }


async def main():
    character = "萧炎"
    print(f"🔥 Skills-World 炼化 MVP 测试")
    print(f"   人物: {character}（《斗破苍穹》）")
    print(f"   搜索引擎: SearXNG @ 100.93.72.102:58080")
    print(f"   LLM: {LLM_MODEL} @ DashScope")

    # Phase 1: 6路调研
    research = await run_research(character)

    # 保存调研原始数据
    with open("forge_research_萧炎.json", "w", encoding="utf-8") as f:
        json.dump(research, f, ensure_ascii=False, indent=2)
    print(f"  💾 调研数据已保存: forge_research_萧炎.json")

    # Phase 2: LLM 炼化
    result = await forge_character(research, character)

    # 保存炼化结果
    output_path = "forge_output_萧炎.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result["output"])
    print(f"\n{'='*60}")
    print(f"🎉 炼化完成！结果已保存: {output_path}")
    print(f"{'='*60}")

    # 打印结果预览
    preview = result["output"][:2000]
    print(f"\n--- 结果预览 (前2000字符) ---\n")
    print(preview)
    if len(result["output"]) > 2000:
        print(f"\n... (共 {len(result['output'])} 字符, 截断显示)")


if __name__ == "__main__":
    asyncio.run(main())
