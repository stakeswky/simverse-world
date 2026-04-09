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
