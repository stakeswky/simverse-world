import pytest
from datetime import datetime, UTC
from app.models.user import User
from app.models.forge_session import ForgeSession


@pytest.mark.anyio
async def test_forge_list_sessions(db_session):
    """Should list forge sessions with pagination and filters."""
    from app.routers.admin.forge_monitor import _list_forge_sessions

    user = User(name="forger", email="forger@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    for i in range(5):
        db_session.add(ForgeSession(
            user_id=user.id,
            character_name=f"Char {i}",
            mode="deep" if i % 2 == 0 else "quick",
            status="completed" if i < 3 else "routing",
        ))
    await db_session.commit()

    sessions, total = await _list_forge_sessions(db_session, offset=0, limit=10)
    assert total == 5
    assert len(sessions) == 5


@pytest.mark.anyio
async def test_forge_list_filter_status(db_session):
    """Should filter by status."""
    from app.routers.admin.forge_monitor import _list_forge_sessions

    user = User(name="f2", email="f2@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    db_session.add(ForgeSession(user_id=user.id, character_name="Active", mode="deep", status="routing"))
    db_session.add(ForgeSession(user_id=user.id, character_name="Done", mode="quick", status="completed"))
    await db_session.commit()

    sessions, total = await _list_forge_sessions(db_session, status="routing")
    assert total == 1
    assert sessions[0].status == "routing"


@pytest.mark.anyio
async def test_forge_session_detail(db_session):
    """Should return full session detail including JSON fields."""
    from app.routers.admin.forge_monitor import _get_forge_session

    user = User(name="f3", email="f3@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    session = ForgeSession(
        user_id=user.id,
        character_name="Detailed",
        mode="deep",
        status="completed",
        research_data={"query": "test", "results": 5},
        validation_report={"passed": True, "score": 0.95},
    )
    db_session.add(session)
    await db_session.commit()

    detail = await _get_forge_session(db_session, session.id)
    assert detail is not None
    assert detail.character_name == "Detailed"
    assert detail.research_data["results"] == 5
    assert detail.validation_report["passed"] is True
