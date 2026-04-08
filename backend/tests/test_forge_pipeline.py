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
