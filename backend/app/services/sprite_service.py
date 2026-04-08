"""Sprite template registry with 25 pre-annotated character sprites and LLM-based matching."""
import json
import logging
import re
from dataclasses import dataclass, field

from app.llm.client import get_client
from app.config import settings

logger = logging.getLogger(__name__)


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


# --- LLM-based sprite matching (Task 5) ---

SPRITE_MATCH_SYSTEM_PROMPT = """你是一个角色外貌分析专家。根据用户给出的角色描述，提取外貌特征。

输出严格 JSON 格式:
{"gender": "male|female|neutral", "age_group": "young|adult|elder", "vibe": "一个词描述气质"}

只输出 JSON，不要输出其他内容。"""


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
