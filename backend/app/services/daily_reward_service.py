from datetime import datetime, date, UTC
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.transaction import Transaction

DAILY_REWARD_AMOUNT = 5

async def claim_daily_reward(db: AsyncSession, user_id: str) -> dict:
    """
    Claim daily login reward (5 SC). Can only be claimed once per calendar day.

    Returns:
        {"claimed": True, "amount": 5, "new_balance": N} if successful
        {"claimed": False, "reason": "already_claimed_today"} if already claimed today
        {"claimed": False, "reason": "user_not_found"} if user doesn't exist
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"claimed": False, "reason": "user_not_found"}

    now = datetime.now(UTC)
    today = now.date()

    # Check if already claimed today (compare in UTC to avoid timezone mismatch)
    if user.last_daily_reward_at is not None:
        last_dt = user.last_daily_reward_at
        # SQLite may strip timezone info — treat naive as UTC
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=UTC)
        if last_dt.date() == today:
            return {"claimed": False, "reason": "already_claimed_today"}

    # Grant reward
    user.soul_coin_balance += DAILY_REWARD_AMOUNT
    user.last_daily_reward_at = datetime.now(UTC)
    db.add(Transaction(user_id=user_id, amount=DAILY_REWARD_AMOUNT, reason="daily_login_reward"))
    await db.commit()
    await db.refresh(user)

    return {
        "claimed": True,
        "amount": DAILY_REWARD_AMOUNT,
        "new_balance": user.soul_coin_balance,
    }
