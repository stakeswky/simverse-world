from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.profile import MyResidentItem, MyConversationItem, MyTransactionItem
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/profile", tags=["profile"])


async def _require_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = await get_current_user(db, auth.removeprefix("Bearer "))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


@router.get("/residents", response_model=list[MyResidentItem])
async def list_my_residents(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await _require_user(request, db)
    result = await db.execute(
        select(Resident)
        .where(Resident.creator_id == user.id)
        .order_by(desc(Resident.created_at))
    )
    residents = result.scalars().all()
    return [MyResidentItem.model_validate(r, from_attributes=True) for r in residents]


@router.get("/conversations", response_model=list[MyConversationItem])
async def list_my_conversations(
    request: Request,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    user = await _require_user(request, db)
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(desc(Conversation.started_at))
        .limit(limit)
        .offset(offset)
    )
    conversations = result.scalars().all()

    items = []
    for conv in conversations:
        res_result = await db.execute(
            select(Resident.name, Resident.slug).where(Resident.id == conv.resident_id)
        )
        row = res_result.first()
        resident_name = row[0] if row else "Unknown"
        resident_slug = row[1] if row else ""
        items.append(MyConversationItem(
            id=conv.id,
            resident_id=conv.resident_id,
            resident_name=resident_name,
            resident_slug=resident_slug,
            started_at=conv.started_at,
            ended_at=conv.ended_at,
            turns=conv.turns,
            rating=conv.rating,
        ))
    return items


@router.get("/transactions", response_model=list[MyTransactionItem])
async def list_my_transactions(
    request: Request,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    user = await _require_user(request, db)
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(desc(Transaction.created_at))
        .limit(limit)
        .offset(offset)
    )
    transactions = result.scalars().all()
    return [MyTransactionItem(
        id=t.id, amount=t.amount, reason=t.reason, created_at=t.created_at
    ) for t in transactions]
