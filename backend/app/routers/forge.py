"""Forge API — endpoints for the Skill creation pipeline (quick + deep)."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.schemas.forge import (
    ForgeStartRequest, ForgeStartResponse,
    ForgeAnswerRequest, ForgeAnswerResponse,
    ForgeStatusResponse,
    DeepStartRequest, DeepStartResponse, DeepStatusResponse,
)
from app.services.auth_service import get_current_user
from app.services.forge_service import (
    start_forge, submit_answer, get_status, run_generation_pipeline,
    run_quick_pipeline,
)
from app.forge.pipeline import ForgePipeline
from app.llm.client import get_client as get_llm_client
from app.models.forge_session import ForgeSession

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
        import asyncio

        async def _run_pipeline():
            async with async_session() as session:
                await run_generation_pipeline(req.forge_id, session)

        asyncio.create_task(_run_pipeline())

    return ForgeAnswerResponse(**result)


from pydantic import BaseModel

class QuickForgeRequest(BaseModel):
    name: str
    raw_text: str   # free-form text about the person — biography, chat logs, descriptions, etc.


@router.post("/quick")
async def forge_quick(
    req: QuickForgeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    One-shot forge: provide a name + raw text, the system extracts all three layers.
    Runs synchronously (blocks until LLM responds) — typically 20-60s.
    """
    user = await _require_auth(request, db)
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    if not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    forge_id_data = start_forge(user.id, req.name.strip())
    forge_id = forge_id_data["forge_id"]

    from app.services.forge_service import _sessions
    forge_session = _sessions[forge_id]
    forge_session["answers"]["2"] = req.raw_text
    forge_session["step"] = 5
    forge_session["status"] = "generating"

    # Use starlette Response + background to ensure task runs after response
    from starlette.responses import JSONResponse
    from starlette.background import BackgroundTask
    import logging

    async def _run():
        logging.warning(f"[FORGE] Background task STARTED for {forge_id}")
        try:
            async with async_session() as db_sess:
                await run_quick_pipeline(forge_id, db_sess)
            logging.warning(f"[FORGE] Background task COMPLETED for {forge_id}")
        except Exception as e:
            logging.error(f"[FORGE] Background task FAILED: {e}")
            forge_session["status"] = "error"
            forge_session["error"] = str(e)

    return JSONResponse(
        content={"forge_id": forge_id, "status": "generating"},
        background=BackgroundTask(_run),
    )


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


# ── Deep forge (pipeline) endpoints ──────────────────────────────────


async def _run_pipeline_bg(session_id: str):
    """Background task: run forge pipeline with its own DB session."""
    async with async_session() as bg_db:
        system_client = get_llm_client("system")
        user_client = get_llm_client("user")
        pipeline = ForgePipeline(
            db=bg_db, system_client=system_client, user_client=user_client,
        )
        await pipeline.run_to_completion(session_id)


@router.post("/deep-start", response_model=DeepStartResponse)
async def deep_start(
    req: DeepStartRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Start a deep-forge pipeline session (routes to quick or deep automatically)."""
    user = await _require_auth(request, db)
    if not req.character_name.strip():
        raise HTTPException(status_code=400, detail="character_name is required")

    system_client = get_llm_client("system")
    user_client = get_llm_client("user")

    pipeline = ForgePipeline(
        db=db, system_client=system_client, user_client=user_client,
    )
    session = await pipeline.start(
        user_id=user.id,
        character_name=req.character_name.strip(),
        raw_text=req.raw_text,
        user_material=req.user_material,
    )

    # Launch the remainder of the pipeline in a background task
    asyncio.create_task(_run_pipeline_bg(session.id))

    return DeepStartResponse(
        forge_id=session.id,
        mode=session.mode,
        status=session.status,
    )


@router.get("/deep-status/{forge_id}", response_model=DeepStatusResponse)
async def deep_status(
    forge_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Check the status of a deep-forge pipeline session."""
    await _require_auth(request, db)

    result = await db.execute(
        select(ForgeSession).where(ForgeSession.id == forge_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Forge session not found")

    return DeepStatusResponse(
        forge_id=session.id,
        status=session.status,
        current_stage=session.current_stage,
        mode=session.mode,
        character_name=session.character_name,
    )
