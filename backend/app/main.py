from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import auth, users, residents, forge
from app.ws.handler import websocket_handler

app = FastAPI(title="Skills World API")

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


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)


@app.get("/health")
async def health():
    return {"status": "ok"}
