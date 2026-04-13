"""Tests for home_location_id assignment in creation paths."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agent.map_data import allocate_home, assign_home


def test_assign_home_empty_town():
    assert assign_home({}) == "house_a"


def test_assign_home_all_full():
    occupied = {
        "house_a": 1, "house_b": 1, "house_c": 1,
        "house_d": 1, "house_e": 1, "house_f": 1,
        "apt_star": 5, "apt_moon": 5, "apt_dawn": 5,
    }
    assert assign_home(occupied) is None


@pytest.mark.asyncio
async def test_allocate_home_returns_location_id():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [("house_a", 1)]
    mock_db.execute.return_value = mock_result
    home_id = await allocate_home(mock_db)
    assert home_id == "house_b"


@pytest.mark.asyncio
async def test_allocate_resident_location_returns_home():
    from app.services.forge_service import allocate_resident_location
    mock_db = AsyncMock()
    with patch("app.services.forge_service._find_available_tile", return_value=(75, 56)):
        with patch("app.services.forge_service.allocate_home", return_value="house_a"):
            result = await allocate_resident_location(mock_db, requested_location_id="central_plaza")
    assert len(result) == 4
    location_id, tile_x, tile_y, home_id = result
    assert location_id == "central_plaza"
    assert home_id == "house_a"


@pytest.mark.asyncio
async def test_allocate_resident_location_no_housing_when_disabled():
    from app.services.forge_service import allocate_resident_location
    mock_db = AsyncMock()
    with patch("app.services.forge_service._find_available_tile", return_value=(75, 56)):
        result = await allocate_resident_location(mock_db, requested_location_id="central_plaza", assign_housing=False)
    assert len(result) == 4
    assert result[3] is None
