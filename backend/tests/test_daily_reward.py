import pytest
from app.models.user import User
from datetime import datetime, UTC

@pytest.fixture
async def test_user(db_session):
    user = User(id="daily-test-user", name="DailyUser",
                email="daily@test.com", soul_coin_balance=100)
    db_session.add(user)
    await db_session.commit()
    return user

@pytest.mark.anyio
async def test_user_has_last_daily_reward_field(db_session, test_user):
    assert hasattr(test_user, "last_daily_reward_at")
    assert test_user.last_daily_reward_at is None

@pytest.mark.anyio
async def test_resident_has_search_vector_field(db_session):
    from app.models.resident import Resident
    r = Resident.__table__.columns
    assert "search_vector" in [c.name for c in r]
