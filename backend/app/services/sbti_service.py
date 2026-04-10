"""
SBTI (Silly Behavioral Type Indicator) personality calculation service.

Analyzes a resident's three-layer text (ability/persona/soul) to compute
a 15-dimension personality profile and match it to one of 27 SBTI types.
"""

import json
import re
import logging

from app.llm.client import get_client

logger = logging.getLogger(__name__)

# ── 15 Dimensions ──────────────────────────────────────────────────────
DIMENSIONS = [
    ("S1", "自尊自信"),
    ("S2", "自我清晰度"),
    ("S3", "核心价值"),
    ("E1", "依恋安全感"),
    ("E2", "情感投入度"),
    ("E3", "边界与依赖"),
    ("A1", "世界观倾向"),
    ("A2", "规则与灵活度"),
    ("A3", "人生意义感"),
    ("Ac1", "动机导向"),
    ("Ac2", "决策风格"),
    ("Ac3", "执行模式"),
    ("So1", "社交主动性"),
    ("So2", "人际边界感"),
    ("So3", "表达与真实度"),
]

DIMENSION_CODES = [d[0] for d in DIMENSIONS]

# ── 25 Normal Type Patterns ────────────────────────────────────────────
# Pattern: 15-char string of L/M/H for S1,S2,S3,E1,E2,E3,A1,A2,A3,Ac1,Ac2,Ac3,So1,So2,So3
TYPE_PATTERNS: dict[str, dict] = {
    "CTRL":   {"name": "拿捏者",   "en": "The Handler",      "pattern": "HHH-HMH-MHH-HHH-MHM"},
    "ATM-er": {"name": "送钱者",   "en": "The Walking ATM",  "pattern": "HHH-HHM-HHH-HMH-MHL"},
    "Dior-s": {"name": "屌丝",     "en": "The Cynic Sage",   "pattern": "MHM-MMH-MHM-HMH-LHL"},
    "BOSS":   {"name": "领导者",   "en": "The Boss",         "pattern": "HHH-HMH-MMH-HHH-LHL"},
    "THAN-K": {"name": "感恩者",   "en": "The Thanker",      "pattern": "MHM-HMM-HHM-MMH-MHL"},
    "OH-NO":  {"name": "哦不人",   "en": "The Alarmist",     "pattern": "HHL-LMH-LHH-HHM-LHL"},
    "GOGO":   {"name": "行者",     "en": "The Go-Goer",      "pattern": "HHM-HMH-MMH-HHH-MHM"},
    "SEXY":   {"name": "尤物",     "en": "The Heartthrob",   "pattern": "HMH-HHL-HMM-HMM-HLH"},
    "LOVE-R": {"name": "多情者",   "en": "The Lover",        "pattern": "MLH-LHL-HLH-MLM-MLH"},
    "MUM":    {"name": "妈妈",     "en": "The Mom Friend",   "pattern": "MMH-MHL-HMM-LMM-HLL"},
    "FAKE":   {"name": "伪人",     "en": "The Masker",       "pattern": "HLM-MML-MLM-MLM-HLH"},
    "OJBK":   {"name": "无所谓人", "en": "The Whatever",     "pattern": "MMH-MMM-HML-LMM-MML"},
    "MALO":   {"name": "吗喽",     "en": "The Chaos Monkey", "pattern": "MLH-MHM-MLH-MLH-LMH"},
    "JOKE-R": {"name": "小丑",     "en": "The Jester",       "pattern": "LLH-LHL-LML-LLL-MLM"},
    "WOC!":   {"name": "握草人",   "en": "The Whoa Person",  "pattern": "HHL-HMH-MMH-HHM-LHH"},
    "THIN-K": {"name": "思考者",   "en": "The Thinker",      "pattern": "HHL-HMH-MLH-MHM-LHH"},
    "SHIT":   {"name": "愤世者",   "en": "The Malcontent",   "pattern": "HHL-HLH-LMM-HHM-LHH"},
    "ZZZZ":   {"name": "装死者",   "en": "The Snoozer",      "pattern": "MHL-MLH-LML-MML-LHM"},
    "POOR":   {"name": "贫困者",   "en": "The Specialist",   "pattern": "HHL-MLH-LMH-HHH-LHL"},
    "MONK":   {"name": "僧人",     "en": "The Monk",         "pattern": "HHL-LLH-LLM-MML-LHM"},
    "IMSB":   {"name": "傻者",     "en": "The Self-Roaster", "pattern": "LLM-LMM-LLL-LLL-MLM"},
    "SOLO":   {"name": "孤儿",     "en": "The Loner",        "pattern": "LML-LLH-LHL-LML-LHM"},
    "FUCK":   {"name": "草者",     "en": "The Wild One",     "pattern": "MLL-LHL-LLM-MLL-HLH"},
    "DEAD":   {"name": "死者",     "en": "The Deadpan",      "pattern": "LLL-LLM-LML-LLL-LHM"},
    "IMFW":   {"name": "废物",     "en": "The Fragile One",  "pattern": "LLH-LHL-LML-LLL-MLL"},
}

# Special types (not in pattern matching)
SPECIAL_TYPES = {
    "HHHH":  {"name": "傻乐者", "en": "The Goofball"},
    "DRUNK": {"name": "酒鬼",   "en": "The Drunkard"},
}

LEVEL_MAP = {"L": 1, "M": 2, "H": 3}


def _parse_pattern(pattern_str: str) -> list[int]:
    """Convert 'HHH-HMH-MHH-HHH-MHM' to [3,3,3,3,2,3,2,3,3,3,3,3,2,3,2]."""
    chars = pattern_str.replace("-", "")
    return [LEVEL_MAP[c] for c in chars]


def match_type(dimensions: dict[str, str]) -> dict:
    """
    Match a 15-dimension L/M/H profile to the best SBTI type.

    dimensions: {"S1": "H", "S2": "M", ...}
    Returns: {"type": "CTRL", "type_name": "拿捏者", "similarity": 85, "exact": 12}
    """
    user_vec = [LEVEL_MAP[dimensions.get(code, "M")] for code in DIMENSION_CODES]

    best = None
    for type_code, info in TYPE_PATTERNS.items():
        type_vec = _parse_pattern(info["pattern"])
        distance = sum(abs(a - b) for a, b in zip(user_vec, type_vec))
        exact = sum(1 for a, b in zip(user_vec, type_vec) if a == b)
        similarity = max(0, round((1 - distance / 30) * 100))

        entry = {
            "type": type_code,
            "type_name": info["name"],
            "type_en": info["en"],
            "distance": distance,
            "exact": exact,
            "similarity": similarity,
        }
        if best is None or distance < best["distance"] or (
            distance == best["distance"] and exact > best["exact"]
        ):
            best = entry

    # Fallback: if similarity < 60%, assign HHHH
    if best and best["similarity"] < 60:
        best["type"] = "HHHH"
        best["type_name"] = SPECIAL_TYPES["HHHH"]["name"]
        best["type_en"] = SPECIAL_TYPES["HHHH"]["en"]

    return best


# ── LLM Analysis Prompt ───────────────────────────────────────────────

SBTI_ANALYSIS_SYSTEM = """\
你是 SBTI（Silly Behavioral Type Indicator）人格分析师。你的任务是根据一个角色/人物的三层描述文档，分析其在 15 个维度上的表现，给出 L（低）/ M（中）/ H（高）评级。

## 15 个维度说明

**自我模型（Self Model）**
- S1 自尊自信：对自己的评价是否稳定正面。H=自信稳定，M=时高时低，L=自卑脆弱
- S2 自我清晰度：是否清楚自己是什么人。H=门儿清，M=有点迷糊，L=完全不认识自己
- S3 核心价值：内心有没有坚定追求的东西。H=有明确信念驱动，M=有但不强烈，L=没什么特别在乎的

**情感模型（Emotion Model）**
- E1 依恋安全感：在关系中是否容易焦虑。H=安心信任，M=偶尔不安，L=经常焦虑担心被抛弃
- E2 情感投入度：对感情/关系的投入程度。H=容易全身心投入，M=有保留地投入，L=不太投入
- E3 边界与依赖：是否重视个人空间。H=非常重视独立空间，M=看情况，L=更偏依赖黏人

**态度模型（Attitude Model）**
- A1 世界观倾向：如何看待世界和他人。H=善意乐观，M=中立观望，L=阴暗悲观
- A2 规则与灵活度：是否遵守规则。H=守序有规则感，M=有弹性，L=叛逆打破常规
- A3 人生意义感：做事是否有方向和意义。H=有明确目标，M=时有时无，L=觉得没意义

**行动驱力模型（Action Model）**
- Ac1 动机导向：做事的驱动力。H=追求成果成长，M=看情况，L=主要是避免麻烦
- Ac2 决策风格：做决定是否果断。H=果断不犹豫，M=偶尔犹豫，L=优柔寡断
- Ac3 执行模式：计划能否落地。H=执行力强有计划，M=时好时坏，L=拖延不落地

**社交模型（Social Model）**
- So1 社交主动性：是否主动靠近他人。H=热情主动，M=弹性社交，L=被动回避
- So2 人际边界感：边界感是否强。H=边界感强不轻易亲近，M=适中，L=没什么边界感
- So3 表达与真实度：在不同场合是否表里如一。H=在不同人面前表现不一/会看场合，M=大体一致偶尔调整，L=完全表里如一

## 输出要求

只输出一个 JSON 对象，不要输出其他内容：
{"S1":"H","S2":"M","S3":"H","E1":"H","E2":"M","E3":"H","A1":"M","A2":"H","A3":"H","Ac1":"H","Ac2":"H","Ac3":"H","So1":"M","So2":"H","So3":"M"}

注意：
1. 每个维度必须是 L/M/H 三选一
2. 基于文本中的实际行为描述判断，不要猜测
3. 如果某个维度信息不足，默认给 M
4. 要综合三层文档判断，不要只看某一层
"""

SBTI_ANALYSIS_USER = """\
居民名字：{name}

=== ability.md（能力层）===
{ability_md}

=== persona.md（人格层）===
{persona_md}

=== soul.md（灵魂层）===
{soul_md}

请分析这位居民的 15 维 SBTI 人格评级。
"""


def _extract_text(response) -> str:
    """Extract text from LLM response, skipping ThinkingBlocks."""
    for block in response.content:
        if hasattr(block, "text"):
            return block.text
    return ""


async def compute_sbti(name: str, ability_md: str, persona_md: str, soul_md: str) -> dict | None:
    """
    Compute SBTI personality type for a resident using LLM analysis.

    Returns dict with keys: type, type_name, type_en, dimensions, similarity, exact
    Returns None if analysis fails.
    """
    combined_len = len(ability_md or "") + len(persona_md or "") + len(soul_md or "")
    if combined_len < 50:
        logger.info(f"SBTI skip for '{name}': text too short ({combined_len} chars)")
        return None

    try:
        client = get_client("system")
        from app.config import settings
        model = settings.effective_model

        resp = await client.messages.create(
            model=model,
            max_tokens=200,
            system=SBTI_ANALYSIS_SYSTEM,
            messages=[{
                "role": "user",
                "content": SBTI_ANALYSIS_USER.format(
                    name=name,
                    ability_md=ability_md or "（无内容）",
                    persona_md=persona_md or "（无内容）",
                    soul_md=soul_md or "（无内容）",
                ),
            }],
        )
        text = _extract_text(resp).strip()

        # Extract JSON from response
        match = re.search(r'\{[^}]+\}', text)
        if not match:
            logger.warning(f"SBTI: no JSON in LLM response for '{name}'")
            return None

        dimensions = json.loads(match.group())

        # Validate all 15 dimensions present and valid
        for code in DIMENSION_CODES:
            val = dimensions.get(code, "M")
            if val not in ("L", "M", "H"):
                val = "M"
            dimensions[code] = val

        # Match to best type
        result = match_type(dimensions)
        result["dimensions"] = dimensions

        # Remove intermediate fields
        result.pop("distance", None)

        logger.info(f"SBTI: '{name}' → {result['type']}（{result['type_name']}）"
                     f" similarity={result['similarity']}% exact={result['exact']}/15")
        return result

    except Exception as e:
        logger.error(f"SBTI computation failed for '{name}': {e}")
        return None


def update_meta_with_sbti(meta_json: dict | None, sbti: dict) -> dict:
    """Merge SBTI result into meta_json."""
    meta = dict(meta_json) if meta_json else {}
    meta["sbti"] = {
        "type": sbti["type"],
        "type_name": sbti["type_name"],
        "type_en": sbti["type_en"],
        "dimensions": sbti["dimensions"],
        "similarity": sbti["similarity"],
        "exact": sbti["exact"],
    }
    return meta
