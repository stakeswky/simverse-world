import asyncio
from typing import Any
import httpx

RESEARCH_DIMENSIONS: dict[str, dict[str, Any]] = {
    "writings": {
        "queries_template": ["{name} 著作 文章 论文", "{name} 核心观点 思想"],
        "instruction": "提取核心观点和思想。",
    },
    "conversations": {
        "queries_template": ["{name} 访谈 播客 演讲", "{name} 语录 对话 采访"],
        "instruction": "提取原话和语境。",
    },
    "expression_dna": {
        "queries_template": ["{name} 说话风格 口头禅", "{name} 社交媒体 短内容 语录"],
        "instruction": "提取说话风格和用词习惯。",
    },
    "external_views": {
        "queries_template": ["{name} 评价 传记 他人看法", "{name} 争议 批评 赞誉"],
        "instruction": "提取外部视角和评价。",
    },
    "decisions": {
        "queries_template": ["{name} 关键决策 转折点", "{name} 重要选择 人生抉择"],
        "instruction": "提取关键决策和决策逻辑。",
    },
    "timeline": {
        "queries_template": ["{name} 成长历程 人生经历", "{name} 时间线 里程碑 生平"],
        "instruction": "提取成长时间线和关键阶段。",
    },
}


class ResearchStage:
    def __init__(self, searxng_url: str, query_delay: float = 1.0, top_n: int = 5):
        self._url = searxng_url
        self._delay = query_delay
        self._top_n = top_n

    async def _search(self, client: httpx.AsyncClient, query: str) -> list[dict]:
        try:
            resp = await client.get(
                self._url,
                params={"q": query, "format": "json", "language": "zh"},
                timeout=30,
            )
            data = resp.json()
            return [
                {"title": r.get("title", ""), "content": r.get("content", ""), "url": r.get("url", "")}
                for r in data.get("results", [])[:self._top_n]
            ]
        except Exception:
            return []

    async def run(self, character_name: str, user_material: str = "") -> dict[str, list[dict]]:
        results: dict[str, list[dict]] = {}

        async with httpx.AsyncClient(trust_env=False) as client:
            for dim_name, dim_config in RESEARCH_DIMENSIONS.items():
                dim_results: list[dict] = []
                for template in dim_config["queries_template"]:
                    query = template.format(name=character_name)
                    search_results = await self._search(client, query)
                    dim_results.extend(search_results)
                    if self._delay > 0:
                        await asyncio.sleep(self._delay)
                results[dim_name] = dim_results

        return results

    def format_for_llm(self, research: dict[str, list[dict]], user_material: str = "") -> str:
        parts: list[str] = []

        if user_material and user_material.strip():
            parts.append("## 用户提供的素材（一级来源，权重最高）")
            parts.append(user_material.strip())
            parts.append("")

        for dim_name, dim_results in research.items():
            instruction = RESEARCH_DIMENSIONS[dim_name]["instruction"]
            parts.append(f"## {dim_name} — {instruction}")
            for r in dim_results:
                if r["content"]:
                    parts.append(f"- [{r['title']}]({r['url']})")
                    parts.append(f"  {r['content']}")
            parts.append("")

        return "\n".join(parts)
