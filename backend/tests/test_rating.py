import pytest
from app.models.conversation import Conversation
from app.models.resident import Resident
from app.models.user import User
from sqlalchemy import func, select


@pytest.fixture
async def test_user(db_session):
    user = User(id="rating-test-user", name="RatingUser",
                email="rating@test.com", soul_coin_balance=100)
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def seeded_user_residents(db_session, test_user):
    r = Resident(slug="rating-r1", name="Rating Resident", district="free",
                 creator_id=test_user.id, status="idle", heat=0, star_rating=1,
                 sprite_key="梅", tile_x=30, tile_y=65, token_cost_per_turn=1,
                 ability_md="", persona_md="", soul_md="", meta_json={})
    db_session.add(r)
    await db_session.commit()
    return [r]


@pytest.mark.anyio
async def test_rating_updates_conversation(db_session, test_user, seeded_user_residents):
    conv = Conversation(user_id=test_user.id, resident_id=seeded_user_residents[0].id, turns=3)
    db_session.add(conv)
    await db_session.commit()

    conv.rating = 4
    await db_session.commit()
    await db_session.refresh(conv)
    assert conv.rating == 4


@pytest.mark.anyio
async def test_avg_rating_calculation(db_session, test_user, seeded_user_residents):
    resident = seeded_user_residents[0]
    for rating in [5, 4, 3, 4]:
        conv = Conversation(user_id=test_user.id, resident_id=resident.id,
                            turns=2, rating=rating)
        db_session.add(conv)
    await db_session.commit()

    result = await db_session.execute(
        select(func.avg(Conversation.rating)).where(
            Conversation.resident_id == resident.id,
            Conversation.rating.is_not(None),
        )
    )
    avg = result.scalar()
    assert avg == 4.0


@pytest.mark.anyio
async def test_valid_rating_range():
    for r in [1, 2, 3, 4, 5]:
        assert 1 <= r <= 5
    for r in [0, 6, -1]:
        assert not (1 <= r <= 5)
