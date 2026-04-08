# Plan 4: Character Unification + Visual System

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每个 User 绑定一个 Resident(type="player") 记录，实现首次登录 Onboarding 流程（选择创建方式 → 选精灵 → 选回复模式 → 进入世界），支持 Skill 格式导入/转换、精灵模板智能匹配、AI 头像生成，以及基于 last_x/last_y 的出生点/重连位置恢复。

**Architecture:** Onboarding 是一个多步骤状态机，用户注册/登录后检测 `User.player_resident_id` 是否为空来决定是否进入 Onboarding。Skill 导入通过 LLM 分类格式并转换为标准三层结构。精灵匹配基于 25 个预标注模板 + LLM 特征提取。AI 头像通过 Gemini 图像生成 API 生成 Q 版肖像。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), httpx, Anthropic SDK, pytest + pytest-asyncio

**Working directory:** `/Users/jimmy/Downloads/Skills-World/.worktrees/mvp-implementation/backend/`

**Depends on:** Plan 1 (Foundation) — User.player_resident_id, User.last_x/last_y, Resident.resident_type/reply_mode/portrait_url fields

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/services/onboarding_service.py` | Create | Onboarding 流程：创建 player resident，绑定到 user |
| `app/services/skill_import_service.py` | Create | Skill 格式检测 + LLM 转换为标准三层 |
| `app/services/sprite_service.py` | Create | 25 精灵模板属性 + LLM 智能匹配 |
| `app/services/portrait_service.py` | Create | AI 头像生成（Gemini via Vertex AI） |
| `app/routers/onboarding.py` | Create | /onboarding/* 端点 |
| `app/routers/sprites.py` | Create | /sprites/templates, /sprites/match |
| `app/routers/avatar.py` | Create | /avatar/generate |
| `app/main.py` | Modify | Include 新 routers |
| `app/ws/handler.py` | Modify | 使用 User.last_x/last_y 恢复位置，断连时保存 |
| `tests/test_onboarding.py` | Create | Onboarding 流程测试 |
| `tests/test_skill_import.py` | Create | Skill 格式检测 + 转换测试 |
| `tests/test_sprite_service.py` | Create | 精灵匹配测试 |
| `tests/test_portrait.py` | Create | 头像生成测试（mock HTTP） |

---

## Task 1: Sprite Template Registry

**Files:**
- Create: `app/services/sprite_service.py`
- Test: `tests/test_sprite_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sprite_service.py
import pytest
from app.services.sprite_service import (
    SPRITE_TEMPLATES,
    get_all_templates,
    match_sprite_by_attributes,
    SpriteTemplate,
)


def test_sprite_templates_count():
    """Should have exactly 25 sprite templates."""
    assert len(SPRITE_TEMPLATES) == 25


def test_sprite_template_structure():
    """Each template should have required fields."""
    for tmpl in SPRITE_TEMPLATES:
        assert isinstance(tmpl, SpriteTemplate)
        assert tmpl.key  # non-empty string
        assert tmpl.gender in ("male", "female", "neutral")
        assert tmpl.age_group in ("young", "adult", "elder")
        assert tmpl.vibe  # non-empty string
        assert isinstance(tmpl.tags, list)


def test_get_all_templates():
    """Should return list of template dicts for API response."""
    result = get_all_templates()
    assert len(result) == 25
    assert "key" in result[0]
    assert "gender" in result[0]
    assert "vibe" in result[0]


def test_match_sprite_by_attributes_exact():
    """Should match sprite by gender + age_group."""
    result = match_sprite_by_attributes(gender="female", age_group="young", vibe="elegant")
    assert isinstance(result, list)
    assert len(result) >= 1
    assert all(r["gender"] == "female" for r in result)


def test_match_sprite_by_attributes_no_match_returns_all():
    """Should return all templates if no filters match."""
    result = match_sprite_by_attributes(gender="alien", age_group="ancient", vibe="cosmic")
    assert len(result) >= 1  # falls back to full list


def test_match_sprite_by_attributes_partial():
    """Should match on partial attributes."""
    result = match_sprite_by_attributes(gender="male")
    assert len(result) >= 1
    assert all(r["gender"] == "male" for r in result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sprite_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# app/services/sprite_service.py
"""Sprite template registry with 25 pre-annotated character sprites."""
from dataclasses import dataclass, field


@dataclass
class SpriteTemplate:
    key: str
    gender: str        # "male" | "female" | "neutral"
    age_group: str     # "young" | "adult" | "elder"
    vibe: str          # free-text descriptor: "elegant", "punk", "scholarly", etc.
    tags: list[str] = field(default_factory=list)


SPRITE_TEMPLATES: list[SpriteTemplate] = [
    # Original 20 from forge_service.py
    SpriteTemplate("伊莎贝拉", "female", "adult", "elegant", ["graceful", "noble"]),
    SpriteTemplate("克劳斯", "male", "adult", "serious", ["stern", "analytical"]),
    SpriteTemplate("亚当", "male", "young", "energetic", ["athletic", "bold"]),
    SpriteTemplate("梅", "female", "young", "gentle", ["soft", "caring"]),
    SpriteTemplate("塔玛拉", "female", "adult", "fierce", ["warrior", "confident"]),
    SpriteTemplate("亚瑟", "male", "elder", "wise", ["scholarly", "calm"]),
    SpriteTemplate("卡洛斯", "male", "adult", "charming", ["suave", "social"]),
    SpriteTemplate("弗朗西斯科", "male", "adult", "artistic", ["creative", "dreamy"]),
    SpriteTemplate("海莉", "female", "young", "cheerful", ["bubbly", "friendly"]),
    SpriteTemplate("拉托亚", "female", "adult", "bold", ["commanding", "leader"]),
    SpriteTemplate("詹妮弗", "female", "adult", "professional", ["sharp", "focused"]),
    SpriteTemplate("约翰", "male", "adult", "reliable", ["steady", "grounded"]),
    SpriteTemplate("玛丽亚", "female", "adult", "warm", ["maternal", "nurturing"]),
    SpriteTemplate("沃尔夫冈", "male", "elder", "eccentric", ["genius", "quirky"]),
    SpriteTemplate("汤姆", "male", "young", "casual", ["laid-back", "humorous"]),
    SpriteTemplate("山本百合子", "female", "young", "shy", ["reserved", "thoughtful"]),
    SpriteTemplate("山姆", "male", "young", "adventurous", ["explorer", "curious"]),
    SpriteTemplate("乔治", "male", "elder", "dignified", ["veteran", "respected"]),
    SpriteTemplate("简", "female", "young", "intellectual", ["bookish", "witty"]),
    SpriteTemplate("埃迪", "male", "young", "punk", ["rebellious", "tech"]),
    # 5 new templates to reach 25
    SpriteTemplate("苏菲", "female", "young", "mystical", ["ethereal", "intuitive"]),
    SpriteTemplate("雷克斯", "male", "adult", "tough", ["street-smart", "gritty"]),
    SpriteTemplate("林", "neutral", "young", "hacker", ["cyberpunk", "underground"]),
    SpriteTemplate("奥利维亚", "female", "elder", "regal", ["aristocratic", "sage"]),
    SpriteTemplate("凯", "neutral", "adult", "minimalist", ["zen", "balanced"]),
]

_TEMPLATE_DICT_CACHE: list[dict] | None = None


def _template_to_dict(t: SpriteTemplate) -> dict:
    return {
        "key": t.key,
        "gender": t.gender,
        "age_group": t.age_group,
        "vibe": t.vibe,
        "tags": t.tags,
    }


def get_all_templates() -> list[dict]:
    """Return all sprite templates as serializable dicts."""
    global _TEMPLATE_DICT_CACHE
    if _TEMPLATE_DICT_CACHE is None:
        _TEMPLATE_DICT_CACHE = [_template_to_dict(t) for t in SPRITE_TEMPLATES]
    return _TEMPLATE_DICT_CACHE


def match_sprite_by_attributes(
    gender: str | None = None,
    age_group: str | None = None,
    vibe: str | None = None,
) -> list[dict]:
    """Filter sprites by attribute criteria. Falls back to all if no matches."""
    candidates = SPRITE_TEMPLATES

    if gender:
        filtered = [t for t in candidates if t.gender == gender]
        if filtered:
            candidates = filtered

    if age_group:
        filtered = [t for t in candidates if t.age_group == age_group]
        if filtered:
            candidates = filtered

    if vibe:
        filtered = [t for t in candidates if vibe.lower() in t.vibe.lower()
                     or any(vibe.lower() in tag.lower() for tag in t.tags)]
        if filtered:
            candidates = filtered

    return [_template_to_dict(t) for t in candidates]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sprite_service.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/sprite_service.py tests/test_sprite_service.py
git commit -m "feat: sprite template registry with 25 annotated templates and attribute matching"
```

---

## Task 2: Skill Format Detection + Conversion Service

**Files:**
- Create: `app/services/skill_import_service.py`
- Test: `tests/test_skill_import.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_skill_import.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.skill_import_service import (
    detect_skill_format,
    convert_to_standard,
    SkillFormat,
)


def test_detect_standard_3layer():
    """Standard 3-layer Skill has # 能力, # 人格, # 灵魂 headers."""
    text = """# 能力档案
## 核心能力
Python 全栈

# 人格档案
## Layer 0: 第一印象
温和友善

# 灵魂档案
## 内核
追求真理
"""
    assert detect_skill_format(text) == SkillFormat.STANDARD_3LAYER


def test_detect_nuwa_skill():
    """Nuwa-skill has 11 numbered sections like 1. 角色定位."""
    text = """1. 角色定位
你是一个高级 Python 工程师

2. 核心能力
- 后端开发
- 数据库设计

3. 工作风格
严谨认真

4. 沟通方式
简洁明了

5. 知识领域
计算机科学

6. 限制
不做前端

7. 输出格式
Markdown

8. 示例对话
用户：你好
助手：你好！

9. 注意事项
保持专业

10. 错误处理
坦诚承认

11. 持续改进
不断学习
"""
    assert detect_skill_format(text) == SkillFormat.NUWA_11SECTION


def test_detect_colleague_skill():
    """Colleague-skill has ## System Prompt and ## User Prompt."""
    text = """## System Prompt
你是一个专业的数据分析师...

## User Prompt
请分析以下数据：{input}
"""
    assert detect_skill_format(text) == SkillFormat.COLLEAGUE_2LAYER


def test_detect_plain_text():
    """Plain text without any recognized structure."""
    text = "我是一个热爱编程的人，擅长 Python 和 JavaScript，喜欢解决问题。"
    assert detect_skill_format(text) == SkillFormat.PLAIN_TEXT


def test_detect_empty_text():
    """Empty text should be PLAIN_TEXT."""
    assert detect_skill_format("") == SkillFormat.PLAIN_TEXT


@pytest.mark.anyio
async def test_convert_standard_returns_as_is():
    """Standard 3-layer text should be returned split without LLM call."""
    text = """# 能力档案
核心技能描述

===SPLIT===

# 人格档案
性格特征描述

===SPLIT===

# 灵魂档案
内核价值观
"""
    result = await convert_to_standard(text, SkillFormat.STANDARD_3LAYER)
    assert "能力" in result["ability_md"]
    assert "人格" in result["persona_md"]
    assert "灵魂" in result["soul_md"]


@pytest.mark.anyio
async def test_convert_nuwa_calls_llm():
    """Non-standard formats should call LLM for conversion."""
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.text = """# 能力档案
## 核心能力
Python 开发

===SPLIT===

# 人格档案
## Layer 0: 第一印象
严谨认真

===SPLIT===

# 灵魂档案
## 内核
追求卓越"""
    mock_response.content = [mock_block]

    with patch("app.services.skill_import_service.get_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_get.return_value = mock_client

        result = await convert_to_standard(
            "1. 角色定位\n你是 Python 工程师\n2. 核心能力\n后端开发",
            SkillFormat.NUWA_11SECTION,
        )

    assert "能力" in result["ability_md"]
    assert "人格" in result["persona_md"]
    assert "灵魂" in result["soul_md"]
    mock_client.messages.create.assert_called_once()


@pytest.mark.anyio
async def test_convert_plain_text_calls_llm():
    """Plain text should also be converted via LLM."""
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.text = """# 能力档案
通用

===SPLIT===

# 人格档案
友善

===SPLIT===

# 灵魂档案
好奇"""
    mock_response.content = [mock_block]

    with patch("app.services.skill_import_service.get_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_get.return_value = mock_client

        result = await convert_to_standard(
            "我是一个热爱编程的人",
            SkillFormat.PLAIN_TEXT,
        )

    assert "ability_md" in result
    assert "persona_md" in result
    assert "soul_md" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_skill_import.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# app/services/skill_import_service.py
"""Skill format detection and conversion to standard 3-layer structure."""
import re
from enum import Enum

from app.llm.client import get_client
from app.config import settings


class SkillFormat(str, Enum):
    STANDARD_3LAYER = "standard_3layer"
    NUWA_11SECTION = "nuwa_11section"
    COLLEAGUE_2LAYER = "colleague_2layer"
    PLAIN_TEXT = "plain_text"


def detect_skill_format(text: str) -> SkillFormat:
    """Detect the format of imported Skill text using heuristic rules."""
    if not text.strip():
        return SkillFormat.PLAIN_TEXT

    # Standard 3-layer: has 能力/人格/灵魂 top-level headers
    has_ability = bool(re.search(r'^#\s*能力', text, re.MULTILINE))
    has_persona = bool(re.search(r'^#\s*人格', text, re.MULTILINE))
    has_soul = bool(re.search(r'^#\s*灵魂', text, re.MULTILINE))
    if sum([has_ability, has_persona, has_soul]) >= 2:
        return SkillFormat.STANDARD_3LAYER

    # Nuwa-skill: numbered sections (at least 5 of "1." through "11.")
    numbered_sections = re.findall(r'^\d{1,2}\.\s+\S+', text, re.MULTILINE)
    if len(numbered_sections) >= 5:
        return SkillFormat.NUWA_11SECTION

    # Colleague-skill: has "System Prompt" and "User Prompt"
    has_system = bool(re.search(r'(?i)##?\s*system\s*prompt', text))
    has_user = bool(re.search(r'(?i)##?\s*user\s*prompt', text))
    if has_system and has_user:
        return SkillFormat.COLLEAGUE_2LAYER

    return SkillFormat.PLAIN_TEXT


CONVERSION_SYSTEM_PROMPT = """你是一个 Skill 格式转换专家。用户会给你一段非标准格式的 AI 角色描述，
你需要将其转换为标准三层结构（能力档案 / 人格档案 / 灵魂档案）。

输出格式要求：
1. 三段内容用 ===SPLIT=== 分隔
2. 第一段以 "# 能力档案" 开头，包含 ## 核心能力、## 工具与技术、## 工作流程
3. 第二段以 "# 人格档案" 开头，包含 ## Layer 0: 第一印象、## Layer 1: 性格特征、## Layer 2: 深层动机
4. 第三段以 "# 灵魂档案" 开头，包含 ## 内核、## 价值观、## 禁忌

严格按照格式输出，不要输出其他内容。"""

CONVERSION_USER_TEMPLATE = """原始格式类型: {format_type}

原始内容:
{raw_text}

请转换为标准三层结构（用 ===SPLIT=== 分隔三段）:"""


async def convert_to_standard(
    text: str,
    detected_format: SkillFormat,
) -> dict[str, str]:
    """Convert Skill text to standard 3-layer dict with ability_md/persona_md/soul_md."""

    # Standard format: parse directly without LLM
    if detected_format == SkillFormat.STANDARD_3LAYER:
        return _parse_standard_3layer(text)

    # All other formats: use LLM to convert
    client = get_client()
    model = settings.effective_model

    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=CONVERSION_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": CONVERSION_USER_TEMPLATE.format(
                format_type=detected_format.value,
                raw_text=text[:8000],  # truncate to avoid token overflow
            ),
        }],
    )

    result_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            result_text = block.text
            break

    return _parse_split_output(result_text)


def _parse_standard_3layer(text: str) -> dict[str, str]:
    """Parse standard 3-layer text by top-level headers."""
    # Try ===SPLIT=== first
    if "===SPLIT===" in text:
        parts = [p.strip() for p in text.split("===SPLIT===")]
        return {
            "ability_md": parts[0] if len(parts) > 0 else "",
            "persona_md": parts[1] if len(parts) > 1 else "",
            "soul_md": parts[2] if len(parts) > 2 else "",
        }

    # Otherwise split by top-level headers
    ability_md = ""
    persona_md = ""
    soul_md = ""

    ability_match = re.search(r'(#\s*能力[^\n]*\n[\s\S]*?)(?=#\s*人格|#\s*灵魂|\Z)', text)
    persona_match = re.search(r'(#\s*人格[^\n]*\n[\s\S]*?)(?=#\s*灵魂|\Z)', text)
    soul_match = re.search(r'(#\s*灵魂[^\n]*\n[\s\S]*?)$', text)

    if ability_match:
        ability_md = ability_match.group(1).strip()
    if persona_match:
        persona_md = persona_match.group(1).strip()
    if soul_match:
        soul_md = soul_match.group(1).strip()

    return {
        "ability_md": ability_md,
        "persona_md": persona_md,
        "soul_md": soul_md,
    }


def _parse_split_output(text: str) -> dict[str, str]:
    """Parse LLM output that uses ===SPLIT=== delimiters."""
    parts = [p.strip() for p in text.split("===SPLIT===")]
    result = {
        "ability_md": parts[0] if len(parts) > 0 else "",
        "persona_md": parts[1] if len(parts) > 1 else "",
        "soul_md": parts[2] if len(parts) > 2 else "",
    }

    # Fallback: if split didn't work, try header-based parsing
    if len(parts) < 3:
        result = _parse_standard_3layer(text)

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_skill_import.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/skill_import_service.py tests/test_skill_import.py
git commit -m "feat: skill format detection (4 formats) and LLM-based conversion to standard 3-layer"
```

---

## Task 3: AI Portrait Generation Service

**Files:**
- Create: `app/services/portrait_service.py`
- Test: `tests/test_portrait.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_portrait.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.portrait_service import (
    generate_portrait,
    build_portrait_prompt,
    save_portrait_image,
    PORTRAIT_DIR,
)


def test_build_portrait_prompt():
    """Should build a descriptive prompt from persona text."""
    persona = """# 人格档案
## Layer 0: 第一印象
- 外貌：短发，戴眼镜，穿白色实验服
- 气质：冷静、理性、略带神秘感
"""
    prompt = build_portrait_prompt("Dr. Nova", persona)
    assert "Dr. Nova" in prompt
    assert "Q-style" in prompt or "chibi" in prompt or "pixel" in prompt
    assert isinstance(prompt, str)
    assert len(prompt) > 20


def test_build_portrait_prompt_no_persona():
    """Should work even with empty persona."""
    prompt = build_portrait_prompt("Unknown", "")
    assert "Unknown" in prompt
    assert len(prompt) > 10


@pytest.mark.anyio
async def test_generate_portrait_success():
    """Should call Gemini API and save image."""
    fake_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # fake PNG header

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": __import__("base64").b64encode(fake_image_bytes).decode(),
                    }
                }]
            }
        }]
    }

    with patch("app.services.portrait_service.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        with patch("app.services.portrait_service.save_portrait_image") as mock_save:
            mock_save.return_value = "/static/portraits/test-id.png"

            url = await generate_portrait("test-id", "Dr. Nova", "冷静理性的科学家")

    assert url == "/static/portraits/test-id.png"
    mock_client.post.assert_called_once()
    mock_save.assert_called_once()


@pytest.mark.anyio
async def test_generate_portrait_api_error():
    """Should return None on API failure."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = Exception("API Error")

    with patch("app.services.portrait_service.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        url = await generate_portrait("fail-id", "Nobody", "")

    assert url is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_portrait.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# app/services/portrait_service.py
"""AI portrait generation via Gemini image model (Vertex AI proxy)."""
import base64
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Gemini endpoint via Vertex AI proxy
GEMINI_BASE_URL = "http://100.93.72.102:3000/v1"
GEMINI_API_KEY = "sk-JH0TeDWO6dk0bRvJCcr6LLZCllFmEbI2CFDZGMquw0bLRetP"
GEMINI_MODEL = "gemini-3-pro-image-preview"

PORTRAIT_DIR = Path("static/portraits")


def build_portrait_prompt(name: str, persona_md: str) -> str:
    """Build image generation prompt from character name and persona description."""
    # Extract appearance hints from persona
    appearance_hints = ""
    if persona_md:
        lines = persona_md.split("\n")
        for line in lines:
            lower = line.lower()
            if any(kw in lower for kw in ["外貌", "appearance", "穿", "wear", "发", "hair", "眼", "eye"]):
                appearance_hints += line.strip() + " "
        appearance_hints = appearance_hints[:300]  # cap length

    if not appearance_hints:
        appearance_hints = "a cyberpunk city character with distinct personality"

    return (
        f"Generate a Q-style chibi pixel-art portrait of a character named '{name}'. "
        f"Character traits: {appearance_hints}. "
        f"Style: 2D pixel art, cyberpunk aesthetic, 128x128 pixels, "
        f"transparent background, game sprite portrait, cute chibi proportions. "
        f"Output a single character portrait, no text, no watermark."
    )


def save_portrait_image(resident_id: str, image_bytes: bytes) -> str:
    """Save portrait image to disk and return URL path."""
    PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{resident_id}.png"
    filepath = PORTRAIT_DIR / filename
    filepath.write_bytes(image_bytes)
    return f"/static/portraits/{filename}"


async def generate_portrait(
    resident_id: str,
    name: str,
    persona_md: str,
) -> str | None:
    """Generate AI portrait via Gemini. Returns URL path or None on failure."""
    prompt = build_portrait_prompt(name, persona_md)

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{GEMINI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {GEMINI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GEMINI_MODEL,
                    "messages": [
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 1,
                    "response_format": {"type": "image_url"},
                },
            )

            if response.status_code != 200:
                logger.error(f"Gemini API returned {response.status_code}: {response.text[:200]}")
                return None

            data = response.json()

            # Parse Gemini image response
            # The proxy may return in OpenAI-compatible format or Gemini native format
            image_data = None

            # Try OpenAI-compatible format (base64 in content)
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                for part in parts:
                    inline = part.get("inlineData", {})
                    if inline.get("data"):
                        image_data = base64.b64decode(inline["data"])
                        break

            # Try OpenAI chat completion format
            if not image_data:
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    # Content might be base64 encoded image
                    if content and not content.startswith("{"):
                        try:
                            image_data = base64.b64decode(content)
                        except Exception:
                            pass

            if not image_data:
                logger.error(f"Could not extract image from Gemini response: {str(data)[:300]}")
                return None

            return save_portrait_image(resident_id, image_data)

    except Exception as e:
        logger.error(f"Portrait generation failed for {resident_id}: {e}")
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_portrait.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/portrait_service.py tests/test_portrait.py
git commit -m "feat: AI portrait generation via Gemini (prompt builder, image save, API client)"
```

---

## Task 4: Onboarding Service

**Files:**
- Create: `app/services/onboarding_service.py`
- Test: `tests/test_onboarding.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_onboarding.py
import pytest
import random
from unittest.mock import AsyncMock, patch, MagicMock
from app.models.user import User
from app.models.resident import Resident
from app.services.onboarding_service import (
    check_onboarding_needed,
    create_player_resident,
    CENTRAL_PLAZA_X,
    CENTRAL_PLAZA_Y,
    SPAWN_RADIUS,
)


@pytest.mark.anyio
async def test_check_onboarding_needed_new_user(db_session):
    """New user with no player_resident_id needs onboarding."""
    user = User(name="New", email="new@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    result = await check_onboarding_needed(db_session, user.id)
    assert result["needs_onboarding"] is True
    assert result["player_resident_id"] is None


@pytest.mark.anyio
async def test_check_onboarding_not_needed(db_session):
    """User with existing player_resident_id does not need onboarding."""
    user = User(name="Existing", email="existing@test.com", player_resident_id="res-123")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    result = await check_onboarding_needed(db_session, user.id)
    assert result["needs_onboarding"] is False
    assert result["player_resident_id"] == "res-123"


@pytest.mark.anyio
async def test_create_player_resident_minimal(db_session):
    """Create a player resident with minimal info (skip flow)."""
    user = User(name="Player", email="player@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resident = await create_player_resident(
        db=db_session,
        user_id=user.id,
        name="Player",
        sprite_key="埃迪",
        reply_mode="auto",
        ability_md="",
        persona_md="",
        soul_md="",
    )

    assert resident.resident_type == "player"
    assert resident.sprite_key == "埃迪"
    assert resident.reply_mode == "auto"
    assert resident.creator_id == user.id

    # User should be updated with player_resident_id and spawn position
    await db_session.refresh(user)
    assert user.player_resident_id == resident.id
    assert user.last_x is not None
    assert user.last_y is not None


@pytest.mark.anyio
async def test_create_player_resident_spawn_near_plaza(db_session):
    """Spawn position should be within SPAWN_RADIUS of Central Plaza."""
    user = User(name="Spawner", email="spawner@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    random.seed(42)  # deterministic test
    resident = await create_player_resident(
        db=db_session,
        user_id=user.id,
        name="Spawner",
        sprite_key="亚当",
        reply_mode="manual",
    )

    await db_session.refresh(user)
    dx = abs(user.last_x - CENTRAL_PLAZA_X)
    dy = abs(user.last_y - CENTRAL_PLAZA_Y)
    assert dx <= SPAWN_RADIUS
    assert dy <= SPAWN_RADIUS


@pytest.mark.anyio
async def test_create_player_resident_with_skill_data(db_session):
    """Create player resident with full Skill data."""
    user = User(name="SkillUser", email="skill@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resident = await create_player_resident(
        db=db_session,
        user_id=user.id,
        name="SkillUser",
        sprite_key="简",
        reply_mode="auto",
        ability_md="# 能力档案\n全栈工程师",
        persona_md="# 人格档案\n友善、耐心",
        soul_md="# 灵魂档案\n追求卓越",
    )

    assert resident.ability_md == "# 能力档案\n全栈工程师"
    assert resident.persona_md == "# 人格档案\n友善、耐心"
    assert resident.soul_md == "# 灵魂档案\n追求卓越"


@pytest.mark.anyio
async def test_create_player_resident_duplicate_blocked(db_session):
    """Should raise if user already has a player resident."""
    user = User(name="Dup", email="dup@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    await create_player_resident(
        db=db_session, user_id=user.id, name="Dup",
        sprite_key="埃迪", reply_mode="auto",
    )

    with pytest.raises(ValueError, match="already has a player resident"):
        await create_player_resident(
            db=db_session, user_id=user.id, name="Dup2",
            sprite_key="亚当", reply_mode="auto",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_onboarding.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# app/services/onboarding_service.py
"""Onboarding service: create player resident, bind to user, assign spawn point."""
import random
import uuid
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.resident import Resident

# Central Plaza spawn point
CENTRAL_PLAZA_X = 76
CENTRAL_PLAZA_Y = 50
SPAWN_RADIUS = 5


async def check_onboarding_needed(db: AsyncSession, user_id: str) -> dict:
    """Check if user needs onboarding (no player_resident_id yet)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(f"User {user_id} not found")

    return {
        "needs_onboarding": user.player_resident_id is None,
        "player_resident_id": user.player_resident_id,
    }


async def create_player_resident(
    db: AsyncSession,
    user_id: str,
    name: str,
    sprite_key: str,
    reply_mode: str = "auto",
    ability_md: str = "",
    persona_md: str = "",
    soul_md: str = "",
    portrait_url: str | None = None,
) -> Resident:
    """Create a Resident(type='player') and bind it to the User."""
    # Check user exists and doesn't already have a player resident
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(f"User {user_id} not found")
    if user.player_resident_id:
        raise ValueError(f"User {user_id} already has a player resident")

    # Generate spawn position near Central Plaza
    spawn_x = CENTRAL_PLAZA_X + random.randint(-SPAWN_RADIUS, SPAWN_RADIUS)
    spawn_y = CENTRAL_PLAZA_Y + random.randint(-SPAWN_RADIUS, SPAWN_RADIUS)

    # Generate unique slug
    slug = _generate_player_slug(name)
    existing = await db.execute(select(Resident).where(Resident.slug == slug))
    if existing.scalar_one_or_none():
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    resident = Resident(
        slug=slug,
        name=name,
        district="free",
        status="idle",
        resident_type="player",
        reply_mode=reply_mode,
        sprite_key=sprite_key,
        tile_x=spawn_x,
        tile_y=spawn_y,
        creator_id=user_id,
        ability_md=ability_md,
        persona_md=persona_md,
        soul_md=soul_md,
        portrait_url=portrait_url,
        meta_json={"origin": "onboarding"},
    )
    db.add(resident)

    # Bind to user and set initial position
    user.player_resident_id = resident.id
    user.last_x = spawn_x
    user.last_y = spawn_y

    await db.commit()
    await db.refresh(resident)
    return resident


def _generate_player_slug(name: str) -> str:
    """Generate a URL-friendly slug from player name."""
    slug = name.lower().strip()
    slug = re.sub(r'[^\w\u4e00-\u9fff-]', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    if not slug:
        slug = f"player-{uuid.uuid4().hex[:8]}"
    return f"p-{slug}"  # prefix with p- to distinguish from NPC residents
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_onboarding.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/onboarding_service.py tests/test_onboarding.py
git commit -m "feat: onboarding service (player resident creation, spawn point, user binding)"
```

---

## Task 5: LLM-based Sprite Matching

**Files:**
- Modify: `app/services/sprite_service.py`
- Test: `tests/test_sprite_service.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_sprite_service.py
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.sprite_service import match_sprite_by_persona


@pytest.mark.anyio
async def test_match_sprite_by_persona_llm():
    """Should call LLM to extract appearance features and match template."""
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.text = '{"gender": "female", "age_group": "young", "vibe": "shy"}'
    mock_response.content = [mock_block]

    with patch("app.services.sprite_service.get_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_get.return_value = mock_client

        result = await match_sprite_by_persona("一个害羞的年轻女孩，喜欢安静地读书")

    assert isinstance(result, list)
    assert len(result) >= 1
    # First result should be the best match (山本百合子 — shy young female)
    assert result[0]["key"] == "山本百合子"
    mock_client.messages.create.assert_called_once()


@pytest.mark.anyio
async def test_match_sprite_by_persona_llm_failure_fallback():
    """Should fall back to all templates if LLM fails."""
    with patch("app.services.sprite_service.get_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("LLM down"))
        mock_get.return_value = mock_client

        result = await match_sprite_by_persona("some persona text")

    assert isinstance(result, list)
    assert len(result) == 25  # all templates as fallback
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sprite_service.py::test_match_sprite_by_persona_llm -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

```python
# Add to app/services/sprite_service.py — new imports at top:
import json
import logging
from app.llm.client import get_client
from app.config import settings

logger = logging.getLogger(__name__)

# Add this constant:
SPRITE_MATCH_SYSTEM_PROMPT = """你是一个角色外貌分析专家。根据用户给出的角色描述，提取外貌特征。

输出严格 JSON 格式:
{"gender": "male|female|neutral", "age_group": "young|adult|elder", "vibe": "一个词描述气质"}

只输出 JSON，不要输出其他内容。"""


# Add this function:
async def match_sprite_by_persona(persona_text: str) -> list[dict]:
    """Use LLM to extract appearance features from persona, then match templates."""
    try:
        client = get_client()
        response = await client.messages.create(
            model=settings.effective_model,
            max_tokens=100,
            system=SPRITE_MATCH_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": persona_text[:2000]}],
        )

        result_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                result_text = block.text
                break

        # Parse JSON from LLM response
        import re
        json_match = re.search(r'\{[^}]+\}', result_text)
        if json_match:
            attrs = json.loads(json_match.group())
            matched = match_sprite_by_attributes(
                gender=attrs.get("gender"),
                age_group=attrs.get("age_group"),
                vibe=attrs.get("vibe"),
            )
            if matched:
                return matched

    except Exception as e:
        logger.warning(f"LLM sprite matching failed, falling back to all: {e}")

    return get_all_templates()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sprite_service.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/sprite_service.py tests/test_sprite_service.py
git commit -m "feat: LLM-based sprite matching from persona description"
```

---

## Task 6: Onboarding Router + Sprites Router + Avatar Router

**Files:**
- Create: `app/routers/onboarding.py`
- Create: `app/routers/sprites.py`
- Create: `app/routers/avatar.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_onboarding.py
from httpx import AsyncClient


@pytest.mark.anyio
async def test_onboarding_check_endpoint(client: AsyncClient):
    """GET /onboarding/check should return onboarding status."""
    # Register a user first
    reg = await client.post("/auth/register", json={
        "name": "OnboardTest", "email": "onboard@test.com", "password": "pass123"
    })
    token = reg.json()["access_token"]

    resp = await client.get(
        "/onboarding/check",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_onboarding"] is True


@pytest.mark.anyio
async def test_onboarding_complete_endpoint(client: AsyncClient):
    """POST /onboarding/complete should create player resident."""
    reg = await client.post("/auth/register", json={
        "name": "CompleteTest", "email": "complete@test.com", "password": "pass123"
    })
    token = reg.json()["access_token"]

    resp = await client.post(
        "/onboarding/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "CompleteTest",
            "sprite_key": "埃迪",
            "reply_mode": "auto",
            "ability_md": "",
            "persona_md": "",
            "soul_md": "",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["resident"]["resident_type"] == "player"
    assert data["resident"]["sprite_key"] == "埃迪"
    assert data["spawn"]["x"] is not None
    assert data["spawn"]["y"] is not None


@pytest.mark.anyio
async def test_onboarding_complete_duplicate_blocked(client: AsyncClient):
    """POST /onboarding/complete twice should fail."""
    reg = await client.post("/auth/register", json={
        "name": "DupTest", "email": "dup2@test.com", "password": "pass123"
    })
    token = reg.json()["access_token"]

    await client.post(
        "/onboarding/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "DupTest", "sprite_key": "埃迪", "reply_mode": "auto"},
    )

    resp = await client.post(
        "/onboarding/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "DupTest2", "sprite_key": "亚当", "reply_mode": "auto"},
    )
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_sprites_templates_endpoint(client: AsyncClient):
    """GET /sprites/templates should return 25 templates."""
    resp = await client.get("/sprites/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["templates"]) == 25


@pytest.mark.anyio
async def test_sprites_match_endpoint(client: AsyncClient):
    """POST /sprites/match should return matched templates."""
    resp = await client.post("/sprites/match", json={
        "gender": "female",
        "age_group": "young",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["matches"]) >= 1
    assert all(m["gender"] == "female" for m in data["matches"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_onboarding.py::test_onboarding_check_endpoint -v`
Expected: FAIL (404 — endpoint doesn't exist)

- [ ] **Step 3: Write onboarding router**

```python
# app/routers/onboarding.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.onboarding_service import check_onboarding_needed, create_player_resident
from app.models.user import User

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingCompleteRequest(BaseModel):
    name: str
    sprite_key: str
    reply_mode: str = "auto"
    ability_md: str = ""
    persona_md: str = ""
    soul_md: str = ""


async def _get_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(lambda: None),  # placeholder
) -> User:
    """Extract user from Authorization header."""
    # We'll use a proper dependency below
    pass


def _extract_token(authorization: str = "") -> str:
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return ""


@router.get("/check")
async def check(
    db: AsyncSession = Depends(get_db),
    authorization: str = Depends(lambda: ""),
):
    """Check if current user needs onboarding."""
    from fastapi import Header
    raise NotImplementedError  # replaced below


# Proper implementation using Header dependency:
from fastapi import Header


@router.get("/check")
async def onboarding_check(
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(default=""),
):
    """Check if current user needs onboarding."""
    token = authorization.replace("Bearer ", "") if authorization else ""
    user = await get_current_user(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    result = await check_onboarding_needed(db, user.id)
    return result


@router.post("/complete")
async def onboarding_complete(
    req: OnboardingCompleteRequest,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(default=""),
):
    """Complete onboarding: create player resident and bind to user."""
    token = authorization.replace("Bearer ", "") if authorization else ""
    user = await get_current_user(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        resident = await create_player_resident(
            db=db,
            user_id=user.id,
            name=req.name,
            sprite_key=req.sprite_key,
            reply_mode=req.reply_mode,
            ability_md=req.ability_md,
            persona_md=req.persona_md,
            soul_md=req.soul_md,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Re-fetch user for updated spawn position
    await db.refresh(user)
    return {
        "resident": {
            "id": resident.id,
            "slug": resident.slug,
            "name": resident.name,
            "resident_type": resident.resident_type,
            "sprite_key": resident.sprite_key,
            "reply_mode": resident.reply_mode,
        },
        "spawn": {
            "x": user.last_x,
            "y": user.last_y,
        },
    }
```

- [ ] **Step 4: Write sprites router**

```python
# app/routers/sprites.py
from fastapi import APIRouter
from pydantic import BaseModel
from app.services.sprite_service import get_all_templates, match_sprite_by_attributes

router = APIRouter(prefix="/sprites", tags=["sprites"])


class SpriteMatchRequest(BaseModel):
    gender: str | None = None
    age_group: str | None = None
    vibe: str | None = None


@router.get("/templates")
async def list_templates():
    """List all 25 available sprite templates."""
    return {"templates": get_all_templates()}


@router.post("/match")
async def match_sprites(req: SpriteMatchRequest):
    """Match sprites by attribute filters."""
    matches = match_sprite_by_attributes(
        gender=req.gender,
        age_group=req.age_group,
        vibe=req.vibe,
    )
    return {"matches": matches}
```

- [ ] **Step 5: Write avatar router**

```python
# app/routers/avatar.py
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.resident import Resident
from app.services.auth_service import get_current_user
from app.services.portrait_service import generate_portrait

router = APIRouter(prefix="/avatar", tags=["avatar"])


class GenerateAvatarRequest(BaseModel):
    resident_id: str
    persona_md: str = ""


@router.post("/generate")
async def generate_avatar(
    req: GenerateAvatarRequest,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(default=""),
):
    """Generate AI portrait for a resident."""
    token = authorization.replace("Bearer ", "") if authorization else ""
    user = await get_current_user(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Verify resident exists and belongs to user
    result = await db.execute(
        select(Resident).where(
            Resident.id == req.resident_id,
            Resident.creator_id == user.id,
        )
    )
    resident = result.scalar_one_or_none()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found or not owned by you")

    persona = req.persona_md or resident.persona_md
    url = await generate_portrait(resident.id, resident.name, persona)

    if not url:
        raise HTTPException(status_code=502, detail="Portrait generation failed")

    # Update resident portrait_url
    resident.portrait_url = url
    await db.commit()

    return {"portrait_url": url}
```

- [ ] **Step 6: Register routers in main.py**

Add to `app/main.py`:

```python
# After existing router imports, add:
from app.routers import onboarding, sprites, avatar

# After existing include_router calls, add:
app.include_router(onboarding.router)
app.include_router(sprites.router)
app.include_router(avatar.router)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_onboarding.py -v`
Expected: All 11 tests PASS (6 service + 5 endpoint)

- [ ] **Step 8: Commit**

```bash
git add app/routers/onboarding.py app/routers/sprites.py app/routers/avatar.py app/main.py tests/test_onboarding.py
git commit -m "feat: onboarding/sprites/avatar routers + register in main.py"
```

---

## Task 7: Skill Import Endpoint

**Files:**
- Modify: `app/routers/onboarding.py`
- Test: `tests/test_skill_import.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_skill_import.py

@pytest.mark.anyio
async def test_skill_detect_endpoint(client):
    """POST /onboarding/skill/detect should classify format."""
    resp = await client.post("/onboarding/skill/detect", json={
        "text": "# 能力档案\n技能\n# 人格档案\n性格\n# 灵魂档案\n内核"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "standard_3layer"


@pytest.mark.anyio
async def test_skill_convert_standard_endpoint(client):
    """POST /onboarding/skill/convert should return parsed layers."""
    resp = await client.post("/onboarding/skill/convert", json={
        "text": "# 能力档案\nPython\n# 人格档案\n友善\n# 灵魂档案\n好奇",
        "format": "standard_3layer",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "ability_md" in data
    assert "persona_md" in data
    assert "soul_md" in data
    assert "能力" in data["ability_md"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_skill_import.py::test_skill_detect_endpoint -v`
Expected: FAIL (404)

- [ ] **Step 3: Write implementation**

Add to `app/routers/onboarding.py`:

```python
# Add import at top:
from app.services.skill_import_service import detect_skill_format, convert_to_standard, SkillFormat


class SkillDetectRequest(BaseModel):
    text: str


class SkillConvertRequest(BaseModel):
    text: str
    format: str  # SkillFormat value


@router.post("/skill/detect")
async def skill_detect(req: SkillDetectRequest):
    """Detect the format of imported Skill text."""
    detected = detect_skill_format(req.text)
    return {"format": detected.value}


@router.post("/skill/convert")
async def skill_convert(req: SkillConvertRequest):
    """Convert Skill text to standard 3-layer structure."""
    try:
        fmt = SkillFormat(req.format)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown format: {req.format}")

    result = await convert_to_standard(req.text, fmt)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_skill_import.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/onboarding.py tests/test_skill_import.py
git commit -m "feat: /onboarding/skill/detect and /onboarding/skill/convert endpoints"
```

---

## Task 8: WebSocket Spawn + Position Persistence

**Files:**
- Modify: `app/ws/handler.py`
- Modify: `app/ws/manager.py`

- [ ] **Step 1: Modify handler for User.last_x/last_y spawn and disconnect save**

Replace the relevant sections in `app/ws/handler.py`:

```python
# In websocket_handler(), REPLACE the block that initializes position:
#   manager.update_position(user_id, 76 * 32, 50 * 32, "down", user_name)
# WITH:

    # Determine spawn position: restore from DB or use Central Plaza default
    spawn_x = 76 * 32  # Central Plaza default (tile coords * 32)
    spawn_y = 50 * 32
    sprite_key = "埃迪"  # default sprite

    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user_row = result.scalar_one_or_none()
        if user_row:
            if user_row.last_x is not None and user_row.last_y is not None:
                # Restore saved position (last_x/last_y are tile coords)
                spawn_x = user_row.last_x * 32
                spawn_y = user_row.last_y * 32
            # If user has a player resident, use their sprite_key
            if user_row.player_resident_id:
                res_result = await db.execute(
                    select(Resident).where(Resident.id == user_row.player_resident_id)
                )
                player_resident = res_result.scalar_one_or_none()
                if player_resident:
                    sprite_key = player_resident.sprite_key

    manager.update_position(user_id, spawn_x, spawn_y, "down", user_name, sprite_key)
```

Then update the `move` handler to include sprite_key in broadcasts:

```python
            # In the move handler, update:
            if msg_type == "move":
                x = float(data.get("x", 0))
                y = float(data.get("y", 0))
                direction = str(data.get("direction", "down"))
                manager.update_position(user_id, x, y, direction, user_name, sprite_key)
                await manager.broadcast(
                    {"type": "player_moved", "player_id": user_id,
                     "name": user_name, "sprite_key": sprite_key,
                     "x": x, "y": y, "direction": direction},
                    exclude=user_id,
                )
                continue
```

Update the `player_joined` broadcast to include sprite_key:

```python
    await manager.broadcast(
        {
            "type": "player_joined",
            "player_id": user_id,
            "name": user_name,
            "sprite_key": sprite_key,
            "x": pos.get("x", 0),
            "y": pos.get("y", 0),
            "direction": pos.get("direction", "down"),
        },
        exclude=user_id,
    )
```

- [ ] **Step 2: Add position save on disconnect**

Replace the `except WebSocketDisconnect` block in `app/ws/handler.py`:

```python
    except WebSocketDisconnect:
        # Save player position to DB before cleanup
        last_pos = manager.positions.get(user_id, {})
        if last_pos:
            async with async_session() as db:
                result = await db.execute(select(User).where(User.id == user_id))
                user_row = result.scalar_one_or_none()
                if user_row:
                    # Convert pixel coords back to tile coords
                    user_row.last_x = int(last_pos.get("x", 0)) // 32
                    user_row.last_y = int(last_pos.get("y", 0)) // 32
                    await db.commit()

        if current_conversation and current_resident:
            manager.unlock_resident(current_resident.id)
            async with async_session() as db:
                result = await db.execute(select(Resident).where(Resident.id == current_resident.id))
                r = result.scalar_one_or_none()
                if r and r.status == "chatting":
                    r.status = "popular" if r.heat >= 50 else "idle"
                    await db.commit()
        await manager.broadcast({"type": "player_left", "player_id": user_id}, exclude=user_id)
        manager.disconnect(user_id)
```

- [ ] **Step 3: Update ConnectionManager to store sprite_key**

Modify `app/ws/manager.py`:

```python
    def update_position(self, user_id: str, x: float, y: float,
                        direction: str, name: str, sprite_key: str = "埃迪") -> None:
        self.positions[user_id] = {
            "x": x, "y": y, "direction": direction,
            "name": name, "sprite_key": sprite_key,
        }
```

- [ ] **Step 4: Run full test suite to verify no regressions**

Run: `python -m pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/ws/handler.py app/ws/manager.py
git commit -m "feat: spawn from User.last_x/last_y, save position on disconnect, broadcast sprite_key"
```

---

## Task 9: Onboarding with Skill Import + Sprite Match Integration

**Files:**
- Modify: `app/routers/onboarding.py`
- Test: `tests/test_onboarding.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_onboarding.py
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.anyio
async def test_onboarding_complete_with_import(client: AsyncClient):
    """POST /onboarding/complete with imported Skill data."""
    reg = await client.post("/auth/register", json={
        "name": "ImportUser", "email": "import@test.com", "password": "pass123"
    })
    token = reg.json()["access_token"]

    resp = await client.post(
        "/onboarding/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "ImportUser",
            "sprite_key": "简",
            "reply_mode": "manual",
            "ability_md": "# 能力档案\n## 核心能力\nPython 全栈开发",
            "persona_md": "# 人格档案\n## Layer 0\n冷静、理性",
            "soul_md": "# 灵魂档案\n## 内核\n追求技术极致",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["resident"]["name"] == "ImportUser"
    assert data["resident"]["sprite_key"] == "简"
    assert data["resident"]["reply_mode"] == "manual"


@pytest.mark.anyio
async def test_onboarding_sprite_match_by_persona(client: AsyncClient):
    """POST /sprites/match-by-persona should use LLM matching."""
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.text = '{"gender": "male", "age_group": "young", "vibe": "punk"}'
    mock_response.content = [mock_block]

    with patch("app.services.sprite_service.get_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_get.return_value = mock_client

        resp = await client.post("/sprites/match-by-persona", json={
            "persona_text": "一个叛逆的年轻黑客，喜欢赛博朋克文化"
        })

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["matches"]) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_onboarding.py::test_onboarding_sprite_match_by_persona -v`
Expected: FAIL (404)

- [ ] **Step 3: Add persona-based sprite matching endpoint**

Add to `app/routers/sprites.py`:

```python
# Add import at top:
from app.services.sprite_service import match_sprite_by_persona


class SpritePersonaMatchRequest(BaseModel):
    persona_text: str


@router.post("/match-by-persona")
async def match_by_persona(req: SpritePersonaMatchRequest):
    """Use LLM to analyze persona and match best sprites."""
    matches = await match_sprite_by_persona(req.persona_text)
    return {"matches": matches}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_onboarding.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/onboarding.py app/routers/sprites.py tests/test_onboarding.py
git commit -m "feat: onboarding skill import integration + persona-based sprite matching endpoint"
```

---

## Task 10: Full Test Suite + Cleanup

**Files:**
- No new files

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Verify new endpoint registration**

Run: `python -c "from app.main import app; routes = [r.path for r in app.routes]; print([r for r in routes if 'onboard' in r or 'sprite' in r or 'avatar' in r])"`
Expected: `['/onboarding/check', '/onboarding/complete', '/onboarding/skill/detect', '/onboarding/skill/convert', '/sprites/templates', '/sprites/match', '/sprites/match-by-persona', '/avatar/generate']`

- [ ] **Step 3: Verify sprite template count**

Run: `python -c "from app.services.sprite_service import SPRITE_TEMPLATES; print(f'{len(SPRITE_TEMPLATES)} sprites'); assert len(SPRITE_TEMPLATES) == 25"`
Expected: `25 sprites`

- [ ] **Step 4: Verify Skill format detection for all 4 types**

Run:
```bash
python -c "
from app.services.skill_import_service import detect_skill_format, SkillFormat
assert detect_skill_format('# 能力档案\nx\n# 人格档案\ny\n# 灵魂档案\nz') == SkillFormat.STANDARD_3LAYER
assert detect_skill_format('1. 角色\nx\n2. 能力\ny\n3. 风格\nz\n4. 方式\na\n5. 领域\nb') == SkillFormat.NUWA_11SECTION
assert detect_skill_format('## System Prompt\nx\n## User Prompt\ny') == SkillFormat.COLLEAGUE_2LAYER
assert detect_skill_format('just some text') == SkillFormat.PLAIN_TEXT
print('All 4 format detections OK')
"
```
Expected: `All 4 format detections OK`

- [ ] **Step 5: Commit any cleanup**

```bash
git add -A
git commit -m "chore: Plan 4 character unification + visual system complete"
```

---

## Summary

| Task | What it does | Key Files |
|------|-------------|-----------|
| 1 | 25 sprite templates with attribute registry | sprite_service.py |
| 2 | Skill format detection (4 formats) + LLM conversion | skill_import_service.py |
| 3 | AI portrait generation via Gemini | portrait_service.py |
| 4 | Onboarding service (player resident + spawn + binding) | onboarding_service.py |
| 5 | LLM-based persona-to-sprite matching | sprite_service.py |
| 6 | Onboarding/sprites/avatar routers + main.py registration | routers/*.py, main.py |
| 7 | Skill import API endpoints (/detect, /convert) | onboarding.py |
| 8 | WS spawn from last_x/last_y + save on disconnect | handler.py, manager.py |
| 9 | Integration: onboarding with Skill import + persona matching | routers, tests |
| 10 | Full test suite verification + cleanup | — |
