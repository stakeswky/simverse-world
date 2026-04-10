import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import auth, users, residents, forge, profile, search, bulletin, onboarding, sprites, avatar, settings as settings_router, media as media_router
from app.routers.admin import router as admin_router
from app.ws.handler import websocket_handler
from app.tasks.heat_cron import heat_cron_loop
from app.agent.loop import agent_loop


@asynccontextmanager
async def lifespan(app):
    # Auto-create tables (dev mode — production uses Alembic migrations)
    from app.database import engine, Base
    # Import all models so Base.metadata knows about them
    import app.models.user  # noqa: F401
    import app.models.resident  # noqa: F401
    import app.models.conversation  # noqa: F401
    import app.models.transaction  # noqa: F401
    import app.models.system_config  # noqa: F401
    import app.models.forge_session  # noqa: F401
    import app.models.pending_message  # noqa: F401
    import app.models.memory  # noqa: F401
    import app.models.personality_history  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Start heat cron on startup
    task = asyncio.create_task(heat_cron_loop())
    agent_task = asyncio.create_task(agent_loop.run())
    yield
    task.cancel()
    agent_task.cancel()


app = FastAPI(title="Skills World API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(residents.router)
app.include_router(forge.router)
app.include_router(profile.router)
app.include_router(search.router)
app.include_router(bulletin.router)
app.include_router(onboarding.router)
app.include_router(sprites.router)
app.include_router(avatar.router)
app.include_router(settings_router.router)
app.include_router(media_router.router)
app.include_router(admin_router)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)


@app.get("/health")
async def health():
    return {"status": "ok"}
