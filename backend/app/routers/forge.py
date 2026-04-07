"""Forge API — 3 endpoints for the Skill creation pipeline."""

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.schemas.forge import (
    ForgeStartRequest, ForgeStartResponse,
    ForgeAnswerRequest, ForgeAnswerResponse,
    ForgeStatusResponse,
)
from app.services.auth_service import get_current_user
from app.services.forge_service import (
    start_forge, submit_answer, get_status, run_generation_pipeline,
)

router = APIRouter(prefix="/forge", tags=["forge"])


async def _require_auth(request: Request, db: AsyncSession = Depends(get_db)):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth token")
    user = await get_current_user(db, auth.removeprefix("Bearer "))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid auth token")
    return user


@router.post("/start", response_model=ForgeStartResponse)
async def forge_start(
    req: ForgeStartRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await _require_auth(request, db)
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    if len(req.name) > 100:
        raise HTTPException(status_code=400, detail="Name too long (max 100 chars)")
    result = start_forge(user.id, req.name.strip())
    return ForgeStartResponse(**result)


@router.post("/answer", response_model=ForgeAnswerResponse)
async def forge_answer(
    req: ForgeAnswerRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    user = await _require_auth(request, db)
    if not req.answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty")
    try:
        result = submit_answer(req.forge_id, req.answer.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Trigger LLM generation in background after final answer
    if result["next_step"] is None:
        async def _run_pipeline():
            async with async_session() as session:
                await run_generation_pipeline(req.forge_id, session)
        background_tasks.add_task(_run_pipeline)

    return ForgeAnswerResponse(**result)


@router.get("/status/{forge_id}", response_model=ForgeStatusResponse)
async def forge_status(
    forge_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await _require_auth(request, db)
    try:
        result = get_status(forge_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ForgeStatusResponse(**result)
