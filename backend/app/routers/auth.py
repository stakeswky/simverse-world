from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import RegisterRequest, LoginRequest, AuthResponse, UserResponse
from app.services.auth_service import register_user, login_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user, token = await register_user(db, req.name, req.email, req.password)
    return AuthResponse(access_token=token, user=UserResponse(
        id=user.id, name=user.name, email=user.email,
        avatar=user.avatar, soul_coin_balance=user.soul_coin_balance
    ))

@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await login_user(db, req.email, req.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user, token = result
    return AuthResponse(access_token=token, user=UserResponse(
        id=user.id, name=user.name, email=user.email,
        avatar=user.avatar, soul_coin_balance=user.soul_coin_balance
    ))
