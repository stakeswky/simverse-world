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
