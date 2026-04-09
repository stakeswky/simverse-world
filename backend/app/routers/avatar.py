"""Avatar router: generate AI portrait from persona text."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.portrait_service import generate_portrait

router = APIRouter(prefix="/avatar", tags=["avatar"])


async def _require_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = await get_current_user(db, auth.removeprefix("Bearer "))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


class GenerateRequest(BaseModel):
    name: str
    persona_md: str = ""


class GenerateResponse(BaseModel):
    portrait_url: str | None


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI portrait from persona text. Returns the portrait URL or null on failure."""
    user = await _require_user(request, db)
    # Use user.id as the resident_id placeholder for portrait storage
    portrait_url = await generate_portrait(
        resident_id=user.id,
        name=body.name,
        persona_md=body.persona_md,
    )
    return GenerateResponse(portrait_url=portrait_url)
