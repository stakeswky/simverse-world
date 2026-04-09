"""Admin authentication dependency. Extracts JWT, verifies user, checks is_admin."""
from fastapi import HTTPException, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth_service import get_current_user
from app.models.user import User


async def require_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency that enforces admin access.
    Returns the authenticated admin User, or raises 401/403.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth.removeprefix("Bearer ")
    user = await get_current_user(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if user.is_banned:
        raise HTTPException(status_code=403, detail="Account is banned")

    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")

    return user
