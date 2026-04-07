import pytest
from datetime import datetime, timedelta
from app.models.resident import Resident
from app.models.user import User
from app.models.conversation import Conversation
from app.services.heat_service import recalculate_heat, POPULAR_THRESHOLD, SLEEPING_DAYS


@pytest.fixture
async def test_resident(db_session):
    user = User(id="heat-creator", name="HeatCreator", email="heat@test.com", soul_coin_balance=0)
    db_session.add(user)
    await db_session.flush()
    r = Resident(
        slug="heat-test-r", name="热度测试居民", district="free", creator_id="heat-creator",
        status="idle", heat=0, star_rating=1, sprite_key="梅",
        tile_x=30, tile_y=65, token_cost_per_turn=1,
        ability_md="", persona_md="", soul_md="", meta_json={},
    )
    db_session.add(r)
    await db_session.commit()
    return r


@pytest.fixture
def make_conversations(db_session):
    async def _make(resident_id: str, count: int, days_ago: int = 1):
        ts = datetime.utcnow() - timedelta(days=days_ago)
        for _ in range(count):
            db_session.add(Conversation(
                user_id="heat-creator", resident_id=resident_id,
                started_at=ts, turns=1,
            ))
        await db_session.commit()
    return _make


@pytest.mark.anyio
async def test_heat_calculation(db_session, test_resident, make_conversations):
    await make_conversations(test_resident.id, count=10, days_ago=3)
    await make_conversations(test_resident.id, count=5, days_ago=10)  # outside 7-day window
    await recalculate_heat(db_session)
    await db_session.refresh(test_resident)
    assert test_resident.heat == 10


@pytest.mark.anyio
async def test_transitions_to_popular(db_session, test_resident, make_conversations):
    await make_conversations(test_resident.id, count=55, days_ago=2)
    changes = await recalculate_heat(db_session)
    await db_session.refresh(test_resident)
    assert test_resident.status == "popular"
    assert any(c["slug"] == test_resident.slug and c["new_status"] == "popular" for c in changes)


@pytest.mark.anyio
async def test_transitions_to_sleeping(db_session, test_resident):
    test_resident.last_conversation_at = datetime.utcnow() - timedelta(days=8)
    test_resident.status = "idle"
    await db_session.commit()
    changes = await recalculate_heat(db_session)
    await db_session.refresh(test_resident)
    assert test_resident.status == "sleeping"
    assert test_resident.heat == 0


@pytest.mark.anyio
async def test_popular_drops_to_idle(db_session, test_resident, make_conversations):
    test_resident.status = "popular"
    await db_session.commit()
    await make_conversations(test_resident.id, count=5, days_ago=2)
    await recalculate_heat(db_session)
    await db_session.refresh(test_resident)
    assert test_resident.status == "idle"
    assert test_resident.heat == 5


@pytest.mark.anyio
async def test_chatting_skipped(db_session, test_resident):
    test_resident.status = "chatting"
    test_resident.last_conversation_at = datetime.utcnow() - timedelta(days=8)
    await db_session.commit()
    await recalculate_heat(db_session)
    await db_session.refresh(test_resident)
    assert test_resident.status == "chatting"
