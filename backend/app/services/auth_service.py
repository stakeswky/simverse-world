import uuid
from datetime import datetime, timedelta, UTC
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.models.transaction import Transaction

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def verify_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except Exception:
        return None

async def register_user(db: AsyncSession, name: str, email: str, password: str) -> tuple[User, str]:
    user_id = str(uuid.uuid4())
    user = User(id=user_id, name=name, email=email, hashed_password=pwd_context.hash(password))
    db.add(user)
    db.add(Transaction(user_id=user_id, amount=100, reason="signup_bonus"))
    await db.commit()
    await db.refresh(user)
    return user, create_token(user.id)

async def login_user(db: AsyncSession, email: str, password: str) -> tuple[User, str] | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password or not pwd_context.verify(password, user.hashed_password):
        return None
    return user, create_token(user.id)

async def get_current_user(db: AsyncSession, token: str) -> User | None:
    user_id = verify_token(token)
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
