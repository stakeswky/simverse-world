import pytest
from datetime import datetime, UTC
from app.models.user import User
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.models.transaction import Transaction


@pytest.mark.anyio
async def test_admin_list_users_pagination(db_session):
    """User list should support offset/limit pagination."""
    from app.routers.admin.users import _list_users

    for i in range(15):
        db_session.add(User(
            name=f"user{i}", email=f"u{i}@test.com",
            is_admin=False, is_banned=False,
        ))
    await db_session.commit()

    users, total = await _list_users(db_session, offset=0, limit=10)
    assert len(users) == 10
    assert total == 15

    users2, _ = await _list_users(db_session, offset=10, limit=10)
    assert len(users2) == 5


@pytest.mark.anyio
async def test_admin_list_users_search(db_session):
    """User list should support search by name or email."""
    from app.routers.admin.users import _list_users

    db_session.add(User(name="Alice", email="alice@test.com", is_admin=False, is_banned=False))
    db_session.add(User(name="Bob", email="bob@test.com", is_admin=False, is_banned=False))
    await db_session.commit()

    users, total = await _list_users(db_session, search="alice")
    assert total == 1
    assert users[0].name == "Alice"


@pytest.mark.anyio
async def test_admin_get_user_detail(db_session):
    """User detail should include counts of residents, conversations, transactions."""
    from app.routers.admin.users import _get_user_detail

    user = User(name="detail_user", email="detail@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    r = Resident(slug="test-r", name="R", creator_id=user.id)
    db_session.add(r)
    db_session.add(Transaction(user_id=user.id, amount=100, reason="signup"))
    await db_session.commit()

    detail = await _get_user_detail(db_session, user.id)
    assert detail is not None
    assert detail["resident_count"] == 1
    assert detail["transaction_count"] == 1


@pytest.mark.anyio
async def test_admin_adjust_balance(db_session):
    """Balance adjustment should update user balance and create transaction."""
    from app.routers.admin.users import _adjust_balance

    user = User(name="rich", email="rich@test.com", soul_coin_balance=100,
                is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    new_balance = await _adjust_balance(db_session, user.id, amount=50, reason="bonus", admin_id="admin-1")
    assert new_balance == 150

    new_balance2 = await _adjust_balance(db_session, user.id, amount=-30, reason="penalty", admin_id="admin-1")
    assert new_balance2 == 120


@pytest.mark.anyio
async def test_admin_ban_unban(db_session):
    """Ban/unban should toggle is_banned."""
    from app.routers.admin.users import _set_ban_status

    user = User(name="target", email="target@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    result = await _set_ban_status(db_session, user.id, is_banned=True)
    assert result is True

    await db_session.refresh(user)
    assert user.is_banned is True

    result2 = await _set_ban_status(db_session, user.id, is_banned=False)
    assert result2 is True

    await db_session.refresh(user)
    assert user.is_banned is False


@pytest.mark.anyio
async def test_admin_set_admin(db_session):
    """Set admin should toggle is_admin."""
    from app.routers.admin.users import _set_admin_status

    user = User(name="promote", email="promote@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    result = await _set_admin_status(db_session, user.id, is_admin=True)
    assert result is True

    await db_session.refresh(user)
    assert user.is_admin is True
