"""Admin User Management — list, detail, balance, ban, admin toggle."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.models.transaction import Transaction
from app.routers.admin.middleware import require_admin
from app.schemas.admin import (
    AdminUserListItem,
    AdminUserDetail,
    BalanceAdjustRequest,
    UserPatchRequest,
)

router = APIRouter(prefix="/users", tags=["admin-users"])


async def _list_users(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 20,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[User], int]:
    """List users with pagination, search, sort."""
    query = select(User)
    count_query = select(func.count(User.id))

    if search:
        pattern = f"%{search}%"
        condition = or_(User.name.ilike(pattern), User.email.ilike(pattern))
        query = query.where(condition)
        count_query = count_query.where(condition)

    # Sort
    sort_col = getattr(User, sort_by, User.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    users = list(result.scalars().all())

    return users, total


async def _get_user_detail(db: AsyncSession, user_id: str) -> dict | None:
    """Get user detail with related counts."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None

    # Count residents
    res_count = (await db.execute(
        select(func.count(Resident.id)).where(Resident.creator_id == user_id)
    )).scalar() or 0

    # Count conversations
    conv_count = (await db.execute(
        select(func.count(Conversation.id)).where(Conversation.user_id == user_id)
    )).scalar() or 0

    # Count transactions
    txn_count = (await db.execute(
        select(func.count(Transaction.id)).where(Transaction.user_id == user_id)
    )).scalar() or 0

    return {
        **{c.key: getattr(user, c.key) for c in User.__table__.columns},
        "resident_count": res_count,
        "conversation_count": conv_count,
        "transaction_count": txn_count,
    }


async def _adjust_balance(
    db: AsyncSession,
    user_id: str,
    amount: int,
    reason: str,
    admin_id: str,
) -> int:
    """Adjust user balance. Returns new balance."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    user.soul_coin_balance += amount
    db.add(Transaction(
        user_id=user_id,
        amount=amount,
        reason=f"admin_adjust:{reason} (by {admin_id})",
    ))
    await db.commit()
    return user.soul_coin_balance


async def _set_ban_status(db: AsyncSession, user_id: str, is_banned: bool) -> bool:
    """Set user ban status."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return False
    user.is_banned = is_banned
    await db.commit()
    return True


async def _set_admin_status(db: AsyncSession, user_id: str, is_admin: bool) -> bool:
    """Set user admin status."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return False
    user.is_admin = is_admin
    await db.commit()
    return True


# ── Routes ─────────────────────────────────────────────────

@router.get("")
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all users with pagination and search."""
    offset = (page - 1) * per_page
    users, total = await _list_users(db, offset=offset, limit=per_page, search=search,
                                      sort_by=sort_by, sort_order=sort_order)
    return {
        "items": [AdminUserListItem.model_validate(u, from_attributes=True) for u in users],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/{user_id}")
async def get_user_detail(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed user info including related counts."""
    detail = await _get_user_detail(db, user_id)
    if not detail:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminUserDetail(**detail)


@router.post("/{user_id}/adjust-coin")
async def adjust_balance(
    user_id: str,
    req: BalanceAdjustRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Adjust user Soul Coin balance (positive = add, negative = deduct)."""
    try:
        new_balance = await _adjust_balance(db, user_id, req.amount, req.reason, admin.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"user_id": user_id, "new_balance": new_balance}


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    req: UserPatchRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Ban/unban or toggle admin on a user. Send JSON with is_banned and/or is_admin."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot modify yourself")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.is_banned is not None:
        user.is_banned = req.is_banned
    if req.is_admin is not None:
        user.is_admin = req.is_admin
    await db.commit()

    return {"user_id": user_id, "is_banned": user.is_banned, "is_admin": user.is_admin}
