import pytest
from app.models.user import User
from app.services.coin_service import get_balance, charge, reward


@pytest.fixture
async def test_user(db_session):
    user = User(id="coin-test-user", name="CoinUser", email="coins@test.com", soul_coin_balance=100)
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.anyio
async def test_get_balance(db_session, test_user):
    balance = await get_balance(db_session, test_user.id)
    assert balance == 100


@pytest.mark.anyio
async def test_charge_deducts_balance(db_session, test_user):
    ok = await charge(db_session, test_user.id, 5, "test_charge")
    assert ok is True
    balance = await get_balance(db_session, test_user.id)
    assert balance == 95


@pytest.mark.anyio
async def test_charge_fails_if_insufficient(db_session, test_user):
    ok = await charge(db_session, test_user.id, 200, "too_much")
    assert ok is False
    balance = await get_balance(db_session, test_user.id)
    assert balance == 100  # unchanged


@pytest.mark.anyio
async def test_reward_adds_balance(db_session, test_user):
    new_balance = await reward(db_session, test_user.id, 50, "test_reward")
    assert new_balance == 150


@pytest.mark.anyio
async def test_charge_records_transaction(db_session, test_user):
    from sqlalchemy import select
    from app.models.transaction import Transaction
    await charge(db_session, test_user.id, 1, "chat:isabella")
    txns = await db_session.execute(
        select(Transaction).where(Transaction.user_id == test_user.id)
    )
    txn_list = txns.scalars().all()
    assert len(txn_list) == 1
    assert txn_list[0].amount == -1
    assert txn_list[0].reason == "chat:isabella"
