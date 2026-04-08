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

# ---------------------------------------------------------------------------
# ExtractionStage prompts
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# BuildStage prompts
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# ValidationStage prompts
# ---------------------------------------------------------------------------

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
