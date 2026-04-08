import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.sprite_service import (
    SPRITE_TEMPLATES,
    get_all_templates,
    match_sprite_by_attributes,
    match_sprite_by_persona,
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


# --- LLM-based sprite matching tests (Task 5) ---


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
