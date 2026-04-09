"""Admin Forge Monitor — session list, detail, SearXNG health."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.database import get_db
from app.models.user import User
from app.models.forge_session import ForgeSession
from app.routers.admin.middleware import require_admin
from app.schemas.admin import ForgeSessionListItem, ForgeSessionDetail, ServiceHealthItem

router = APIRouter(prefix="/forge", tags=["admin-forge"])


async def _list_forge_sessions(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 20,
    status: str | None = None,
    mode: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[ForgeSession], int]:
    """List forge sessions with pagination and filters."""
    query = select(ForgeSession)
    count_query = select(func.count(ForgeSession.id))

    if status:
        query = query.where(ForgeSession.status == status)
        count_query = count_query.where(ForgeSession.status == status)

    if mode:
        query = query.where(ForgeSession.mode == mode)
        count_query = count_query.where(ForgeSession.mode == mode)

    sort_col = getattr(ForgeSession, sort_by, ForgeSession.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    sessions = list(result.scalars().all())

    return sessions, total


async def _get_forge_session(db: AsyncSession, session_id: str) -> ForgeSession | None:
    """Get a single forge session by ID."""
    result = await db.execute(
        select(ForgeSession).where(ForgeSession.id == session_id)
    )
    return result.scalar_one_or_none()


# ── Routes ─────────────────────────────────────────────────

@router.get("")
async def list_forge_sessions(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = None,
    mode: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all forge sessions with filters."""
    sessions, total = await _list_forge_sessions(
        db, offset=offset, limit=limit, status=status, mode=mode,
        sort_by=sort_by, sort_order=sort_order,
    )
    return {
        "items": [ForgeSessionListItem.model_validate(s, from_attributes=True) for s in sessions],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/active")
async def list_active_forge_sessions(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List currently active (non-completed, non-error) forge sessions."""
    result = await db.execute(
        select(ForgeSession)
        .where(ForgeSession.status.notin_(["completed", "error"]))
        .order_by(ForgeSession.updated_at.desc())
    )
    sessions = result.scalars().all()
    return [ForgeSessionListItem.model_validate(s, from_attributes=True) for s in sessions]


@router.get("/searxng-health", response_model=ServiceHealthItem)
async def searxng_health(
    admin: User = Depends(require_admin),
):
    """Dedicated SearXNG health check with extended diagnostics."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("http://localhost:8888/healthz")
            latency = int(resp.elapsed.total_seconds() * 1000)
            if resp.status_code == 200:
                return ServiceHealthItem(service="searxng", status="ok", latency_ms=latency)
            return ServiceHealthItem(
                service="searxng", status="error", latency_ms=latency,
                detail=f"HTTP {resp.status_code}",
            )
    except httpx.TimeoutException:
        return ServiceHealthItem(service="searxng", status="timeout", detail="Connection timed out")
    except Exception as e:
        return ServiceHealthItem(service="searxng", status="error", detail=str(e))


@router.get("/{session_id}")
async def get_forge_session_detail(
    session_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get full forge session detail including all JSON data."""
    session = await _get_forge_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Forge session not found")
    return ForgeSessionDetail.model_validate(session, from_attributes=True)
