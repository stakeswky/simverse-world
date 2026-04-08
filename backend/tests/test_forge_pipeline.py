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
