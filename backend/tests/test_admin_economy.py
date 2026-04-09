import pytest
from app.models.user import User
from app.models.transaction import Transaction


@pytest.mark.anyio
async def test_economy_global_stats(db_session):
    """Economy stats should aggregate correctly."""
    from app.routers.admin.economy import _get_economy_stats

    u1 = User(name="u1", email="u1@test.com", soul_coin_balance=150,
              is_admin=False, is_banned=False)
    u2 = User(name="u2", email="u2@test.com", soul_coin_balance=50,
              is_admin=False, is_banned=False)
    db_session.add_all([u1, u2])
    await db_session.commit()

    # Positive transactions (issued)
    db_session.add(Transaction(user_id=u1.id, amount=100, reason="signup"))
    db_session.add(Transaction(user_id=u2.id, amount=100, reason="signup"))
    db_session.add(Transaction(user_id=u1.id, amount=50, reason="daily"))
    # Negative transactions (consumed)
    db_session.add(Transaction(user_id=u2.id, amount=-50, reason="chat"))
    await db_session.commit()

    stats = await _get_economy_stats(db_session)
    assert stats["total_issued"] == 250  # 100 + 100 + 50
    assert stats["total_consumed"] == 50  # abs(-50)
    assert stats["net_circulation"] == 200  # 250 - 50
    assert stats["total_users"] == 2
    assert stats["avg_balance"] == 100.0  # (150 + 50) / 2


@pytest.mark.anyio
async def test_economy_transaction_log(db_session):
    """Transaction log should support pagination and filters."""
    from app.routers.admin.economy import _get_transaction_log

    u = User(name="txn", email="txn@test.com", is_admin=False, is_banned=False)
    db_session.add(u)
    await db_session.commit()

    for i in range(8):
        db_session.add(Transaction(
            user_id=u.id,
            amount=10 if i % 2 == 0 else -5,
            reason="signup" if i % 2 == 0 else "chat",
        ))
    await db_session.commit()

    txns, total = await _get_transaction_log(db_session, offset=0, limit=5)
    assert total == 8
    assert len(txns) == 5

    # Filter by reason
    txns2, total2 = await _get_transaction_log(db_session, reason="chat")
    assert total2 == 4


@pytest.mark.anyio
async def test_economy_config_update(db_session):
    """Economy config update should write to ConfigService."""
    from app.routers.admin.economy import _update_economy_config
    from app.services.config_service import ConfigService

    svc = ConfigService(db_session)
    await _update_economy_config(db_session, admin_id="admin-1", signup_bonus=200, daily_reward=10)

    value = await svc.get("economy.signup_bonus", default=100)
    assert value == 200

    value2 = await svc.get("economy.daily_reward", default=5)
    assert value2 == 10
