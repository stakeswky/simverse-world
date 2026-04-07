from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.transaction import Transaction


async def get_balance(db: AsyncSession, user_id: str) -> int:
    result = await db.execute(select(User.soul_coin_balance).where(User.id == user_id))
    balance = result.scalar_one_or_none()
    return balance or 0


async def charge(db: AsyncSession, user_id: str, amount: int, reason: str) -> bool:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.soul_coin_balance < amount:
        return False
    user.soul_coin_balance -= amount
    db.add(Transaction(user_id=user_id, amount=-amount, reason=reason))
    await db.commit()
    return True


async def reward(db: AsyncSession, user_id: str, amount: int, reason: str) -> int:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return 0
    user.soul_coin_balance += amount
    db.add(Transaction(user_id=user_id, amount=amount, reason=reason))
    await db.commit()
    return user.soul_coin_balance


async def reward_creator_passive(db: AsyncSession, creator_id: str, resident_slug: str) -> dict | None:
    """
    Award 1 SC to creator when their resident gets a conversation.
    Returns notification payload if reward given, None if creator is 'system' or not found.
    """
    if creator_id == "system":
        return None

    result = await db.execute(select(User).where(User.id == creator_id))
    user = result.scalar_one_or_none()
    if not user:
        return None

    user.soul_coin_balance += 1
    db.add(Transaction(user_id=creator_id, amount=1, reason=f"creator_passive:{resident_slug}"))
    await db.commit()

    return {
        "type": "coin_earned",
        "amount": 1,
        "reason": "creator_passive",
        "resident_slug": resident_slug,
        "new_balance": user.soul_coin_balance,
    }
