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
