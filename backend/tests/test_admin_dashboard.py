import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, patch, MagicMock
from app.models.user import User
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.models.transaction import Transaction


@pytest.mark.anyio
async def test_dashboard_stats(db_session):
    """Dashboard stats should return correct aggregated counts."""
    from app.routers.admin.dashboard import _get_dashboard_stats

    now = datetime.now(UTC)

    # Users: 2 total, 1 registered today
    u1 = User(name="old_user", email="old@test.com", is_admin=False, is_banned=False,
              created_at=now - timedelta(days=5))
    u2 = User(name="new_user", email="new@test.com", is_admin=False, is_banned=False,
              created_at=now)
    db_session.add_all([u1, u2])
    await db_session.commit()

    # Transactions today: +100 signup, -5 chat
    db_session.add(Transaction(user_id=u2.id, amount=100, reason="signup_bonus", created_at=now))
    db_session.add(Transaction(user_id=u1.id, amount=-5, reason="chat_cost", created_at=now))
    await db_session.commit()

    stats = await _get_dashboard_stats(db_session)
    assert stats["today_registrations"] == 1
    assert stats["soul_coin_net_flow"] == 95  # 100 - 5


@pytest.mark.anyio
async def test_dashboard_trends(db_session):
    """Trends should return 7 data points."""
    from app.routers.admin.dashboard import _get_7day_trends

    trends = await _get_7day_trends(db_session)
    assert len(trends) == 7
    assert all("date" in t and "users" in t and "conversations" in t for t in trends)


@pytest.mark.anyio
async def test_dashboard_top_residents(db_session):
    """Top residents should be sorted by heat descending."""
    from app.routers.admin.dashboard import _get_top_residents

    u = User(name="creator", email="c@test.com", is_admin=False, is_banned=False)
    db_session.add(u)
    await db_session.commit()

    for i in range(3):
        r = Resident(slug=f"r-{i}", name=f"R{i}", creator_id=u.id, heat=i * 10)
        db_session.add(r)
    await db_session.commit()

    top = await _get_top_residents(db_session, limit=10)
    assert len(top) == 3
    assert top[0]["heat"] >= top[1]["heat"] >= top[2]["heat"]


@pytest.mark.anyio
async def test_health_check_formats():
    """Health check should return list of ServiceHealthItem-compatible dicts."""
    from app.routers.admin.dashboard import _check_service_health

    with patch("app.routers.admin.dashboard.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.elapsed = timedelta(milliseconds=50)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        results = await _check_service_health()
    assert isinstance(results, list)
    assert all("service" in r and "status" in r for r in results)
