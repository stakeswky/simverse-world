"""Test PUT /residents/player/position endpoint."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_update_player_position_requires_auth():
    """Unauthenticated requests should return 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put("/residents/player/position", json={"tile_x": 10, "tile_y": 20})
    assert resp.status_code == 401