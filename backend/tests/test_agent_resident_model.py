import pytest
from sqlalchemy import select
from app.models.resident import Resident


@pytest.mark.anyio
async def test_resident_has_home_tile_fields(db_session):
    r = Resident(
        id="agent-model-test",
        slug="agent-model-test",
        name="Wanderer",
        district="engineering",
        status="idle",
        ability_md="Can wander",
        persona_md="Curious",
        soul_md="Free",
        creator_id="creator-1",
    )
    db_session.add(r)
    await db_session.commit()

    result = await db_session.execute(select(Resident).where(Resident.id == "agent-model-test"))
    saved = result.scalar_one()
    # home_tile fields nullable, default None
    assert saved.home_tile_x is None
    assert saved.home_tile_y is None


@pytest.mark.anyio
async def test_resident_home_tile_set(db_session):
    r = Resident(
        id="agent-model-test-2",
        slug="agent-model-test-2",
        name="Homebody",
        district="free",
        status="idle",
        ability_md="Stays home",
        persona_md="Introvert",
        soul_md="Rooted",
        creator_id="creator-1",
        home_tile_x=42,
        home_tile_y=58,
    )
    db_session.add(r)
    await db_session.commit()

    result = await db_session.execute(select(Resident).where(Resident.id == "agent-model-test-2"))
    saved = result.scalar_one()
    assert saved.home_tile_x == 42
    assert saved.home_tile_y == 58


@pytest.mark.anyio
async def test_resident_status_values(db_session):
    """Status can be idle/chatting/sleeping/walking/socializing."""
    for status in ["idle", "chatting", "sleeping", "walking", "socializing"]:
        r = Resident(
            id=f"status-test-{status}",
            slug=f"status-test-{status}",
            name=f"Res {status}",
            district="free",
            status=status,
            ability_md="x",
            persona_md="x",
            soul_md="x",
            creator_id="creator-1",
        )
        db_session.add(r)
    await db_session.commit()

    result = await db_session.execute(
        select(Resident).where(Resident.id.like("status-test-%"))
    )
    rows = result.scalars().all()
    statuses = {r.status for r in rows}
    assert statuses == {"idle", "chatting", "sleeping", "walking", "socializing"}
