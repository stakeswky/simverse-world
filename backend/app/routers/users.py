from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import UserResponse
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserResponse)
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401)
    user = await get_current_user(db, auth.removeprefix("Bearer "))
    if not user:
        raise HTTPException(status_code=401)
    return UserResponse(
        id=user.id, name=user.name, email=user.email,
        avatar=user.avatar, soul_coin_balance=user.soul_coin_balance
    )
