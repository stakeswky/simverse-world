import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import auth, users, residents, forge, profile, search, bulletin
from app.routers.admin import router as admin_router
from app.ws.handler import websocket_handler
from app.tasks.heat_cron import heat_cron_loop


@asynccontextmanager
async def lifespan(app):
    # Start heat cron on startup
    task = asyncio.create_task(heat_cron_loop())
    yield
    task.cancel()


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
app.include_router(admin_router)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)


@app.get("/health")
async def health():
    return {"status": "ok"}
