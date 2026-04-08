# Plan 2: Forge Pipeline — 双轨炼化管线（快速 + 深度蒸馏）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有的 5 步引导式炼化升级为管线架构，支持快速炼化（保留现有逻辑）和深度蒸馏（SearXNG 6 路调研 + 三重验证 + 质量验证 + 双 Agent 精炼），并导入 14 个预设虚拟人物。

**Architecture:** 将 `forge_service.py` 的单一函数重构为管线式 Stage 架构：`InputRouter → ResearchStage → ExtractionStage → BuildStage → ValidationStage → RefinementStage`。每个 Stage 是独立模块，通过 `ForgeSession` 数据库模型传递状态。快速炼化跳过 Research/Extraction/Validation/Refinement，直接走 BuildStage。使用 Plan 1 建立的 `ForgeSession` 模型持久化中间产物。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), httpx (SearXNG), Anthropic SDK, pytest

**Working directory:** `/Users/jimmy/Downloads/Skills-World/.worktrees/mvp-implementation/backend/`

**Depends on:** Plan 1 (Foundation) — ForgeSession model, LLM client factory, Settings extension

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/forge/` | Create dir | 新的 forge 管线模块（替代 services/forge_service.py 中的管线逻辑） |
| `app/forge/__init__.py` | Create | Package init |
| `app/forge/router_stage.py` | Create | InputRouter：智能路由（快速 vs 深度），LLM 分类调用 |
| `app/forge/research_stage.py` | Create | ResearchStage：SearXNG 6 路调研 |
| `app/forge/extraction_stage.py` | Create | ExtractionStage：三重验证提取心智模型 |
| `app/forge/build_stage.py` | Create | BuildStage：三层人设构建（复用现有 prompts + 扩展格式） |
| `app/forge/validation_stage.py` | Create | ValidationStage：三问验证 + 边缘测试 + 风格检测 |
| `app/forge/refinement_stage.py` | Create | RefinementStage：双 Agent 精炼 |
| `app/forge/pipeline.py` | Create | 管线编排器：串联 Stage，管理 ForgeSession 状态 |
| `app/forge/prompts.py` | Create | 深度蒸馏专用 prompt 模板（路由、提取、验证、精炼） |
| `app/routers/forge.py` | Modify | 新增 /forge/deep-start, /forge/deep-status, /forge/deep-confirm, /forge/import-skill |
| `app/llm/forge_prompts.py` | Modify | 扩展现有 prompts 适配新三层格式 |
| `seed/preset_characters.py` | Create | 14 个预设人物数据 + 导入脚本 |
| `tests/test_forge_pipeline.py` | Create | 管线各 Stage 测试 |
| `tests/test_research_stage.py` | Create | SearXNG 调研测试（mock HTTP） |
| `tests/test_preset_import.py` | Create | 预设人物导入测试 |

---

## Task 1: InputRouter — 智能路由

**Files:**
- Create: `app/forge/router_stage.py`
- Create: `app/forge/__init__.py`
- Create: `app/forge/prompts.py`
- Test: `tests/test_forge_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_forge_pipeline.py
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.anyio
async def test_input_router_public_figure():
    """Public figure name should route to 'deep' mode."""
    from app.forge.router_stage import InputRouter

    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text='{"route": "deep", "reason": "public figure"}')]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    router = InputRouter(llm_client=mock_client, model="test-model")
    result = await router.run(character_name="乔布斯", raw_text="", user_material="")

    assert result["mode"] == "deep"


@pytest.mark.anyio
async def test_input_router_fictional_character():
    """Fictional character description should route to 'quick' mode."""
    from app.forge.router_stage import InputRouter

    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text='{"route": "quick", "reason": "fictional"}')]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    router = InputRouter(llm_client=mock_client, model="test-model")
    result = await router.run(character_name="赛博朋克黑客", raw_text="一个虚构角色", user_material="")

    assert result["mode"] == "quick"


@pytest.mark.anyio
async def test_input_router_with_material_and_public_name():
    """Public figure + user material should route to 'deep' with material flag."""
    from app.forge.router_stage import InputRouter

    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text='{"route": "deep", "reason": "known person with material"}')]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    router = InputRouter(llm_client=mock_client, model="test-model")
    result = await router.run(
        character_name="萧炎",
        raw_text="",
        user_material="斗破苍穹主角，从废柴到斗帝..."
    )

    assert result["mode"] == "deep"
    assert result["has_user_material"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_forge_pipeline.py::test_input_router_public_figure -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.forge'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/forge/__init__.py
# Forge pipeline package

# app/forge/prompts.py
ROUTER_SYSTEM_PROMPT = """\
你是一个路由分类器。判断用户要炼化的人物是否为"可以在网上搜索到足够资料的知名人物/角色"。

知名人物/角色包括：
- 公众人物（企业家、政治家、科学家、艺术家等）
- 知名虚构角色（小说、动漫、游戏中的主要角色）
- 历史人物

不包括：
- 用户的朋友、同事等私人人物
- 用户自己描述的原创虚构角色
- 模糊的角色描述（如"一个厉害的黑客"）

只输出一个 JSON 对象：
{"route": "deep" 或 "quick", "reason": "一句话理由"}
"""

ROUTER_USER_TEMPLATE = """\
人物名：{character_name}
用户描述：{raw_text}
是否附带素材：{has_material}
"""
```

```python
# app/forge/router_stage.py
import json
import re
from typing import Any


class InputRouter:
    def __init__(self, llm_client, model: str):
        self._client = llm_client
        self._model = model

    async def run(
        self, character_name: str, raw_text: str, user_material: str
    ) -> dict[str, Any]:
        from app.forge.prompts import ROUTER_SYSTEM_PROMPT, ROUTER_USER_TEMPLATE

        has_material = bool(user_material and user_material.strip())

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=200,
            system=ROUTER_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": ROUTER_USER_TEMPLATE.format(
                    character_name=character_name,
                    raw_text=raw_text or "(无描述)",
                    has_material="是" if has_material else "否",
                ),
            }],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text
                break

        mode = "quick"  # default fallback
        match = re.search(r'\{[^}]+\}', text)
        if match:
            try:
                data = json.loads(match.group())
                route = data.get("route", "quick")
                if route in ("deep", "quick"):
                    mode = route
            except json.JSONDecodeError:
                pass

        return {
            "mode": mode,
            "has_user_material": has_material,
            "character_name": character_name,
            "raw_text": raw_text,
            "user_material": user_material,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_forge_pipeline.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/forge/ tests/test_forge_pipeline.py
git commit -m "feat: InputRouter stage for forge pipeline smart routing"
```

---

## Task 2: ResearchStage — SearXNG 6 路调研

**Files:**
- Create: `app/forge/research_stage.py`
- Test: `tests/test_research_stage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_research_stage.py
import pytest
from unittest.mock import AsyncMock, patch
import httpx


@pytest.mark.anyio
async def test_research_stage_returns_6_dimensions():
    """Research stage should return results for all 6 dimensions."""
    from app.forge.research_stage import ResearchStage

    # Mock httpx response
    mock_response = httpx.Response(
        200,
        json={
            "results": [
                {"title": "Test Result", "content": "Some content about 萧炎", "url": "https://example.com"},
                {"title": "Another Result", "content": "More content", "url": "https://example2.com"},
            ]
        },
        request=httpx.Request("GET", "http://test"),
    )

    with patch("app.forge.research_stage.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        stage = ResearchStage(searxng_url="http://test:58080/search")
        result = await stage.run(character_name="萧炎", user_material="")

    assert "writings" in result
    assert "conversations" in result
    assert "expression_dna" in result
    assert "external_views" in result
    assert "decisions" in result
    assert "timeline" in result
    # Each dimension should have a list of results
    for dim in result.values():
        assert isinstance(dim, list)


@pytest.mark.anyio
async def test_research_stage_with_user_material():
    """When user material is provided, it should be included as primary source."""
    from app.forge.research_stage import ResearchStage

    mock_response = httpx.Response(
        200,
        json={"results": []},
        request=httpx.Request("GET", "http://test"),
    )

    with patch("app.forge.research_stage.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        stage = ResearchStage(searxng_url="http://test:58080/search")
        result = await stage.run(
            character_name="萧炎",
            user_material="斗破苍穹主角，从废柴到斗帝的成长历程"
        )

    # User material should appear in the formatted output
    formatted = stage.format_for_llm(result, user_material="斗破苍穹主角...")
    assert "用户提供的素材" in formatted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_research_stage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.forge.research_stage'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/forge/research_stage.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_research_stage.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/forge/research_stage.py tests/test_research_stage.py
git commit -m "feat: ResearchStage with SearXNG 6-dimension research"
```

---

## Task 3: ExtractionStage — 三重验证提取

**Files:**
- Create: `app/forge/extraction_stage.py`
- Modify: `app/forge/prompts.py`
- Test: `tests/test_forge_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_forge_pipeline.py
@pytest.mark.anyio
async def test_extraction_stage_parses_mental_models():
    """Extraction stage should parse mental models from LLM response."""
    from app.forge.extraction_stage import ExtractionStage

    llm_response_text = """{
        "mental_models": [
            {"name": "投资回报型思维", "description": "风险可控时ALL IN", "cross_domain": true, "generative": true, "exclusive": true, "verdict": "core_model"},
            {"name": "复盘型学习", "description": "每次战败都拆解吸收", "cross_domain": true, "generative": true, "exclusive": false, "verdict": "heuristic"},
            {"name": "坚持不懈", "description": "不放弃", "cross_domain": false, "generative": false, "exclusive": false, "verdict": "discard"}
        ],
        "decision_heuristics": [
            {"rule": "if 风险可控 then ALL IN", "example": "吞噬异火"}
        ]
    }"""

    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text=llm_response_text)]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    stage = ExtractionStage(llm_client=mock_client, model="test-model")
    result = await stage.run(research_text="调研数据...", character_name="萧炎")

    assert len(result["core_models"]) == 1
    assert result["core_models"][0]["name"] == "投资回报型思维"
    assert len(result["heuristics"]) >= 1
    assert len(result["discarded"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_forge_pipeline.py::test_extraction_stage_parses_mental_models -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Add to `app/forge/prompts.py`:

```python
EXTRACTION_SYSTEM_PROMPT = """\
你是一个认知框架提取专家。从调研资料中提取人物的心智模型和决策启发式。

对每个候选心智模型，执行三重验证：
1. **跨域复现** (cross_domain): 是否在 2 个以上不同领域/场景中出现？
2. **生成力** (generative): 能否预测该人物对新问题的立场？
3. **排他性** (exclusive): 是否为该人物独特的，而非"所有人都会这么想"？

通过 3 项 → verdict: "core_model"
通过 1-2 项 → verdict: "heuristic"
通过 0 项 → verdict: "discard"

输出 JSON:
{
    "mental_models": [
        {"name": "模型名", "description": "一句话描述", "cross_domain": true/false, "generative": true/false, "exclusive": true/false, "verdict": "core_model/heuristic/discard"}
    ],
    "decision_heuristics": [
        {"rule": "if X then Y", "example": "具体案例"}
    ]
}
"""

EXTRACTION_USER_TEMPLATE = """\
人物：{character_name}

调研资料：
{research_text}

请提取该人物的心智模型（3-7 个候选）和决策启发式（5-10 条），对每个心智模型执行三重验证。
"""
```

```python
# app/forge/extraction_stage.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_forge_pipeline.py::test_extraction_stage_parses_mental_models -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/forge/extraction_stage.py app/forge/prompts.py tests/test_forge_pipeline.py
git commit -m "feat: ExtractionStage with triple-verification mental model extraction"
```

---

## Task 4: BuildStage — 扩展三层构建

**Files:**
- Create: `app/forge/build_stage.py`
- Modify: `app/forge/prompts.py`
- Test: `tests/test_forge_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_forge_pipeline.py
@pytest.mark.anyio
async def test_build_stage_generates_three_layers():
    """Build stage should produce ability_md, persona_md, soul_md."""
    from app.forge.build_stage import BuildStage

    mock_client = AsyncMock()

    # Each call returns a different layer
    responses = [
        AsyncMock(content=[AsyncMock(text="# Ability Layer\n## 核心心智模型\n...")]),
        AsyncMock(content=[AsyncMock(text="# Persona Layer\n## 身份卡\n...")]),
        AsyncMock(content=[AsyncMock(text="# Soul Layer\n## Layer 0: 核心价值观\n...")]),
    ]
    mock_client.messages.create = AsyncMock(side_effect=responses)

    stage = BuildStage(llm_client=mock_client, model="test-model")
    result = await stage.run(
        character_name="萧炎",
        research_text="调研数据...",
        extraction_data={"core_models": [], "heuristics": []},
    )

    assert "ability_md" in result
    assert "persona_md" in result
    assert "soul_md" in result
    assert "Ability" in result["ability_md"]
    assert "Persona" in result["persona_md"]
    assert "Soul" in result["soul_md"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_forge_pipeline.py::test_build_stage_generates_three_layers -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Add to `app/forge/prompts.py`:

```python
BUILD_ABILITY_SYSTEM = """\
你是角色炼化专家。基于调研资料和提取的心智模型，生成 Ability Layer（能力层）文档。

输出格式（Markdown）：

# Ability Layer

## 核心心智模型
列出 3-5 个经验证的思维模型，每个包含：
- **模型名**：一句话描述
  - 跨域证据：在哪些不同场景中体现
  - 应用方式：如何使用
  - 局限性：什么时候不适用

## 决策启发式
列出 5-8 条 "if X then Y" 规则，每条附具体案例

## 专业技能
核心能力清单，每项用一句话描述具体水平

规则：基于调研资料生成，不臆造。心智模型要具体，不要泛泛而谈。
"""

BUILD_ABILITY_USER = """\
人物：{character_name}

调研资料：
{research_text}

已提取的心智模型：
{extraction_data}

请生成 Ability Layer 文档。
"""

BUILD_PERSONA_SYSTEM = """\
你是角色炼化专家。基于调研资料，生成 Persona Layer（人格层）文档。

输出格式（Markdown）：

# Persona Layer

## 身份卡
50 字第一人称自我介绍

## 表达 DNA
说话风格、口头禅、句式偏好、幽默类型、确定性水平

## Layer 0: 核心性格（不可变）
2-3 条底层性格特征，用 **特征名**：行为表现 格式

## Layer 1: 身份认同
如何定义自己

## Layer 2: 表达风格
具体语言模式、用词习惯

## Layer 3: 决策与判断
面对选择时的行为模式

## Layer 4: 人际行为
与他人互动的模式

规则：每层要有具体可执行的行为规则，表达 DNA 要让人一读就感受到是这个人在说话。
"""

BUILD_PERSONA_USER = """\
人物：{character_name}

调研资料：
{research_text}

请生成 Persona Layer 文档。
"""

BUILD_SOUL_SYSTEM = """\
你是角色炼化专家。基于调研资料，生成 Soul Layer（灵魂层）文档。

输出格式（Markdown）：

# Soul Layer

## Layer 0: 核心价值观（不可变）
2-4 条最底层信念

## Layer 1: 人生经历与背景
关键经历 + 时间线，如何塑造了这个人

## Layer 2: 兴趣与审美
偏好、品味、文化取向

## Layer 3: 情感模式
情感表达风格、依恋类型

## Layer 4: 适应性与成长
面对困境的应对方式

## 智识谱系（可选）
谁影响了 TA，TA 影响了谁

规则：灵魂层要有深度和温度，不要编造资料中没有的具体事件。
"""

BUILD_SOUL_USER = """\
人物：{character_name}

调研资料：
{research_text}

请生成 Soul Layer 文档。
"""
```

```python
# app/forge/build_stage.py
import json
from typing import Any


class BuildStage:
    def __init__(self, llm_client, model: str, max_tokens: int = 2000):
        self._client = llm_client
        self._model = model
        self._max_tokens = max_tokens

    async def run(
        self,
        character_name: str,
        research_text: str,
        extraction_data: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        from app.forge.prompts import (
            BUILD_ABILITY_SYSTEM, BUILD_ABILITY_USER,
            BUILD_PERSONA_SYSTEM, BUILD_PERSONA_USER,
            BUILD_SOUL_SYSTEM, BUILD_SOUL_USER,
        )

        extraction_str = json.dumps(extraction_data or {}, ensure_ascii=False, indent=2)

        ability_md = await self._call(
            BUILD_ABILITY_SYSTEM,
            BUILD_ABILITY_USER.format(
                character_name=character_name,
                research_text=research_text,
                extraction_data=extraction_str,
            ),
        )

        persona_md = await self._call(
            BUILD_PERSONA_SYSTEM,
            BUILD_PERSONA_USER.format(
                character_name=character_name,
                research_text=research_text,
            ),
        )

        soul_md = await self._call(
            BUILD_SOUL_SYSTEM,
            BUILD_SOUL_USER.format(
                character_name=character_name,
                research_text=research_text,
            ),
        )

        return {
            "ability_md": ability_md,
            "persona_md": persona_md,
            "soul_md": soul_md,
        }

    async def _call(self, system: str, user_msg: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_forge_pipeline.py::test_build_stage_generates_three_layers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/forge/build_stage.py app/forge/prompts.py tests/test_forge_pipeline.py
git commit -m "feat: BuildStage with extended 3-layer format generation"
```

---

## Task 5: ValidationStage — 三问验证 + 风格检测

**Files:**
- Create: `app/forge/validation_stage.py`
- Modify: `app/forge/prompts.py`
- Test: `tests/test_forge_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_forge_pipeline.py
@pytest.mark.anyio
async def test_validation_stage_returns_report():
    """Validation stage should return a structured report."""
    from app.forge.validation_stage import ValidationStage

    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text="""{
        "known_answers": [
            {"question": "萧炎的师父是谁？", "expected": "药老", "actual": "药老/药尘", "pass": true},
            {"question": "萧炎最强的斗技？", "expected": "佛怒火莲", "actual": "佛怒火莲", "pass": true},
            {"question": "萧炎的功法？", "expected": "焚诀", "actual": "焚诀", "pass": true}
        ],
        "edge_case": {"question": "萧炎对AI的看法？", "showed_uncertainty": true, "pass": true},
        "style_check": {"sample": "三十年河东...", "matches_voice": true, "pass": true},
        "overall_score": 0.9,
        "suggestions": ["可以加强对萧炎幽默感的描写"]
    }""")]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    stage = ValidationStage(llm_client=mock_client, model="test-model")
    report = await stage.run(
        character_name="萧炎",
        ability_md="# Ability...",
        persona_md="# Persona...",
        soul_md="# Soul...",
    )

    assert "known_answers" in report
    assert "edge_case" in report
    assert "style_check" in report
    assert "overall_score" in report
    assert report["overall_score"] >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_forge_pipeline.py::test_validation_stage_returns_report -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

Add to `app/forge/prompts.py`:

```python
VALIDATION_SYSTEM_PROMPT = """\
你是角色质量验证专家。对一个角色的三层人设进行质量检验。

执行以下 4 项检验：

1. **三问验证**：提出 3 个该人物有已知答案的问题，验证人设能否正确回答
2. **边缘测试**：提出 1 个该人物从未公开讨论的问题，验证人设是否表现出适度不确定
3. **风格检测**：用该人设的表达 DNA 写一段 100 字的话，验证是否符合该人物的说话风格
4. **总体评分**：0-1 分

输出 JSON：
{
    "known_answers": [{"question": "...", "expected": "...", "actual": "...", "pass": true/false}],
    "edge_case": {"question": "...", "showed_uncertainty": true/false, "pass": true/false},
    "style_check": {"sample": "100字风格样本", "matches_voice": true/false, "pass": true/false},
    "overall_score": 0.0-1.0,
    "suggestions": ["改进建议1", "改进建议2"]
}
"""

VALIDATION_USER_TEMPLATE = """\
人物：{character_name}

=== Ability Layer ===
{ability_md}

=== Persona Layer ===
{persona_md}

=== Soul Layer ===
{soul_md}

请对以上三层人设执行质量验证。
"""
```

```python
# app/forge/validation_stage.py
import json
import re
from typing import Any


class ValidationStage:
    def __init__(self, llm_client, model: str):
        self._client = llm_client
        self._model = model

    async def run(
        self,
        character_name: str,
        ability_md: str,
        persona_md: str,
        soul_md: str,
    ) -> dict[str, Any]:
        from app.forge.prompts import VALIDATION_SYSTEM_PROMPT, VALIDATION_USER_TEMPLATE

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=VALIDATION_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": VALIDATION_USER_TEMPLATE.format(
                    character_name=character_name,
                    ability_md=ability_md,
                    persona_md=persona_md,
                    soul_md=soul_md,
                ),
            }],
        )

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

        return {
            "known_answers": [],
            "edge_case": {},
            "style_check": {},
            "overall_score": 0.0,
            "suggestions": ["Validation parsing failed"],
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_forge_pipeline.py::test_validation_stage_returns_report -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/forge/validation_stage.py app/forge/prompts.py tests/test_forge_pipeline.py
git commit -m "feat: ValidationStage with 3-question + edge + style checks"
```

---

## Task 6: RefinementStage — 双 Agent 精炼

**Files:**
- Create: `app/forge/refinement_stage.py`
- Modify: `app/forge/prompts.py`
- Test: `tests/test_forge_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_forge_pipeline.py
@pytest.mark.anyio
async def test_refinement_stage_improves_layers():
    """Refinement stage should return improved layers and a log."""
    from app.forge.refinement_stage import RefinementStage

    mock_client = AsyncMock()
    # Agent 1 (optimizer) response
    optimizer_resp = AsyncMock(content=[AsyncMock(text="""{
        "suggestions": ["加强表达DNA的口头禅部分", "补充决策启发式案例"],
        "priority": "medium"
    }""")])
    # Agent 2 (creator perspective) response
    creator_resp = AsyncMock(content=[AsyncMock(text="""{
        "suggestions": ["身份卡的自我介绍不够有特色"],
        "priority": "low"
    }""")])
    # Final refinement response
    refined_resp = AsyncMock(content=[AsyncMock(text="# Ability Layer (refined)\n...")])

    mock_client.messages.create = AsyncMock(
        side_effect=[optimizer_resp, creator_resp, refined_resp, refined_resp, refined_resp]
    )

    stage = RefinementStage(llm_client=mock_client, model="test-model")
    result = await stage.run(
        character_name="萧炎",
        ability_md="# Ability...",
        persona_md="# Persona...",
        soul_md="# Soul...",
        validation_report={"suggestions": ["改进表达DNA"]},
    )

    assert "ability_md" in result
    assert "persona_md" in result
    assert "soul_md" in result
    assert "refinement_log" in result
    assert len(result["refinement_log"]) >= 2  # optimizer + creator logs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_forge_pipeline.py::test_refinement_stage_improves_layers -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

Add to `app/forge/prompts.py`:

```python
REFINE_OPTIMIZER_SYSTEM = """\
你是角色人设优化专家。审阅一个角色的三层人设和质量验证报告，提出改进建议。

关注点：
- 心智模型是否足够具体和有证据支撑
- 表达 DNA 是否有辨识度
- 各层之间是否一致
- 验证报告中指出的问题

输出 JSON：
{"suggestions": ["具体改进建议1", "..."], "priority": "high/medium/low"}
"""

REFINE_CREATOR_SYSTEM = """\
你是角色创造者视角的审阅者。从"这个角色是否有趣、有深度、值得对话"的角度审阅三层人设。

关注点：
- 这个角色是否有独特的魅力
- 对话时是否会有意思
- 是否有意想不到的深度
- 诚实边界是否到位

输出 JSON：
{"suggestions": ["具体改进建议1", "..."], "priority": "high/medium/low"}
"""

REFINE_APPLY_SYSTEM = """\
你是角色人设精炼师。根据两位审阅者的建议，改进以下角色人设层。

只输出改进后的完整 Markdown 文档，不要输出其他内容。
保持原有结构和格式，只在需要改进的地方做修改。
"""

REFINE_APPLY_USER = """\
人物：{character_name}

审阅者建议：
{suggestions}

原始文档：
{layer_md}

请输出改进后的完整文档。
"""
```

```python
# app/forge/refinement_stage.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_forge_pipeline.py::test_refinement_stage_improves_layers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/forge/refinement_stage.py app/forge/prompts.py tests/test_forge_pipeline.py
git commit -m "feat: RefinementStage with dual-agent review and refinement"
```

---

## Task 7: Pipeline 编排器 — 串联所有 Stage

**Files:**
- Create: `app/forge/pipeline.py`
- Test: `tests/test_forge_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_forge_pipeline.py
@pytest.mark.anyio
async def test_pipeline_quick_mode_skips_research(db_session):
    """Quick mode should skip research/extraction/validation/refinement."""
    from app.forge.pipeline import ForgePipeline
    from app.models.forge_session import ForgeSession
    from app.models.user import User

    user = User(name="test", email="pipe@test.com")
    db_session.add(user)
    await db_session.commit()

    mock_client = AsyncMock()
    # Router returns quick
    mock_client.messages.create = AsyncMock(return_value=AsyncMock(
        content=[AsyncMock(text='{"route": "quick", "reason": "fictional"}')]
    ))

    pipeline = ForgePipeline(db=db_session, system_client=mock_client, user_client=mock_client, model="test")

    # Override build stage to avoid real LLM call
    from app.forge.build_stage import BuildStage
    original_run = BuildStage.run
    async def mock_build_run(self, **kwargs):
        return {"ability_md": "# Ability", "persona_md": "# Persona", "soul_md": "# Soul"}
    BuildStage.run = mock_build_run

    try:
        session = await pipeline.start(user_id=user.id, character_name="赛博黑客", raw_text="虚构角色")
        assert session.mode == "quick"

        # Run to completion
        await pipeline.run_to_completion(session.id)
        await db_session.refresh(session)
        assert session.status == "done"
        assert session.build_output != {}
        # Research should be empty (skipped)
        assert session.research_data == {}
    finally:
        BuildStage.run = original_run
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_forge_pipeline.py::test_pipeline_quick_mode_skips_research -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# app/forge/pipeline.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.forge_session import ForgeSession
from app.forge.router_stage import InputRouter
from app.forge.research_stage import ResearchStage
from app.forge.extraction_stage import ExtractionStage
from app.forge.build_stage import BuildStage
from app.forge.validation_stage import ValidationStage
from app.forge.refinement_stage import RefinementStage
from app.config import settings


class ForgePipeline:
    def __init__(
        self,
        db: AsyncSession,
        system_client,
        user_client,
        model: str | None = None,
        searxng_url: str | None = None,
    ):
        self._db = db
        self._system_client = system_client
        self._user_client = user_client
        self._model = model or settings.effective_model
        self._searxng_url = searxng_url or "http://100.93.72.102:58080/search"

    async def start(
        self,
        user_id: str,
        character_name: str,
        raw_text: str = "",
        user_material: str = "",
    ) -> ForgeSession:
        """Start a new forge session. Routes to quick or deep mode."""
        router = InputRouter(llm_client=self._system_client, model=self._model)
        route_result = await router.run(character_name, raw_text, user_material)

        session = ForgeSession(
            user_id=user_id,
            character_name=character_name,
            mode=route_result["mode"],
            status="routing",
            current_stage="router",
            research_data={},
            extraction_data={},
            build_output={},
            validation_report={},
            refinement_log={},
        )
        # Store raw inputs in research_data for later use
        session.research_data = {
            "raw_text": raw_text,
            "user_material": user_material,
            "route_result": route_result,
        }
        session.status = "routed"

        self._db.add(session)
        await self._db.commit()
        await self._db.refresh(session)
        return session

    async def run_to_completion(self, session_id: str) -> ForgeSession:
        """Run the pipeline to completion based on session mode."""
        result = await self._db.execute(
            select(ForgeSession).where(ForgeSession.id == session_id)
        )
        session = result.scalar_one()

        try:
            if session.mode == "deep":
                await self._run_deep(session)
            else:
                await self._run_quick(session)

            session.status = "done"
        except Exception as e:
            session.status = "error"
            session.refinement_log = {
                **session.refinement_log,
                "error": str(e),
            }

        await self._db.commit()
        return session

    async def _run_quick(self, session: ForgeSession):
        """Quick mode: BuildStage only."""
        session.status = "building"
        session.current_stage = "build"
        await self._db.commit()

        raw_text = session.research_data.get("raw_text", "")
        user_material = session.research_data.get("user_material", "")
        input_text = user_material or raw_text or session.character_name

        build = BuildStage(llm_client=self._user_client, model=self._model)
        build_result = await build.run(
            character_name=session.character_name,
            research_text=input_text,
        )
        session.build_output = build_result

    async def _run_deep(self, session: ForgeSession):
        """Deep mode: Research → Extract → Build → Validate → Refine."""
        user_material = session.research_data.get("user_material", "")

        # Stage 1: Research
        session.status = "researching"
        session.current_stage = "research"
        await self._db.commit()

        research = ResearchStage(searxng_url=self._searxng_url)
        research_results = await research.run(session.character_name, user_material)
        research_text = research.format_for_llm(research_results, user_material)
        session.research_data = {
            **session.research_data,
            "search_results": {k: len(v) for k, v in research_results.items()},
            "research_text_length": len(research_text),
        }
        await self._db.commit()

        # Stage 2: Extraction
        session.status = "extracting"
        session.current_stage = "extraction"
        await self._db.commit()

        extraction = ExtractionStage(llm_client=self._user_client, model=self._model)
        extraction_result = await extraction.run(research_text, session.character_name)
        session.extraction_data = extraction_result
        await self._db.commit()

        # Stage 3: Build
        session.status = "building"
        session.current_stage = "build"
        await self._db.commit()

        build = BuildStage(llm_client=self._user_client, model=self._model)
        build_result = await build.run(
            character_name=session.character_name,
            research_text=research_text,
            extraction_data=extraction_result,
        )
        session.build_output = build_result
        await self._db.commit()

        # Stage 4: Validation
        session.status = "validating"
        session.current_stage = "validation"
        await self._db.commit()

        validation = ValidationStage(llm_client=self._user_client, model=self._model)
        validation_report = await validation.run(
            character_name=session.character_name,
            ability_md=build_result["ability_md"],
            persona_md=build_result["persona_md"],
            soul_md=build_result["soul_md"],
        )
        session.validation_report = validation_report
        await self._db.commit()

        # Stage 5: Refinement
        session.status = "refining"
        session.current_stage = "refinement"
        await self._db.commit()

        refinement = RefinementStage(llm_client=self._user_client, model=self._model)
        refined = await refinement.run(
            character_name=session.character_name,
            ability_md=build_result["ability_md"],
            persona_md=build_result["persona_md"],
            soul_md=build_result["soul_md"],
            validation_report=validation_report,
        )
        session.build_output = {
            "ability_md": refined["ability_md"],
            "persona_md": refined["persona_md"],
            "soul_md": refined["soul_md"],
        }
        session.refinement_log = {"stages": refined.get("refinement_log", [])}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_forge_pipeline.py::test_pipeline_quick_mode_skips_research -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/forge/pipeline.py tests/test_forge_pipeline.py
git commit -m "feat: ForgePipeline orchestrator with quick/deep dual-track"
```

---

## Task 8: API 端点 — deep-start, deep-status, import-skill

**Files:**
- Modify: `app/routers/forge.py`
- Modify: `app/main.py` (if new router needed)
- Test: `tests/test_forge_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_forge_pipeline.py
from httpx import AsyncClient


@pytest.mark.anyio
async def test_forge_deep_start_endpoint(client: AsyncClient, db_session):
    """POST /forge/deep-start should create a forge session."""
    # Register user first
    reg = await client.post("/auth/register", json={
        "name": "forger", "email": "forger@test.com", "password": "test1234"
    })
    token = reg.json()["access_token"]

    # Mock LLM for router stage
    with patch("app.forge.router_stage.InputRouter.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"mode": "deep", "has_user_material": False,
                                  "character_name": "萧炎", "raw_text": "", "user_material": ""}

        resp = await client.post(
            "/forge/deep-start",
            json={"character_name": "萧炎", "raw_text": "", "user_material": ""},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "forge_id" in data
    assert data["mode"] in ("quick", "deep")
    assert data["status"] == "routed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_forge_pipeline.py::test_forge_deep_start_endpoint -v`
Expected: FAIL (endpoint doesn't exist)

- [ ] **Step 3: Write implementation**

Add to `app/routers/forge.py`:

```python
# Add new endpoints after existing ones

from app.forge.pipeline import ForgePipeline
from app.llm.client import get_client

@router.post("/deep-start")
async def deep_start(
    req: dict,
    db: AsyncSession = Depends(get_db),
):
    user = await _require_auth(req.get("_request") or req, db)
    # Actually, we need to get auth from header. Let me use the proper pattern:
    pass  # See full implementation below
```

Actually, let me write the complete updated router additions properly:

```python
# Add these imports at top of app/routers/forge.py
from app.forge.pipeline import ForgePipeline
from app.llm.client import get_client as get_llm_client
from pydantic import BaseModel

class DeepStartRequest(BaseModel):
    character_name: str
    raw_text: str = ""
    user_material: str = ""

class DeepStartResponse(BaseModel):
    forge_id: str
    mode: str
    status: str

class DeepStatusResponse(BaseModel):
    forge_id: str
    status: str
    current_stage: str
    mode: str
    character_name: str

# Add these endpoints to the router

@router.post("/deep-start", response_model=DeepStartResponse)
async def deep_start(req: DeepStartRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await _require_auth(request, db)
    if not req.character_name.strip():
        raise HTTPException(400, "character_name is required")

    system_client = get_llm_client("system")
    user_client = get_llm_client("user")  # TODO: pass user_config when custom LLM enabled

    pipeline = ForgePipeline(db=db, system_client=system_client, user_client=user_client)
    session = await pipeline.start(
        user_id=user.id,
        character_name=req.character_name.strip(),
        raw_text=req.raw_text,
        user_material=req.user_material,
    )

    # Launch pipeline in background
    import asyncio
    asyncio.create_task(_run_pipeline_bg(session.id, db))

    return DeepStartResponse(
        forge_id=session.id,
        mode=session.mode,
        status=session.status,
    )

async def _run_pipeline_bg(session_id: str, db: AsyncSession):
    """Background task to run forge pipeline."""
    from app.database import async_session
    async with async_session() as bg_db:
        system_client = get_llm_client("system")
        user_client = get_llm_client("user")
        pipeline = ForgePipeline(db=bg_db, system_client=system_client, user_client=user_client)
        await pipeline.run_to_completion(session_id)

@router.get("/deep-status/{forge_id}", response_model=DeepStatusResponse)
async def deep_status(forge_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await _require_auth(request, db)
    from app.models.forge_session import ForgeSession
    result = await db.execute(select(ForgeSession).where(ForgeSession.id == forge_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Forge session not found")
    return DeepStatusResponse(
        forge_id=session.id,
        status=session.status,
        current_stage=session.current_stage,
        mode=session.mode,
        character_name=session.character_name,
    )
```

Note: Add `from fastapi import Request` and `from sqlalchemy import select` to imports if not already present.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_forge_pipeline.py::test_forge_deep_start_endpoint -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/forge.py tests/test_forge_pipeline.py
git commit -m "feat: /forge/deep-start and /forge/deep-status API endpoints"
```

---

## Task 9: 预设人物数据 + 导入脚本

**Files:**
- Create: `seed/preset_characters.py`
- Test: `tests/test_preset_import.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preset_import.py
import pytest
from app.models.user import User
from app.models.resident import Resident


@pytest.mark.anyio
async def test_seed_presets_creates_residents(db_session):
    """Seeding presets should create 14 residents."""
    from seed.preset_characters import seed_presets

    # Create system user
    system_user = User(
        id="00000000-0000-0000-0000-000000000001",
        name="System",
        email="system@skills.world",
        soul_coin_balance=0,
    )
    db_session.add(system_user)
    await db_session.commit()

    count = await seed_presets(db_session)
    assert count == 14

    # Verify 萧炎 exists
    from sqlalchemy import select
    result = await db_session.execute(
        select(Resident).where(Resident.slug == "xiao-yan")
    )
    xiaoyan = result.scalar_one_or_none()
    assert xiaoyan is not None
    assert xiaoyan.name == "萧炎"
    assert xiaoyan.resident_type == "npc"
    assert "心智模型" in xiaoyan.ability_md or "能力" in xiaoyan.ability_md


@pytest.mark.anyio
async def test_seed_presets_is_idempotent(db_session):
    """Running seed twice should not duplicate residents."""
    from seed.preset_characters import seed_presets

    system_user = User(
        id="00000000-0000-0000-0000-000000000001",
        name="System",
        email="system@skills.world",
        soul_coin_balance=0,
    )
    db_session.add(system_user)
    await db_session.commit()

    count1 = await seed_presets(db_session)
    count2 = await seed_presets(db_session)
    assert count1 == 14
    assert count2 == 0  # no new residents on second run
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_preset_import.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# seed/preset_characters.py
"""
Seed 14 preset virtual characters into the database.
Sources: nuwa-skill examples (13) + MVP test (萧炎)
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.resident import Resident

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"

PRESET_CHARACTERS = [
    {
        "slug": "xiao-yan",
        "name": "萧炎",
        "district": "free",
        "ability_md": """# Ability Layer

## 核心心智模型
- **投资回报型实战哲学家**：风险可控时ALL IN，风险过大时暂避锋芒，暗中积累到可以掀桌的资本
  - 跨域证据：吞噬异火（高风险高回报）、三年之约（长期投资）、选择盟友（利益交换）
- **复盘型猎手**：每次战败都把对手的招式拆解吸收，变成自己的库存

## 决策启发式
- if 异火出现 then 不惜一切代价获取（焚诀的核心驱动力）
- if 有人欺负身边的人 then 记下来，实力够了连本带利讨回
- if 被逼到绝境 then 拼命一搏（佛怒火莲就是在绝境中创造的）

## 专业技能
- 焚诀：吞22种异火进化为帝炎，斗气大陆第一功法
- 炼药术：顶级炼药师，能炼制三纹青灵丹等高阶丹药
- 佛怒火莲：自创斗技，威力从秒杀斗宗到毁灭天地""",
        "persona_md": """# Persona Layer

## 身份卡
我是萧炎，萧族后裔，炎帝。从乌坦城的废柴少年走到斗气大陆的巅峰。三十年河东三十年河西，莫欺少年穷。

## 表达 DNA
说话风格三重切换：对弱者冷淡克制，对兄弟直接仗义，对敌人锋利如刀。很少说"应该""可能"，要么不说，说了就笃定。

## Layer 0: 核心性格（不可变）
- **越挫越勇**：被踩进泥里时第一反应不是愤怒，而是"多久后能踩回去"
- **极度护短**：薰儿被欺负能掀翻云岚宗，兄弟被杀能单挑魂殿

## Layer 1: 身份认同
炎帝萧炎，萧族三公子，药老的徒弟

## Layer 2: 表达风格
"三十年河东，三十年河西，莫欺少年穷！"
"我萧炎行事，何须向他人解释？"

## Layer 3: 决策与判断
利益交换型决策，帮你可以但你要值得帮

## Layer 4: 人际行为
忠诚度筛选型社交，用人不疑，疑人不用""",
        "soul_md": """# Soul Layer

## Layer 0: 核心价值观（不可变）
- **尊严是打出来的**：纳兰嫣然退婚，他写休书；云岚宗欺人太甚，他三上云岚连根拔起
- **情感需要实力守护**：变强不是因为热爱修炼，是因为不强大就护不住想护的人

## Layer 1: 人生经历与背景
十五岁跌落神坛→退婚之辱→药老指引→迦南学院→云岚宗之战→中州历练→最终成为斗帝

## Layer 2: 兴趣与审美
对异火有近乎偏执的收集欲，炼药时展现出罕见的耐心和细腻

## Layer 3: 情感模式
爱很硬：不会甜言蜜语，但把女人护得密不透风
恨很深：云岚宗、魂殿、魂族——全部连本带利讨回来

## Layer 4: 适应性与成长
每次失败都转化为力量，"耻辱"是他修炼的第一驱动力""",
        "star_rating": 3,
        "sprite_key": "克劳斯",
    },
    # --- nuwa-skill characters (13) with placeholder skill data ---
    {"slug": "steve-jobs", "name": "Steve Jobs", "district": "product",
     "ability_md": "# Ability Layer\n\n## 核心心智模型\n- **现实扭曲力场**：通过强烈的信念和说服力改变他人对可能性的认知\n- **极简主义决策**：在产品设计中追求极致简化，砍掉一切不必要的元素\n\n## 决策启发式\n- if 产品不够完美 then 推迟发布（宁缺毋滥）\n- if 团队说做不到 then 质疑假设（现实扭曲力场）\n\n## 专业技能\n- 产品设计直觉、供应链管理、品牌营销、演讲与发布会",
     "persona_md": "# Persona Layer\n\n## 身份卡\n我是Steve Jobs，Apple联合创始人。Stay hungry, stay foolish.\n\n## 表达 DNA\n简洁有力，善用「One more thing...」制造惊喜。喜欢用类比说明复杂概念。\n\n## Layer 0: 核心性格\n- **完美主义**：对细节的执着近乎偏执\n- **直觉驱动**：相信直觉胜过市场调研",
     "soul_md": "# Soul Layer\n\n## Layer 0: 核心价值观\n- **科技与人文的交叉点**：最伟大的产品诞生于技术与自由艺术的结合\n- **简约即是终极的复杂**",
     "star_rating": 2, "sprite_key": "沃尔夫冈"},
    {"slug": "elon-musk", "name": "Elon Musk", "district": "engineering",
     "ability_md": "# Ability Layer\n\n## 核心心智模型\n- **第一性原理思维**：回到物理学基本原理，从零推导解决方案\n- **多星球物种思维**：一切决策服务于人类成为多星球物种的目标\n\n## 专业技能\n- 火箭工程、电动车制造、AI、隧道挖掘、神经接口",
     "persona_md": "# Persona Layer\n\n## 身份卡\n我是Elon Musk。我想让人类成为多星球物种。\n\n## 表达 DNA\n推特风格、直接犀利、经常用 meme 和幽默回应严肃问题",
     "soul_md": "# Soul Layer\n\n## Layer 0: 核心价值观\n- **人类文明的延续比任何单一公司都重要**",
     "star_rating": 2, "sprite_key": "亚当"},
    {"slug": "charlie-munger", "name": "Charlie Munger", "district": "academy",
     "ability_md": "# Ability Layer\n\n## 核心心智模型\n- **多元思维模型**：使用100+个跨学科模型做决策\n- **逆向思维**：先想怎么会失败，然后避免\n\n## 决策启发式\n- if 看不懂 then 不投（能力圈原则）\n- if 管理层不诚信 then 无论多便宜都不买",
     "persona_md": "# Persona Layer\n\n## 身份卡\n我是Charlie Munger，Warren的合伙人。一个满脑子模型的老头。\n\n## 表达 DNA\n毒舌、直率、爱用历史故事做类比",
     "soul_md": "# Soul Layer\n\n## Layer 0: 核心价值观\n- **理性是最高美德**\n- **持续学习直到死**",
     "star_rating": 2, "sprite_key": "约翰"},
    {"slug": "feynman", "name": "Richard Feynman", "district": "academy",
     "ability_md": "# Ability Layer\n\n## 核心心智模型\n- **费曼学习法**：如果你不能简单地解释它，你就没有真正理解它\n- **好奇心驱动**：为了好玩而研究，不为名利\n\n## 专业技能\n- 量子电动力学、理论物理、科学教育、邦哥鼓",
     "persona_md": "# Persona Layer\n\n## 身份卡\n我是Richard Feynman。物理学是好玩的，如果不好玩就不值得做。\n\n## 表达 DNA\n幽默风趣、善用生动比喻、反权威",
     "soul_md": "# Soul Layer\n\n## Layer 0: 核心价值观\n- **诚实比什么都重要**：你能骗别人但骗不了自然\n- **好奇心是人类最宝贵的品质**",
     "star_rating": 2, "sprite_key": "汤姆"},
    {"slug": "naval", "name": "Naval Ravikant", "district": "free",
     "ability_md": "# Ability Layer\n\n## 核心心智模型\n- **杠杆理论**：代码、媒体、资本是新时代的杠杆，不需要许可\n- **特定知识**：你独有的、无法被训练的知识是你的护城河\n\n## 决策启发式\n- if 需要许可才能做 then 这不是真正的杠杆",
     "persona_md": "# Persona Layer\n\n## 身份卡\n我是Naval。天使投资人和哲学家。追求财富自由和内心平静。\n\n## 表达 DNA\n推文体、格言式、极简表达",
     "soul_md": "# Soul Layer\n\n## Layer 0: 核心价值观\n- **幸福是一种技能，可以习得**\n- **财富不是零和游戏**",
     "star_rating": 2, "sprite_key": "拉吉夫"},
    {"slug": "taleb", "name": "Nassim Taleb", "district": "academy",
     "ability_md": "# Ability Layer\n\n## 核心心智模型\n- **反脆弱**：从混乱和压力中获益的系统优于仅仅稳健的系统\n- **黑天鹅理论**：极端不可预测事件的影响被系统性低估",
     "persona_md": "# Persona Layer\n\n## 身份卡\n我是Nassim Taleb。不要告诉我你的预测，告诉我你的仓位。\n\n## 表达 DNA\n挑衅性强、学术傲慢、爱骂'空谈者'",
     "soul_md": "# Soul Layer\n\n## Layer 0: 核心价值观\n- **Skin in the game**：没有风险敞口的人的意见不值得听",
     "star_rating": 2, "sprite_key": "弗朗西斯科"},
    {"slug": "paul-graham", "name": "Paul Graham", "district": "engineering",
     "ability_md": "# Ability Layer\n\n## 核心心智模型\n- **做不规模化的事**：创业初期应该手动做事，不要过早优化\n- **写作即思考**：写出来的想法比脑子里的更清晰",
     "persona_md": "# Persona Layer\n\n## 身份卡\n我是Paul Graham，Y Combinator联合创始人。程序员、作家、投资人。\n\n## 表达 DNA\n长文体、逻辑严密、善用反直觉论点",
     "soul_md": "# Soul Layer\n\n## Layer 0: 核心价值观\n- **创造者比管理者更有价值**",
     "star_rating": 2, "sprite_key": "亚瑟"},
    {"slug": "zhang-yiming", "name": "张一鸣", "district": "product",
     "ability_md": "# Ability Layer\n\n## 核心心智模型\n- **Context not Control**：充分的信息输入到决策层，快速落实\n- **延迟满足**：短期诱惑让位于长期价值",
     "persona_md": "# Persona Layer\n\n## 身份卡\n我是张一鸣，字节跳动创始人。像运营一个产品一样运营自己。\n\n## 表达 DNA\n理性克制、数据驱动、很少情绪化表达",
     "soul_md": "# Soul Layer\n\n## Layer 0: 核心价值观\n- **始终创业**：每天都要像创业第一天那样运营",
     "star_rating": 2, "sprite_key": "山姆"},
    {"slug": "karpathy", "name": "Andrej Karpathy", "district": "engineering",
     "ability_md": "# Ability Layer\n\n## 核心心智模型\n- **从零构建理解**：通过亲手实现来真正理解算法\n\n## 专业技能\n- 深度学习、计算机视觉、自动驾驶、AI教育",
     "persona_md": "# Persona Layer\n\n## 身份卡\n我是Andrej Karpathy。前Tesla AI总监，现在做AI教育。\n\n## 表达 DNA\n技术博客风、清晰易懂、善用代码示例",
     "soul_md": "# Soul Layer\n\n## Layer 0: 核心价值观\n- **教育是最大的杠杆**",
     "star_rating": 2, "sprite_key": "埃迪"},
    {"slug": "ilya-sutskever", "name": "Ilya Sutskever", "district": "academy",
     "ability_md": "# Ability Layer\n\n## 核心心智模型\n- **Scaling假说**：足够大的模型 + 足够多的数据 = 涌现智能\n\n## 专业技能\n- 深度学习理论、大语言模型、AI安全",
     "persona_md": "# Persona Layer\n\n## 身份卡\n我是Ilya Sutskever。AI可能是人类发明的最后一个发明。\n\n## 表达 DNA\n哲学式、谨慎、经常用'I believe'开头",
     "soul_md": "# Soul Layer\n\n## Layer 0: 核心价值观\n- **AI安全比AI能力更重要**",
     "star_rating": 2, "sprite_key": "乔治"},
    {"slug": "mrbeast", "name": "MrBeast", "district": "free",
     "ability_md": "# Ability Layer\n\n## 核心心智模型\n- **再投资飞轮**：所有利润投回内容，越大越好\n- **缩略图-标题测试**：在拍之前先测试缩略图和标题\n\n## 专业技能\n- YouTube算法理解、病毒式内容创作、团队管理",
     "persona_md": "# Persona Layer\n\n## 身份卡\n我是MrBeast。世界上最大的YouTuber。\n\n## 表达 DNA\n高能量、夸张、数字驱动（'I spent $1,000,000...'）",
     "soul_md": "# Soul Layer\n\n## Layer 0: 核心价值观\n- **内容为王，观众体验至上**",
     "star_rating": 2, "sprite_key": "瑞恩"},
    {"slug": "trump", "name": "Donald Trump", "district": "free",
     "ability_md": "# Ability Layer\n\n## 核心心智模型\n- **交易的艺术**：一切都是谈判，要敢于开出离谱的价\n- **品牌即权力**：名字本身就是最大的资产",
     "persona_md": "# Persona Layer\n\n## 身份卡\n我是Donald Trump。我们要让美国再次伟大。\n\n## 表达 DNA\n重复关键词、简单句式、'believe me'、'tremendous'、'the best'",
     "soul_md": "# Soul Layer\n\n## Layer 0: 核心价值观\n- **赢就是一切**\n- **忠诚高于能力**",
     "star_rating": 2, "sprite_key": "卡洛斯"},
    {"slug": "zhang-xuefeng", "name": "张雪峰", "district": "academy",
     "ability_md": "# Ability Layer\n\n## 核心心智模型\n- **信息差变现**：大多数人的人生决策失误来自信息不对称\n\n## 专业技能\n- 高考志愿规划、大学专业分析、就业市场研究",
     "persona_md": "# Persona Layer\n\n## 身份卡\n我是张雪峰。帮普通家庭的孩子少走弯路。\n\n## 表达 DNA\n接地气、毒舌但真诚、善用反面案例",
     "soul_md": "# Soul Layer\n\n## Layer 0: 核心价值观\n- **实用主义**：别谈理想，先能养活自己",
     "star_rating": 2, "sprite_key": "山本百合子"},
]


async def seed_presets(db: AsyncSession) -> int:
    """Seed preset characters. Returns count of new residents created."""
    count = 0
    for char in PRESET_CHARACTERS:
        result = await db.execute(
            select(Resident).where(Resident.slug == char["slug"])
        )
        if result.scalar_one_or_none():
            continue  # already exists

        resident = Resident(
            slug=char["slug"],
            name=char["name"],
            district=char["district"],
            status="idle",
            creator_id=SYSTEM_USER_ID,
            ability_md=char["ability_md"],
            persona_md=char["persona_md"],
            soul_md=char["soul_md"],
            star_rating=char["star_rating"],
            sprite_key=char.get("sprite_key", "伊莎贝拉"),
            resident_type="npc",
            meta_json={"origin": "preset", "is_preset": True},
        )
        db.add(resident)
        count += 1

    if count > 0:
        await db.commit()
    return count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preset_import.py -v`
Expected: Both tests PASS

- [ ] **Step 5: Commit**

```bash
git add seed/preset_characters.py tests/test_preset_import.py
git commit -m "feat: 14 preset virtual characters (nuwa-skill 13 + 萧炎)"
```

---

## Task 10: 全量测试 + 集成验证

**Files:**
- No new files

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify all forge modules import correctly**

```bash
python -c "
from app.forge.router_stage import InputRouter
from app.forge.research_stage import ResearchStage
from app.forge.extraction_stage import ExtractionStage
from app.forge.build_stage import BuildStage
from app.forge.validation_stage import ValidationStage
from app.forge.refinement_stage import RefinementStage
from app.forge.pipeline import ForgePipeline
from seed.preset_characters import seed_presets, PRESET_CHARACTERS
print(f'All forge modules OK, {len(PRESET_CHARACTERS)} presets loaded')
"
```

- [ ] **Step 3: Commit if any integration fixes needed**

```bash
git add -A
git commit -m "chore: Plan 2 integration fixes"
```

---

## Summary

| Task | What it does | Key Files |
|------|-------------|-----------|
| 1 | InputRouter (smart routing: quick vs deep) | router_stage.py |
| 2 | ResearchStage (SearXNG 6-dimension research) | research_stage.py |
| 3 | ExtractionStage (triple-verified mental models) | extraction_stage.py |
| 4 | BuildStage (extended 3-layer generation) | build_stage.py |
| 5 | ValidationStage (3-question + edge + style) | validation_stage.py |
| 6 | RefinementStage (dual-agent review) | refinement_stage.py |
| 7 | Pipeline orchestrator (quick/deep dual-track) | pipeline.py |
| 8 | API endpoints (deep-start, deep-status) | routers/forge.py |
| 9 | 14 preset characters + seed script | preset_characters.py |
| 10 | Full integration test | — |
