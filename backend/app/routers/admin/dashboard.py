"""Admin Dashboard — real-time stats, 7-day trends, top residents, health checks."""
from datetime import datetime, timedelta, UTC
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.database import get_db
from app.models.user import User
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.models.transaction import Transaction
from app.routers.admin.middleware import require_admin
from app.schemas.admin import (
    DashboardStatsResponse,
    DashboardTrendPoint,
    TopResidentItem,
    ServiceHealthItem,
)
from app.config import settings

router = APIRouter(prefix="/dashboard", tags=["admin-dashboard"])


async def _get_dashboard_stats(db: AsyncSession) -> dict:
    """Compute dashboard metric cards."""
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Today's registrations
    reg_result = await db.execute(
        select(func.count(User.id)).where(User.created_at >= today_start)
    )
    today_registrations = reg_result.scalar() or 0

    # Active chats (conversations with no ended_at)
    chat_result = await db.execute(
        select(func.count(Conversation.id)).where(Conversation.ended_at.is_(None))
    )
    active_chats = chat_result.scalar() or 0

    # Soul Coin net flow today (sum of all transaction amounts today)
    flow_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.created_at >= today_start)
    )
    soul_coin_net_flow = flow_result.scalar() or 0

    # Online users: approximate as users with activity in last 15 min
    # MVP: count users with conversations started in last 15 min
    fifteen_min_ago = now - timedelta(minutes=15)
    online_result = await db.execute(
        select(func.count(func.distinct(Conversation.user_id)))
        .where(Conversation.started_at >= fifteen_min_ago)
    )
    online_users = online_result.scalar() or 0

    return {
        "online_users": online_users,
        "today_registrations": today_registrations,
        "active_chats": active_chats,
        "soul_coin_net_flow": soul_coin_net_flow,
    }


async def _get_7day_trends(db: AsyncSession) -> list[dict]:
    """Return 7-day daily user registration and conversation counts."""
    now = datetime.now(UTC)
    trends = []

    for days_ago in range(6, -1, -1):
        day = (now - timedelta(days=days_ago)).date()
        day_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)

        # User registrations that day
        user_result = await db.execute(
            select(func.count(User.id))
            .where(User.created_at >= day_start, User.created_at < day_end)
        )
        user_count = user_result.scalar() or 0

        # Conversations started that day
        conv_result = await db.execute(
            select(func.count(Conversation.id))
            .where(Conversation.started_at >= day_start, Conversation.started_at < day_end)
        )
        conv_count = conv_result.scalar() or 0

        trends.append({
            "date": day.isoformat(),
            "users": user_count,
            "conversations": conv_count,
        })

    return trends


async def _get_top_residents(db: AsyncSession, limit: int = 10) -> list[dict]:
    """Return top N residents by heat."""
    result = await db.execute(
        select(Resident)
        .order_by(Resident.heat.desc())
        .limit(limit)
    )
    residents = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "slug": r.slug,
            "heat": r.heat,
            "district": r.district,
            "star_rating": r.star_rating,
        }
        for r in residents
    ]


SEARXNG_URL = "http://100.93.72.102:58080"


async def _check_service_health() -> list[dict]:
    """Ping external services and return health status."""
    results = []

    async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
        # SearXNG — do a real search query to verify it's functional
        try:
            resp = await client.get(
                f"{SEARXNG_URL}/search",
                params={"q": "ping", "format": "json"},
            )
            latency = int(resp.elapsed.total_seconds() * 1000)
            ok = resp.status_code == 200
            results.append({
                "service": "searxng",
                "status": "ok" if ok else "error",
                "latency_ms": latency,
                "detail": None if ok else f"HTTP {resp.status_code}",
            })
        except httpx.TimeoutException:
            results.append({"service": "searxng", "status": "timeout", "latency_ms": None, "detail": "Connection timed out"})
        except Exception as e:
            results.append({"service": "searxng", "status": "error", "latency_ms": None, "detail": str(e)})

        # LLM API — just check if the base URL is reachable (any HTTP response = reachable)
        llm_url = settings.llm_base_url or "https://api.anthropic.com"
        try:
            resp = await client.get(llm_url.rstrip("/"))
            latency = int(resp.elapsed.total_seconds() * 1000)
            # Any HTTP response means the host is reachable
            results.append({
                "service": "llm_api",
                "status": "ok",
                "latency_ms": latency,
                "detail": None,
            })
        except httpx.TimeoutException:
            results.append({"service": "llm_api", "status": "timeout", "latency_ms": None, "detail": "Connection timed out"})
        except Exception as e:
            results.append({"service": "llm_api", "status": "error", "latency_ms": None, "detail": str(e) or f"{type(e).__name__}"})

    return results


@router.get("/stats", response_model=DashboardStatsResponse)
async def dashboard_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Real-time dashboard metric cards."""
    stats = await _get_dashboard_stats(db)
    return DashboardStatsResponse(**stats)


@router.get("/trends", response_model=list[DashboardTrendPoint])
async def dashboard_trends(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """7-day user registration and conversation trends."""
    trends = await _get_7day_trends(db)
    return [DashboardTrendPoint(**t) for t in trends]


@router.get("/top-residents", response_model=list[TopResidentItem])
async def dashboard_top_residents(
    limit: int = 10,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Top N residents by heat."""
    top = await _get_top_residents(db, limit=min(limit, 50))
    return [TopResidentItem(**r) for r in top]


@router.get("/health", response_model=list[ServiceHealthItem])
async def dashboard_health(
    admin: User = Depends(require_admin),
):
    """Ping SearXNG and LLM API health."""
    results = await _check_service_health()
    return [ServiceHealthItem(**r) for r in results]
