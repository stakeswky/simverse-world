"""Admin Economy — global stats, transaction log, dynamic config."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.transaction import Transaction
from app.routers.admin.middleware import require_admin
from app.services.config_service import ConfigService
from app.schemas.admin import (
    EconomyStatsResponse,
    TransactionLogItem,
    EconomyConfigUpdate,
)

router = APIRouter(prefix="/economy", tags=["admin-economy"])


async def _get_economy_stats(db: AsyncSession) -> dict:
    """Compute global economy statistics."""
    # Total issued (sum of positive amounts)
    issued_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.amount > 0)
    )
    total_issued = issued_result.scalar() or 0

    # Total consumed (sum of negative amounts, as absolute value)
    consumed_result = await db.execute(
        select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0))
        .where(Transaction.amount < 0)
    )
    total_consumed = consumed_result.scalar() or 0

    # User stats
    user_stats = await db.execute(
        select(
            func.count(User.id),
            func.coalesce(func.avg(User.soul_coin_balance), 0),
        )
    )
    row = user_stats.one()
    total_users = row[0] or 0
    avg_balance = float(row[1] or 0)

    return {
        "total_issued": total_issued,
        "total_consumed": total_consumed,
        "net_circulation": total_issued - total_consumed,
        "total_users": total_users,
        "avg_balance": round(avg_balance, 2),
    }


async def _get_transaction_log(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 20,
    user_id: str | None = None,
    reason: str | None = None,
) -> tuple[list[Transaction], int]:
    """Get transaction log with filters and pagination."""
    query = select(Transaction)
    count_query = select(func.count(Transaction.id))

    if user_id:
        query = query.where(Transaction.user_id == user_id)
        count_query = count_query.where(Transaction.user_id == user_id)

    if reason:
        pattern = f"%{reason}%"
        query = query.where(Transaction.reason.ilike(pattern))
        count_query = count_query.where(Transaction.reason.ilike(pattern))

    query = query.order_by(Transaction.created_at.desc())
    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    transactions = list(result.scalars().all())

    return transactions, total


async def _update_economy_config(
    db: AsyncSession,
    admin_id: str,
    signup_bonus: int | None = None,
    daily_reward: int | None = None,
    chat_cost_per_turn: int | None = None,
    creator_reward: int | None = None,
    rating_bonus: int | None = None,
) -> dict:
    """Update economy parameters in dynamic config."""
    svc = ConfigService(db)
    updated = {}

    params = {
        "economy.signup_bonus": signup_bonus,
        "economy.daily_reward": daily_reward,
        "economy.chat_cost_per_turn": chat_cost_per_turn,
        "economy.creator_reward": creator_reward,
        "economy.rating_bonus": rating_bonus,
    }

    for key, value in params.items():
        if value is not None:
            await svc.set(key, value, group="economy", updated_by=admin_id)
            updated[key] = value

    return updated


# ── Routes ─────────────────────────────────────────────────

@router.get("/stats", response_model=EconomyStatsResponse)
async def economy_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Global economy statistics."""
    stats = await _get_economy_stats(db)
    return EconomyStatsResponse(**stats)


@router.get("/transactions")
async def transaction_log(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: str | None = None,
    reason: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Transaction log with filters and pagination."""
    transactions, total = await _get_transaction_log(
        db, offset=offset, limit=limit, user_id=user_id, reason=reason,
    )
    return {
        "items": [TransactionLogItem.model_validate(t, from_attributes=True) for t in transactions],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.put("/config")
async def update_economy_config(
    req: EconomyConfigUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update economy dynamic parameters."""
    updated = await _update_economy_config(
        db, admin_id=admin.id,
        signup_bonus=req.signup_bonus, daily_reward=req.daily_reward,
        chat_cost_per_turn=req.chat_cost_per_turn,
        creator_reward=req.creator_reward, rating_bonus=req.rating_bonus,
    )
    if not updated:
        raise HTTPException(status_code=400, detail="No parameters to update")
    return {"updated": updated}


@router.get("/config")
async def get_economy_config(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get current economy config values with defaults."""
    svc = ConfigService(db)
    return {
        "signup_bonus": await svc.get("economy.signup_bonus", default=100),
        "daily_reward": await svc.get("economy.daily_reward", default=5),
        "chat_cost_per_turn": await svc.get("economy.chat_cost_per_turn", default=1),
        "creator_reward": await svc.get("economy.creator_reward", default=1),
        "rating_bonus": await svc.get("economy.rating_bonus", default=2),
    }
