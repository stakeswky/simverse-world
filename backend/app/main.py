import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import auth, users, residents, forge, profile, search, bulletin, onboarding, sprites, avatar, settings as settings_router, media as media_router, events as events_router, notifications as notifications_router, achievements as achievements_router, shop as shop_router, digest as digest_router, daily as daily_router, commissions as commissions_router, graph as graph_router, exploration as exploration_router, capsules as capsules_router, feed as feed_router, photos as photos_router, tts as tts_router, seasons as seasons_router, goals as goals_router, debates as debates_router, polls as polls_router, home_decor as home_decor_router, caravans as caravans_router, markets as markets_router
from app.routers import lab as lab_router
from app.routers import world as world_router
from app.routers import townhall as townhall_router
from app.routers import agent_players as agent_players_router
from app.routers import challenge as challenge_router
from app.routers import living_loop as living_loop_router
from app.routers import product_events as product_events_router
# Import the modules whose @on(...) handlers must register on the event bus.
import app.events.achievements  # noqa: F401
import app.services.daily_quest_service  # noqa: F401
import app.services.commission_service  # noqa: F401
import app.services.season_scorer  # noqa: F401
import app.services.lab_task_service  # noqa: F401  (lab_task_completed handler)
import app.services.proposal_service  # noqa: F401  (world_proposal_applied handler)
from app.routers.admin import router as admin_router
from app.ws.handlers import websocket_handler
from app.tasks.heat_cron import heat_cron_loop
from app.tasks.event_cron import event_cron_loop
from app.tasks.nightly_cron import nightly_cron_loop
from app.tasks.embedding_backfill import embedding_backfill_loop
from app.tasks.economy_cron import economy_cron_loop
from app.tasks.caravan_lifecycle import caravan_lifecycle_loop
from app.tasks.resident_sprite_worker import resident_sprite_worker_loop
from app.agent.loop import agent_loop
from app.http import close_client
from app.redis_client import close_redis
from app.ws.manager import manager
from app.services.player_npc_chat_service import run_agent_npc_chat_reaper
from app.observability import init_sentry, wire_runtime_gauges

logger = logging.getLogger(__name__)

# Upper bound for waiting on cancelled background tasks during lifespan
# teardown. Module-level so tests can monkeypatch it down.
_SHUTDOWN_TIMEOUT = 10.0

# Sentry must initialise before the app object so its FastAPI/Starlette
# integration can wrap request handling. No-op without SENTRY_DSN.
init_sentry("api")


@asynccontextmanager
async def lifespan(app):
    # Auto-create tables — dev convenience only, off by default (P0-6).
    # Production schema is managed exclusively by Alembic migrations.
    if settings.auto_create_tables:
        from app.database import engine, Base
        # Import all models so Base.metadata knows about them
        import app.models  # noqa: F401
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Seed achievement definitions (idempotent) so GET /achievements + the
        # ops-editable table are populated in dev. Fail-open: a seed hiccup must
        # never block startup.
        try:
            from app.database import async_session
            from app.events.achievements import seed_achievements
            from app.services.shop_service import seed_items
            async with async_session() as _db:
                await seed_achievements(_db)
                await seed_items(_db)
        except Exception:
            logger.warning("achievement/item seed skipped", exc_info=True)

    # WS pub/sub subscriber (P0-3b): every API worker relays broadcast/direct
    # envelopes from Redis to its own local sockets. Runs regardless of
    # run_background_tasks — this process owns live WebSocket clients even when
    # the agent loops live in the standalone worker.
    subscriber_task = asyncio.create_task(manager.run_subscriber())
    agent_presence_task = asyncio.create_task(manager.run_agent_presence_reaper())
    agent_npc_chat_task = asyncio.create_task(run_agent_npc_chat_reaper())

    # S5: the location-visit consumer runs on every API worker (move messages
    # arrive on the worker that owns the user's socket), independent of
    # run_background_tasks. DB writes happen off the move hot path here.
    from app.services.location_tracker import location_consumer_loop
    location_task = asyncio.create_task(location_consumer_loop())

    # P3: world-overlay — merge active dynamic locations at startup, then
    # subscribe to sv:world:reload so an applied/reverted proposal takes effect
    # across processes without a redeploy. Runs on every API worker.
    from app.lab.apply import reload_world, world_reload_subscriber
    try:
        await reload_world()
    except Exception:
        logger.warning("initial world overlay load skipped", exc_info=True)
    world_reload_task = asyncio.create_task(world_reload_subscriber())

    # Background loops run in-process only in single-process mode (P0-3):
    # with RUN_BACKGROUND_TASKS=false they are owned by the standalone
    # agent-worker process (python -m app.agent.main).
    background_tasks: list[asyncio.Task] = []
    if settings.run_background_tasks:
        background_tasks = [
            asyncio.create_task(heat_cron_loop()),
            asyncio.create_task(event_cron_loop()),
            asyncio.create_task(nightly_cron_loop()),
            asyncio.create_task(agent_loop.run()),
            asyncio.create_task(embedding_backfill_loop()),
            asyncio.create_task(caravan_lifecycle_loop()),
            asyncio.create_task(economy_cron_loop()),
        ]
        if settings.resident_sprite_enabled:
            background_tasks.append(asyncio.create_task(resident_sprite_worker_loop()))
        logger.info("Background loops started in-process (run_background_tasks=true)")
    else:
        logger.info(
            "run_background_tasks=false — background loops are delegated "
            "to the agent-worker process"
        )
    yield
    all_tasks = [
        subscriber_task,
        agent_presence_task,
        agent_npc_chat_task,
        location_task,
        world_reload_task,
        *background_tasks,
    ]
    for task in all_tasks:
        task.cancel()
    # Bounded wait for the cancelled tasks to actually finish their cleanup
    # BEFORE tearing down the shared HTTP/Redis clients they may still touch.
    # asyncio.wait (not wait_for(gather(...))) because a task that swallows
    # cancellation would make a cancelled gather wait on it forever; wait()
    # returns after the timeout regardless, keeping shutdown bounded.
    done, pending = await asyncio.wait(all_tasks, timeout=_SHUTDOWN_TIMEOUT)
    if pending:
        logger.warning(
            "lifespan teardown timed out after %.1fs; %d task(s) still pending: %s",
            _SHUTDOWN_TIMEOUT,
            len(pending),
            sorted(t.get_name() for t in pending),
        )
    for task in done:
        # Retrieve exceptions so the loop doesn't log
        # "Task exception was never retrieved" at GC time.
        if not task.cancelled() and task.exception() is not None:
            logger.warning("background task ended with error", exc_info=task.exception())
    await close_client()
    await close_redis()


app = FastAPI(title="Simverse World API", lifespan=lifespan)

# --- Static files (P1 fix: uploaded media & AI portraits 404'd in prod) ---
# Serves /static/* (portraits, uploads) from settings.static_dir. The media
# service and portrait service both write beneath this root; mounting here is
# what makes their returned /static/... URLs actually resolvable.
from pathlib import Path as _Path  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_static_root = _Path(settings.static_dir)
for _sub in ("uploads", "portraits"):
    (_static_root / _sub).mkdir(parents=True, exist_ok=True)
if not _Path(settings.media_upload_dir).resolve().is_relative_to(_static_root.resolve()):
    logger.warning(
        "MEDIA_UPLOAD_DIR (%s) is outside STATIC_DIR (%s) — uploaded media "
        "URLs will 404. Fix the deployment env.",
        settings.media_upload_dir, settings.static_dir,
    )
app.mount("/static", StaticFiles(directory=str(_static_root)), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Multipart parsing happens before the residents route body runs.  Bound the
# wire body at the ASGI receive layer as well as bounding the extracted file,
# covering chunked requests and dishonest/missing Content-Length headers.
from app.http_body_limit import RouteBodyLimitMiddleware  # noqa: E402
from app.services.skill_import_service import IMPORT_MAX_MULTIPART_BODY_BYTES  # noqa: E402

app.add_middleware(
    RouteBodyLimitMiddleware,
    limits={("POST", "/residents/import"): IMPORT_MAX_MULTIPART_BODY_BYTES},
    detail="Import request exceeds the multipart body size limit",
)

from app.routers.admin.hosted_agents import (  # noqa: E402
    MAX_HOSTED_AGENT_CREATE_BODY_BYTES,
)

app.add_middleware(
    RouteBodyLimitMiddleware,
    limits={
        ("POST", "/admin/hosted-agents"): MAX_HOSTED_AGENT_CREATE_BODY_BYTES,
    },
    prefix_limits={
        ("PATCH", "/admin/hosted-agents/"): MAX_HOSTED_AGENT_CREATE_BODY_BYTES,
    },
    detail="Hosted Agent request exceeds the body size limit",
)

from app.routers.product_events import PRODUCT_EVENTS_MAX_BODY_BYTES  # noqa: E402

app.add_middleware(
    RouteBodyLimitMiddleware,
    limits={
        ("POST", "/product-events/batch"): PRODUCT_EVENTS_MAX_BODY_BYTES,
    },
    detail="Product Event request exceeds the body size limit",
)

# --- REST rate limiting (OPTIMIZATION_PLAN P1-1, limit sub-item) ---
# The Limiter instance lives in app.rate_limit so routers can import the
# decorator without a circular dependency on this module. Here we only wire
# it into the app + register the 429 handler.
from app.rate_limit import limiter as _rest_limiter  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

app.state.limiter = _rest_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(residents.router)
app.include_router(home_decor_router.router)
app.include_router(forge.router)
app.include_router(profile.router)
app.include_router(profile.creator_router)  # D4: GET /creator/stats
app.include_router(search.router)
app.include_router(bulletin.router)
app.include_router(onboarding.router)
app.include_router(sprites.router)
app.include_router(avatar.router)
app.include_router(settings_router.router)
app.include_router(media_router.router)
app.include_router(events_router.router)
app.include_router(caravans_router.router)
app.include_router(markets_router.router)
app.include_router(notifications_router.router)
app.include_router(achievements_router.router)
app.include_router(shop_router.router)
app.include_router(digest_router.router)
app.include_router(daily_router.router)
app.include_router(commissions_router.router)
app.include_router(graph_router.router)
app.include_router(exploration_router.router)
app.include_router(capsules_router.router)
app.include_router(feed_router.router)
app.include_router(photos_router.router)
app.include_router(tts_router.router)
app.include_router(seasons_router.router)
app.include_router(goals_router.router)
app.include_router(debates_router.router)
app.include_router(polls_router.router)
app.include_router(lab_router.router)
app.include_router(world_router.router)
app.include_router(townhall_router.router)
app.include_router(townhall_router.alias_router)  # 收口: /town/{treasury,policies} 别名
app.include_router(agent_players_router.router)
app.include_router(challenge_router.router)
app.include_router(living_loop_router.router)
app.include_router(product_events_router.router)
app.include_router(admin_router)

# --- Observability (Phase 3): GET /metrics + runtime gauges ---
# Instrumentator adds per-handler HTTP latency/count metrics; our own domain
# metrics (LLM latency/failures, tick duration, WS online, pool usage) live in
# app.observability and are fed from their respective chokepoints.
if settings.metrics_enabled:
    from prometheus_fastapi_instrumentator import Instrumentator  # noqa: E402

    Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(
        app, include_in_schema=False
    )
    wire_runtime_gauges()

    # /metrics is publicly reachable through the CF tunnel; when METRICS_TOKEN
    # is set, require `Authorization: Bearer <token>` (Prometheus scrape_config
    # supports bearer_token). Empty token = open (dev). Token is read per
    # request so tests/ops can flip it without a restart.
    @app.middleware("http")
    async def _metrics_auth(request, call_next):  # noqa: ANN001
        if settings.metrics_token and request.url.path == "/metrics":
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {settings.metrics_token}":
                from fastapi.responses import PlainTextResponse
                return PlainTextResponse("unauthorized", status_code=401)
        return await call_next(request)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/loops")
async def health_loops():
    """Read-only liveness view of the background loops (P2, Roadmap #5).

    The background loops above run in a single process; heartbeats live in Redis, so
    this answers correctly from any API worker even when the loops are owned by
    the standalone agent-worker. ``degraded`` = at least one loop's heartbeat
    expired (a loop that never beat at all is ``never_seen``, not an outage).
    """
    from app.tasks.loop_heartbeat import heartbeats_enabled, snapshot

    loops = await snapshot()
    stale = sorted(n for n, i in loops.items() if i["state"] == "stale")
    return {
        "status": "degraded" if stale else "ok",
        "enabled": heartbeats_enabled(),
        "stale": stale,
        "loops": loops,
    }
