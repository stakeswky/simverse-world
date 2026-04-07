# Skills World MVP — Core Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the minimum end-to-end loop: user logs in → walks around the pixel world → chats with an AI resident → Soul Coin is charged.

**Architecture:** React SPA with Phaser.js game canvas embedded. FastAPI backend with WebSocket for real-time chat + REST for CRUD. PostgreSQL for persistence, Redis for sessions and live state. LLM calls via Anthropic SDK.

**Tech Stack:** React 18 + Vite + TypeScript (frontend), Phaser 3.80 (game engine), FastAPI + SQLAlchemy + Alembic (backend), PostgreSQL 16, Redis 7, Anthropic Python SDK.

**Scope:** This is Plan 1 of 4. Future plans cover:
- Plan 2: Forge (炼化器) — Skill creation pipeline
- Plan 3: Profile & Resident Management — CRUD, import, quality scoring
- Plan 4: Economy & Social — Soul Coin advanced flows, search, bulletin board

**Existing assets:**
- `demo/index.html` — Verified Phaser prototype with map, movement, collision, status visuals, React overlay chat drawer
- `demo/assets/village/` — Smallville tilemap (3.7MB), 16 tileset PNGs, 25 character spritesheets, collision data

---

## File Structure

### Frontend (`frontend/`)

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── main.tsx                    # React entry point
│   ├── App.tsx                     # Router + layout shell
│   ├── stores/
│   │   └── gameStore.ts            # Zustand store: auth, chat, coins, npc state
│   ├── pages/
│   │   ├── LoginPage.tsx           # GitHub OAuth + email login
│   │   └── GamePage.tsx            # Phaser container + overlays
│   ├── components/
│   │   ├── TopNav.tsx              # Navigation bar
│   │   ├── ChatDrawer.tsx          # Right-side conversation panel
│   │   ├── NpcTooltip.tsx          # Floating NPC info on proximity
│   │   └── LoadingScreen.tsx       # Pixel-art loading progress
│   ├── game/
│   │   ├── GameScene.ts            # Phaser scene: preload, create, update
│   │   ├── PlayerController.ts     # WASD/arrow movement + collision
│   │   ├── NpcManager.ts           # Spawn NPCs, status visuals, bubbles
│   │   ├── StatusVisuals.ts        # Tween/tint/particle configs per status
│   │   └── phaserBridge.ts         # Event bus between Phaser and React
│   ├── services/
│   │   ├── api.ts                  # REST client (fetch wrapper)
│   │   ├── ws.ts                   # WebSocket client + reconnect
│   │   └── auth.ts                 # OAuth flow + JWT storage
│   └── styles/
│       └── global.css              # Dark theme variables + base styles
├── public/
│   └── assets/village/             # Copied from demo/assets/village/
```

### Backend (`backend/`)

```
backend/
├── pyproject.toml
├── alembic.ini
├── alembic/
│   └── versions/                   # DB migrations
├── app/
│   ├── main.py                     # FastAPI app + CORS + WebSocket mount
│   ├── config.py                   # Settings (env vars)
│   ├── database.py                 # SQLAlchemy engine + session
│   ├── models/
│   │   ├── user.py                 # User ORM model
│   │   ├── resident.py             # Resident ORM model
│   │   ├── conversation.py         # Conversation + Message ORM
│   │   └── transaction.py          # Soul Coin transaction ORM
│   ├── schemas/
│   │   ├── user.py                 # Pydantic schemas
│   │   ├── resident.py
│   │   ├── conversation.py
│   │   └── transaction.py
│   ├── routers/
│   │   ├── auth.py                 # POST /auth/login, /auth/github/callback
│   │   ├── residents.py            # GET /residents, GET /residents/:slug
│   │   └── users.py                # GET /users/me
│   ├── services/
│   │   ├── auth_service.py         # JWT create/verify, GitHub OAuth
│   │   ├── chat_service.py         # Prompt assembly + LLM call + streaming
│   │   ├── coin_service.py         # Balance check + charge + reward
│   │   └── resident_service.py     # Resident CRUD + status management
│   ├── ws/
│   │   ├── handler.py              # WebSocket connection handler
│   │   ├── protocol.py             # Message type definitions
│   │   └── manager.py              # Connection pool + broadcast
│   └── llm/
│       ├── client.py               # Anthropic SDK wrapper
│       └── prompt.py               # Three-layer prompt assembler
├── tests/
│   ├── conftest.py                 # Fixtures: test DB, test client
│   ├── test_auth.py
│   ├── test_residents.py
│   ├── test_chat.py
│   └── test_coins.py
├── seed/
│   └── seed_residents.py           # Load demo residents into DB
```

---

## Task 1: Backend Project Scaffold + Database

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/resident.py`
- Create: `backend/app/models/conversation.py`
- Create: `backend/app/models/transaction.py`
- Create: `backend/alembic.ini`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create `pyproject.toml` with dependencies**

```toml
[project]
name = "skills-world-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "pydantic-settings>=2.6",
    "python-jose[cryptography]>=3.3",
    "passlib[bcrypt]>=1.7",
    "httpx>=0.27",
    "redis>=5.2",
    "anthropic>=0.42",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "httpx>=0.27"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create `app/config.py`**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/skills_world"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours
    github_client_id: str = ""
    github_client_secret: str = ""
    anthropic_api_key: str = ""
    llm_default_model: str = "claude-haiku-4-5-20251001"
    llm_max_tokens: int = 512
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": ".env"}

settings = Settings()
```

- [ ] **Step 3: Create `app/database.py`**

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with async_session() as session:
        yield session
```

- [ ] **Step 4: Create ORM models**

`app/models/user.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    soul_coin_balance: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

`app/models/resident.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Resident(Base):
    __tablename__ = "residents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    district: Mapped[str] = mapped_column(String(50), default="free")
    status: Mapped[str] = mapped_column(String(20), default="idle")  # idle, chatting, sleeping, popular
    heat: Mapped[int] = mapped_column(Integer, default=0)
    model_tier: Mapped[str] = mapped_column(String(20), default="standard")
    token_cost_per_turn: Mapped[int] = mapped_column(Integer, default=1)
    creator_id: Mapped[str] = mapped_column(String, index=True)
    ability_md: Mapped[str] = mapped_column(Text, default="")
    persona_md: Mapped[str] = mapped_column(Text, default="")
    soul_md: Mapped[str] = mapped_column(Text, default="")
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    sprite_key: Mapped[str] = mapped_column(String(100), default="伊莎贝拉")
    tile_x: Mapped[int] = mapped_column(Integer, default=76)
    tile_y: Mapped[int] = mapped_column(Integer, default=50)
    star_rating: Mapped[int] = mapped_column(Integer, default=1)  # 1-3
    total_conversations: Mapped[int] = mapped_column(Integer, default=0)
    avg_rating: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_conversation_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

`app/models/conversation.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    resident_id: Mapped[str] = mapped_column(String, ForeignKey("residents.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    turns: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(String, ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

`app/models/transaction.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, index=True)
    amount: Mapped[int] = mapped_column(Integer)  # positive = earn, negative = spend
    reason: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 5: Create `app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

app = FastAPI(title="Skills World API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Initialize Alembic and create first migration**

```bash
cd backend
pip install -e ".[dev]"
alembic init alembic
```

Edit `alembic/env.py` to import models and set `target_metadata = Base.metadata`.

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

- [ ] **Step 7: Write test to verify DB connection**

`tests/conftest.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.fixture
def anyio_backend():
    return "asyncio"
```

`tests/test_health.py`:
```python
import pytest

@pytest.mark.anyio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 8: Run tests**

```bash
cd backend && pytest tests/test_health.py -v
```
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/
git commit -m "feat: backend scaffold with FastAPI, SQLAlchemy models, Alembic migrations"
```

---

## Task 2: Auth — JWT + GitHub OAuth

**Files:**
- Create: `backend/app/services/auth_service.py`
- Create: `backend/app/routers/auth.py`
- Create: `backend/app/schemas/user.py`
- Modify: `backend/app/main.py` (register router)
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing test for email registration**

`tests/test_auth.py`:
```python
import pytest

@pytest.mark.anyio
async def test_register_email(client):
    resp = await client.post("/auth/register", json={
        "name": "TestUser",
        "email": "test@example.com",
        "password": "securepass123"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["name"] == "TestUser"
    assert data["user"]["soul_coin_balance"] == 100

@pytest.mark.anyio
async def test_login_email(client):
    # Register first
    await client.post("/auth/register", json={
        "name": "TestUser", "email": "login@example.com", "password": "securepass123"
    })
    # Then login
    resp = await client.post("/auth/login", json={
        "email": "login@example.com", "password": "securepass123"
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()

@pytest.mark.anyio
async def test_get_me(client):
    reg = await client.post("/auth/register", json={
        "name": "Me", "email": "me@example.com", "password": "pass123"
    })
    token = reg.json()["access_token"]
    resp = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_auth.py -v
```
Expected: FAIL — routes don't exist yet

- [ ] **Step 3: Implement auth schemas**

`app/schemas/user.py`:
```python
from pydantic import BaseModel, EmailStr

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    avatar: str | None
    soul_coin_balance: int

class AuthResponse(BaseModel):
    access_token: str
    user: UserResponse
```

- [ ] **Step 4: Implement auth service**

`app/services/auth_service.py`:
```python
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.models.transaction import Transaction

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def verify_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except Exception:
        return None

async def register_user(db: AsyncSession, name: str, email: str, password: str) -> tuple[User, str]:
    user = User(name=name, email=email, hashed_password=pwd_context.hash(password))
    db.add(user)
    # Record signup bonus
    db.add(Transaction(user_id=user.id, amount=100, reason="signup_bonus"))
    await db.commit()
    await db.refresh(user)
    return user, create_token(user.id)

async def login_user(db: AsyncSession, email: str, password: str) -> tuple[User, str] | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password or not pwd_context.verify(password, user.hashed_password):
        return None
    return user, create_token(user.id)

async def get_current_user(db: AsyncSession, token: str) -> User | None:
    user_id = verify_token(token)
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
```

- [ ] **Step 5: Implement auth router**

`app/routers/auth.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import RegisterRequest, LoginRequest, AuthResponse, UserResponse
from app.services.auth_service import register_user, login_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user, token = await register_user(db, req.name, req.email, req.password)
    return AuthResponse(access_token=token, user=UserResponse(
        id=user.id, name=user.name, email=user.email,
        avatar=user.avatar, soul_coin_balance=user.soul_coin_balance
    ))

@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await login_user(db, req.email, req.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user, token = result
    return AuthResponse(access_token=token, user=UserResponse(
        id=user.id, name=user.name, email=user.email,
        avatar=user.avatar, soul_coin_balance=user.soul_coin_balance
    ))
```

`app/routers/users.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import UserResponse
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserResponse)
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401)
    user = await get_current_user(db, auth.removeprefix("Bearer "))
    if not user:
        raise HTTPException(status_code=401)
    return UserResponse(
        id=user.id, name=user.name, email=user.email,
        avatar=user.avatar, soul_coin_balance=user.soul_coin_balance
    )
```

- [ ] **Step 6: Register routers in `main.py`**

Add to `app/main.py`:
```python
from app.routers import auth, users

app.include_router(auth.router)
app.include_router(users.router)
```

- [ ] **Step 7: Run tests**

```bash
pytest tests/test_auth.py -v
```
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: auth with email registration, login, JWT, /users/me"
```

---

## Task 3: Residents REST API + Seed Data

**Files:**
- Create: `backend/app/schemas/resident.py`
- Create: `backend/app/routers/residents.py`
- Create: `backend/app/services/resident_service.py`
- Create: `backend/seed/seed_residents.py`
- Modify: `backend/app/main.py` (register router)
- Create: `backend/tests/test_residents.py`

- [ ] **Step 1: Write failing test**

`tests/test_residents.py`:
```python
import pytest

@pytest.mark.anyio
async def test_list_residents(client):
    resp = await client.get("/residents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

@pytest.mark.anyio
async def test_get_resident_by_slug(client, seeded_db):
    resp = await client.get("/residents/isabella")
    assert resp.status_code == 200
    assert resp.json()["name"] == "伊莎贝拉"
    assert resp.json()["status"] in ["idle", "sleeping", "popular", "chatting"]
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_residents.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement resident schemas**

`app/schemas/resident.py`:
```python
from pydantic import BaseModel

class ResidentListItem(BaseModel):
    id: str
    slug: str
    name: str
    district: str
    status: str
    heat: int
    sprite_key: str
    tile_x: int
    tile_y: int
    star_rating: int
    token_cost_per_turn: int
    meta_json: dict

class ResidentDetail(ResidentListItem):
    ability_md: str
    persona_md: str
    soul_md: str
    total_conversations: int
    avg_rating: float
    creator_id: str
```

- [ ] **Step 4: Implement resident service**

`app/services/resident_service.py`:
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.resident import Resident

async def list_residents(db: AsyncSession) -> list[Resident]:
    result = await db.execute(select(Resident).order_by(Resident.heat.desc()))
    return list(result.scalars().all())

async def get_resident_by_slug(db: AsyncSession, slug: str) -> Resident | None:
    result = await db.execute(select(Resident).where(Resident.slug == slug))
    return result.scalar_one_or_none()
```

- [ ] **Step 5: Implement residents router**

`app/routers/residents.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.resident import ResidentListItem, ResidentDetail
from app.services.resident_service import list_residents, get_resident_by_slug

router = APIRouter(prefix="/residents", tags=["residents"])

@router.get("", response_model=list[ResidentListItem])
async def list_all(db: AsyncSession = Depends(get_db)):
    residents = await list_residents(db)
    return [ResidentListItem.model_validate(r, from_attributes=True) for r in residents]

@router.get("/{slug}", response_model=ResidentDetail)
async def get_one(slug: str, db: AsyncSession = Depends(get_db)):
    r = await get_resident_by_slug(db, slug)
    if not r:
        raise HTTPException(status_code=404)
    return ResidentDetail.model_validate(r, from_attributes=True)
```

Register in `main.py`:
```python
from app.routers import auth, users, residents
app.include_router(residents.router)
```

- [ ] **Step 6: Create seed script**

`seed/seed_residents.py`:
```python
"""Seed 5 demo residents matching the verified demo/index.html NPCs."""
import asyncio
from app.database import engine, async_session, Base
from app.models.resident import Resident

SEED_RESIDENTS = [
    Resident(slug="isabella", name="伊莎贝拉", district="free", status="idle", heat=15,
             sprite_key="伊莎贝拉", tile_x=70, tile_y=42, star_rating=2, creator_id="system",
             token_cost_per_turn=1, ability_md="# 能力\n咖啡调制、客户服务",
             persona_md="# 人格\n热情开朗，喜欢和人聊天", soul_md="# 灵魂\n相信好咖啡能改变一天的心情",
             meta_json={"role": "咖啡店老板", "impression": "总是笑眯眯的"}),
    Resident(slug="klaus", name="克劳斯", district="engineering", status="popular", heat=62,
             sprite_key="克劳斯", tile_x=58, tile_y=55, star_rating=3, creator_id="system",
             token_cost_per_turn=1, ability_md="# 能力\n学术研究、论文写作",
             persona_md="# 人格\n严谨、话少、数据驱动", soul_md="# 灵魂\n追求真理，讨厌模糊的表述",
             meta_json={"role": "研究员", "impression": "总在思考什么"}),
    Resident(slug="adam", name="亚当", district="free", status="sleeping", heat=0,
             sprite_key="亚当", tile_x=100, tile_y=52, star_rating=1, creator_id="system",
             token_cost_per_turn=1, ability_md="# 能力\n药物学知识",
             persona_md="# 人格\n慵懒、随和", soul_md="# 灵魂\n享受当下",
             meta_json={"role": "药剂师", "impression": "经常打瞌睡"}),
    Resident(slug="mei", name="梅", district="academy", status="idle", heat=8,
             sprite_key="梅", tile_x=30, tile_y=65, star_rating=2, creator_id="system",
             token_cost_per_turn=1, ability_md="# 能力\n学习能力强、好奇心旺盛",
             persona_md="# 人格\n活泼、爱提问", soul_md="# 灵魂\n相信学习是终身的事",
             meta_json={"role": "大学生", "impression": "总是充满好奇"}),
    Resident(slug="tamara", name="塔玛拉", district="free", status="idle", heat=25,
             sprite_key="塔玛拉", tile_x=118, tile_y=38, star_rating=2, creator_id="system",
             token_cost_per_turn=1, ability_md="# 能力\n创意写作、故事构思",
             persona_md="# 人格\n沉浸在自己的世界里", soul_md="# 灵魂\n文字是灵魂的出口",
             meta_json={"role": "作家", "impression": "总在记录灵感"}),
]

async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as db:
        for r in SEED_RESIDENTS:
            db.add(r)
        await db.commit()
    print(f"Seeded {len(SEED_RESIDENTS)} residents")

if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 7: Run seed + tests**

```bash
cd backend && python -m seed.seed_residents
pytest tests/test_residents.py -v
```
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: residents REST API with seed data for 5 demo NPCs"
```

---

## Task 4: WebSocket + Chat Service with LLM

**Files:**
- Create: `backend/app/ws/protocol.py`
- Create: `backend/app/ws/manager.py`
- Create: `backend/app/ws/handler.py`
- Create: `backend/app/llm/client.py`
- Create: `backend/app/llm/prompt.py`
- Create: `backend/app/services/chat_service.py`
- Create: `backend/app/services/coin_service.py`
- Modify: `backend/app/main.py` (mount WebSocket)
- Create: `backend/tests/test_chat.py`

- [ ] **Step 1: Write failing test for coin service**

`tests/test_coins.py`:
```python
import pytest
from app.services.coin_service import check_balance, charge, reward

@pytest.mark.anyio
async def test_charge_deducts_balance(db_session, test_user):
    ok = await charge(db_session, test_user.id, 5, "chat")
    assert ok is True
    assert test_user.soul_coin_balance == 95  # started with 100

@pytest.mark.anyio
async def test_charge_fails_if_insufficient(db_session, test_user):
    test_user.soul_coin_balance = 0
    ok = await charge(db_session, test_user.id, 5, "chat")
    assert ok is False
```

- [ ] **Step 2: Implement coin service**

`app/services/coin_service.py`:
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.transaction import Transaction

async def check_balance(db: AsyncSession, user_id: str, amount: int) -> bool:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    return user is not None and user.soul_coin_balance >= amount

async def charge(db: AsyncSession, user_id: str, amount: int, reason: str) -> bool:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.soul_coin_balance < amount:
        return False
    user.soul_coin_balance -= amount
    db.add(Transaction(user_id=user_id, amount=-amount, reason=reason))
    await db.commit()
    return True

async def reward(db: AsyncSession, user_id: str, amount: int, reason: str) -> int:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return 0
    user.soul_coin_balance += amount
    db.add(Transaction(user_id=user_id, amount=amount, reason=reason))
    await db.commit()
    return user.soul_coin_balance
```

- [ ] **Step 3: Implement LLM prompt assembler**

`app/llm/prompt.py`:
```python
def assemble_system_prompt(resident) -> str:
    """Assemble the three-layer system prompt from resident data."""
    parts = [
        f"你是 {resident.name}，住在 Skills World 的{resident.district}街区。",
        "",
    ]
    if resident.soul_md:
        parts.append("## 灵魂（你为什么这样做）")
        parts.append(resident.soul_md)
        parts.append("")
    if resident.persona_md:
        parts.append("## 人格（你怎么做、怎么说）")
        parts.append(resident.persona_md)
        parts.append("")
    if resident.ability_md:
        parts.append("## 能力（你能做什么）")
        parts.append(resident.ability_md)
        parts.append("")
    parts.append("请始终保持角色扮演，用你的人格风格回应访客。回复简洁，不超过200字。")
    return "\n".join(parts)
```

- [ ] **Step 4: Implement LLM client**

`app/llm/client.py`:
```python
import anthropic
from app.config import settings

_client = None

def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client

async def stream_chat(system_prompt: str, messages: list[dict], model: str | None = None):
    """Yield text chunks from LLM streaming response."""
    client = get_client()
    async with client.messages.stream(
        model=model or settings.llm_default_model,
        max_tokens=settings.llm_max_tokens,
        system=system_prompt,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text
```

- [ ] **Step 5: Implement WebSocket protocol and manager**

`app/ws/protocol.py`:
```python
from pydantic import BaseModel

class WSMessage(BaseModel):
    type: str

class StartChat(WSMessage):
    type: str = "start_chat"
    resident_slug: str

class ChatMsg(WSMessage):
    type: str = "chat_msg"
    text: str

class EndChat(WSMessage):
    type: str = "end_chat"
```

`app/ws/manager.py`:
```python
import json
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}  # user_id -> ws

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active[user_id] = ws

    def disconnect(self, user_id: str):
        self.active.pop(user_id, None)

    async def send(self, user_id: str, data: dict):
        ws = self.active.get(user_id)
        if ws:
            await ws.send_json(data)

    async def broadcast(self, data: dict, exclude: str | None = None):
        for uid, ws in self.active.items():
            if uid != exclude:
                await ws.send_json(data)

manager = ConnectionManager()
```

- [ ] **Step 6: Implement WebSocket handler**

`app/ws/handler.py`:
```python
import json
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.database import async_session
from app.models.resident import Resident
from app.models.conversation import Conversation, Message
from app.services.auth_service import verify_token
from app.services.coin_service import charge
from app.llm.prompt import assemble_system_prompt
from app.llm.client import stream_chat
from app.ws.manager import manager

async def websocket_handler(ws: WebSocket):
    # Authenticate via query param token
    token = ws.query_params.get("token", "")
    user_id = verify_token(token)
    if not user_id:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(user_id, ws)
    current_conversation: Conversation | None = None
    current_resident: Resident | None = None
    chat_messages: list[dict] = []

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")

            async with async_session() as db:
                if msg_type == "start_chat":
                    slug = data["resident_slug"]
                    result = await db.execute(select(Resident).where(Resident.slug == slug))
                    resident = result.scalar_one_or_none()
                    if not resident:
                        await manager.send(user_id, {"type": "error", "message": "Resident not found"})
                        continue
                    if resident.status == "chatting":
                        await manager.send(user_id, {"type": "error", "message": "Resident is busy"})
                        continue
                    if resident.status == "sleeping":
                        resident.status = "idle"

                    # Create conversation
                    conv = Conversation(user_id=user_id, resident_id=resident.id)
                    db.add(conv)
                    resident.status = "chatting"
                    await db.commit()
                    await db.refresh(conv)

                    current_conversation = conv
                    current_resident = resident
                    chat_messages = []

                    await manager.send(user_id, {"type": "chat_started", "resident_slug": slug})
                    await manager.broadcast(
                        {"type": "resident_status", "resident_slug": slug, "status": "chatting"},
                        exclude=user_id
                    )

                elif msg_type == "chat_msg" and current_conversation and current_resident:
                    text = data["text"]
                    cost = current_resident.token_cost_per_turn

                    # Charge soul coins
                    ok = await charge(db, user_id, cost, f"chat:{current_resident.slug}")
                    if not ok:
                        await manager.send(user_id, {"type": "error", "message": "Insufficient Soul Coins"})
                        continue

                    # Save user message
                    db.add(Message(conversation_id=current_conversation.id, role="user", content=text))
                    current_conversation.turns += 1
                    await db.commit()

                    # Send balance update
                    result = await db.execute(
                        select(__import__('app.models.user', fromlist=['User']).User).where(
                            __import__('app.models.user', fromlist=['User']).User.id == user_id
                        )
                    )
                    user = result.scalar_one()
                    await manager.send(user_id, {
                        "type": "coin_update", "balance": user.soul_coin_balance,
                        "delta": -cost, "reason": "chat"
                    })

                    # Build messages for LLM
                    chat_messages.append({"role": "user", "content": text})
                    system_prompt = assemble_system_prompt(current_resident)

                    # Stream LLM response
                    full_reply = ""
                    async for chunk in stream_chat(system_prompt, chat_messages):
                        full_reply += chunk
                        await manager.send(user_id, {"type": "chat_reply", "text": chunk, "done": False})
                    await manager.send(user_id, {"type": "chat_reply", "text": "", "done": True})

                    # Save assistant message
                    chat_messages.append({"role": "assistant", "content": full_reply})
                    db.add(Message(conversation_id=current_conversation.id, role="assistant", content=full_reply))
                    await db.commit()

                    # Reward creator (1 SC per conversation turn)
                    from app.services.coin_service import reward
                    await reward(db, current_resident.creator_id, 1, f"chat_reward:{current_resident.slug}")

                elif msg_type == "end_chat" and current_conversation and current_resident:
                    from datetime import datetime
                    current_conversation.ended_at = datetime.utcnow()
                    # Restore resident status
                    current_resident.status = "popular" if current_resident.heat >= 50 else "idle"
                    current_resident.total_conversations += 1
                    current_resident.last_conversation_at = datetime.utcnow()
                    await db.commit()

                    slug = current_resident.slug
                    await manager.send(user_id, {"type": "chat_ended"})
                    await manager.broadcast(
                        {"type": "resident_status", "resident_slug": slug, "status": current_resident.status},
                        exclude=user_id
                    )
                    current_conversation = None
                    current_resident = None
                    chat_messages = []

    except WebSocketDisconnect:
        # Clean up if disconnected mid-chat
        if current_conversation and current_resident:
            async with async_session() as db:
                result = await db.execute(select(Resident).where(Resident.id == current_resident.id))
                r = result.scalar_one_or_none()
                if r:
                    r.status = "popular" if r.heat >= 50 else "idle"
                    await db.commit()
        manager.disconnect(user_id)
```

- [ ] **Step 7: Mount WebSocket in `main.py`**

Add to `app/main.py`:
```python
from fastapi import WebSocket
from app.ws.handler import websocket_handler

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)
```

- [ ] **Step 8: Run coin tests**

```bash
pytest tests/test_coins.py -v
```
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/
git commit -m "feat: WebSocket chat with LLM streaming, Soul Coin charging, three-layer prompt assembly"
```

---

## Task 5: Frontend Project Scaffold + React Shell

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles/global.css`
- Create: `frontend/src/stores/gameStore.ts`
- Create: `frontend/src/pages/LoginPage.tsx`
- Create: `frontend/src/pages/GamePage.tsx`
- Create: `frontend/src/components/TopNav.tsx`

- [ ] **Step 1: Initialize Vite + React + TypeScript project**

```bash
cd /Users/jimmy/Downloads/Skills-World
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install zustand react-router-dom
npm install -D @types/node
```

- [ ] **Step 2: Create global CSS with dark theme**

`src/styles/global.css`:
```css
:root {
  --bg-page: #0f0f17;
  --bg-card: #18181b;
  --bg-input: #27272a;
  --border: #27272a;
  --text-primary: #fafafa;
  --text-secondary: #a1a1aa;
  --text-muted: #71717a;
  --accent-red: #e94560;
  --accent-green: #53d769;
  --accent-blue: #0ea5e9;
  --radius: 8px;
  --nav-height: 48px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: var(--bg-page);
  color: var(--text-primary);
  font-family: Inter, system-ui, -apple-system, sans-serif;
  overflow: hidden;
}
```

- [ ] **Step 3: Create Zustand store**

`src/stores/gameStore.ts`:
```typescript
import { create } from 'zustand'

interface User {
  id: string
  name: string
  email: string
  avatar: string | null
  soul_coin_balance: number
}

interface GameState {
  user: User | null
  token: string | null
  chatOpen: boolean
  chatResident: { slug: string; name: string; role: string } | null
  inputFocused: boolean

  setAuth: (user: User, token: string) => void
  logout: () => void
  openChat: (resident: { slug: string; name: string; role: string }) => void
  closeChat: () => void
  setInputFocused: (v: boolean) => void
  updateBalance: (balance: number) => void
}

export const useGameStore = create<GameState>((set) => ({
  user: null,
  token: null,
  chatOpen: false,
  chatResident: null,
  inputFocused: false,

  setAuth: (user, token) => {
    localStorage.setItem('token', token)
    set({ user, token })
  },
  logout: () => {
    localStorage.removeItem('token')
    set({ user: null, token: null })
  },
  openChat: (resident) => set({ chatOpen: true, chatResident: resident }),
  closeChat: () => set({ chatOpen: false, chatResident: null, inputFocused: false }),
  setInputFocused: (v) => set({ inputFocused: v }),
  updateBalance: (balance) => set((s) => s.user ? { user: { ...s.user, soul_coin_balance: balance } } : {}),
}))
```

- [ ] **Step 4: Create TopNav component**

`src/components/TopNav.tsx`:
```typescript
import { useGameStore } from '../stores/gameStore'

export function TopNav() {
  const user = useGameStore((s) => s.user)
  const balance = user?.soul_coin_balance ?? 0

  return (
    <nav style={{
      position: 'fixed', top: 0, left: 0, right: 0, height: 'var(--nav-height)',
      background: 'var(--bg-card)', borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 16px', zIndex: 20,
    }}>
      <span style={{ fontWeight: 700, fontSize: 15 }}>🏙️ Skills World</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{
          color: 'var(--accent-green)', fontSize: 13,
          background: '#53d76915', padding: '4px 12px', borderRadius: 16,
        }}>🪙 {balance}</span>
        <div style={{
          width: 30, height: 30, background: 'var(--bg-input)', borderRadius: '50%',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
        }}>👤</div>
      </div>
    </nav>
  )
}
```

- [ ] **Step 5: Create LoginPage (minimal)**

`src/pages/LoginPage.tsx`:
```typescript
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGameStore } from '../stores/gameStore'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [isRegister, setIsRegister] = useState(false)
  const [error, setError] = useState('')
  const setAuth = useGameStore((s) => s.setAuth)
  const navigate = useNavigate()

  const submit = async () => {
    setError('')
    const endpoint = isRegister ? '/auth/register' : '/auth/login'
    const body = isRegister ? { name, email, password } : { email, password }
    const resp = await fetch(`${API}${endpoint}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!resp.ok) { setError('登录失败'); return }
    const data = await resp.json()
    setAuth(data.user, data.access_token)
    navigate('/')
  }

  const inputStyle = {
    width: '100%', background: 'var(--bg-input)', border: '1px solid var(--border)',
    color: 'var(--text-primary)', padding: '10px 14px', borderRadius: 'var(--radius)',
    fontSize: 14, outline: 'none', marginBottom: 8,
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%)',
    }}>
      <div style={{
        background: '#18181bf0', border: '1px solid var(--border)', borderRadius: 16,
        padding: 32, width: 340, backdropFilter: 'blur(12px)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <div style={{ fontSize: 28 }}>🏙️</div>
          <div style={{ fontWeight: 800, fontSize: 18, marginTop: 4 }}>Skills World</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
            一座永不关闭的赛博城市
          </div>
        </div>
        {isRegister && (
          <input style={inputStyle} placeholder="名字" value={name} onChange={(e) => setName(e.target.value)} />
        )}
        <input style={inputStyle} placeholder="邮箱" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input style={inputStyle} placeholder="密码" type="password" value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()} />
        {error && <div style={{ color: 'var(--accent-red)', fontSize: 12, marginBottom: 8 }}>{error}</div>}
        <button onClick={submit} style={{
          width: '100%', background: 'var(--accent-red)', color: 'white', border: 'none',
          padding: 10, borderRadius: 'var(--radius)', fontSize: 14, fontWeight: 700, cursor: 'pointer',
        }}>{isRegister ? '注册并进入城市' : '进入城市'}</button>
        <div style={{ textAlign: 'center', marginTop: 10, color: 'var(--text-muted)', fontSize: 12, cursor: 'pointer' }}
          onClick={() => setIsRegister(!isRegister)}>
          {isRegister ? '已有账号？登录' : '没有账号？注册'}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Create GamePage (container for Phaser + overlays)**

`src/pages/GamePage.tsx`:
```typescript
import { useEffect, useRef } from 'react'
import { TopNav } from '../components/TopNav'
import { ChatDrawer } from '../components/ChatDrawer'
import { NpcTooltip } from '../components/NpcTooltip'
import { useGameStore } from '../stores/gameStore'

export function GamePage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const chatOpen = useGameStore((s) => s.chatOpen)

  useEffect(() => {
    // Phaser will be initialized in Task 6
    // Import GameScene dynamically to avoid SSR issues
    import('../game/GameScene').then(({ initGame }) => {
      if (containerRef.current) {
        initGame(containerRef.current)
      }
    })
  }, [])

  return (
    <>
      <TopNav />
      <div
        ref={containerRef}
        id="game-container"
        style={{
          position: 'fixed', top: 48, left: 0, bottom: 0,
          right: chatOpen ? 380 : 0,
          transition: 'right 0.3s ease',
        }}
      />
      <NpcTooltip />
      <ChatDrawer />
    </>
  )
}
```

- [ ] **Step 7: Create App.tsx with router**

`src/App.tsx`:
```typescript
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useGameStore } from './stores/gameStore'
import { LoginPage } from './pages/LoginPage'
import { GamePage } from './pages/GamePage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useGameStore((s) => s.token)
  if (!token) return <Navigate to="/login" />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<ProtectedRoute><GamePage /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
  )
}
```

Update `src/main.tsx`:
```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles/global.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>
)
```

- [ ] **Step 8: Verify frontend builds**

```bash
cd frontend && npm run build
```
Expected: Build succeeds (Phaser imports will be stubbed in next task)

- [ ] **Step 9: Commit**

```bash
git add frontend/
git commit -m "feat: frontend scaffold with React, Zustand, login page, game page shell"
```

---

## Task 6: Phaser Game Integration into React

**Files:**
- Create: `frontend/src/game/phaserBridge.ts`
- Create: `frontend/src/game/StatusVisuals.ts`
- Create: `frontend/src/game/NpcManager.ts`
- Create: `frontend/src/game/PlayerController.ts`
- Create: `frontend/src/game/GameScene.ts`
- Copy: `demo/assets/village/` → `frontend/public/assets/village/`

- [ ] **Step 1: Install Phaser**

```bash
cd frontend && npm install phaser
```

- [ ] **Step 2: Create Phaser↔React event bridge**

`src/game/phaserBridge.ts`:
```typescript
type EventCallback = (...args: any[]) => void

class PhaserBridge {
  private listeners = new Map<string, Set<EventCallback>>()

  on(event: string, cb: EventCallback) {
    if (!this.listeners.has(event)) this.listeners.set(event, new Set())
    this.listeners.get(event)!.add(cb)
    return () => this.listeners.get(event)?.delete(cb)
  }

  emit(event: string, ...args: any[]) {
    this.listeners.get(event)?.forEach((cb) => cb(...args))
  }
}

export const bridge = new PhaserBridge()

// Events:
// "npc:nearby"   -> { name, role, status, slug } | null
// "npc:interact" -> { slug, name, role }
// "input:focus"  -> boolean
```

- [ ] **Step 3: Create StatusVisuals config**

`src/game/StatusVisuals.ts`:
```typescript
import Phaser from 'phaser'

export interface StatusConfig {
  label: string
  canChat: boolean
  bubble: string
  alpha: number
  tint: number | null
}

export const STATUS_CONFIG: Record<string, StatusConfig> = {
  idle:     { label: '🟢 空闲',  canChat: true,  bubble: '💭', alpha: 1.0, tint: null },
  sleeping: { label: '💤 沉睡',  canChat: false, bubble: '💤', alpha: 0.5, tint: 0x8888cc },
  chatting: { label: '💬 对话中', canChat: false, bubble: '💬', alpha: 1.0, tint: null },
  popular:  { label: '🔥 热门',  canChat: true,  bubble: '🔥', alpha: 1.0, tint: null },
}

const IDLE_THOUGHTS = ['💭', '☕', '🤔', '📖', '✨', '🎵']

export function applyStatusVisuals(
  scene: Phaser.Scene,
  sprite: Phaser.Physics.Arcade.Sprite,
  status: string,
  x: number, y: number
) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.idle
  sprite.setAlpha(cfg.alpha)
  if (cfg.tint) sprite.setTint(cfg.tint)

  if (status === 'idle') {
    scene.tweens.add({ targets: sprite, scaleY: sprite.scaleY * 0.97, duration: 1800, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
  } else if (status === 'sleeping') {
    scene.tweens.add({ targets: sprite, y: y + 3, duration: 2500, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
    scene.tweens.add({ targets: sprite, angle: 8, duration: 3000, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
  } else if (status === 'chatting') {
    scene.tweens.add({ targets: sprite, x: x - 2, duration: 300, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
  } else if (status === 'popular') {
    scene.tweens.add({ targets: sprite, scaleX: sprite.scaleX * 1.03, scaleY: sprite.scaleY * 1.03, duration: 1200, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
    const glow = scene.add.graphics().setDepth(0)
    glow.fillStyle(0xf59e0b, 0.08); glow.fillCircle(x, y, 35)
    glow.fillStyle(0xf59e0b, 0.05); glow.fillCircle(x, y, 50)
    scene.tweens.add({ targets: glow, alpha: 0.3, duration: 1500, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
  }

  // Bubble
  const bubbleText = scene.add.text(x + 20, y - 48, cfg.bubble, {
    font: '16px system-ui', backgroundColor: '#18181bee', padding: { x: 4, y: 2 },
  }).setOrigin(0.5).setDepth(4)
  scene.tweens.add({ targets: bubbleText, y: bubbleText.y - 4, duration: 2000, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })

  if (status === 'idle') {
    let idx = 0
    scene.time.addEvent({ delay: 3000, loop: true, callback: () => {
      idx = (idx + 1) % IDLE_THOUGHTS.length
      bubbleText.setText(IDLE_THOUGHTS[idx])
    }})
  } else if (status === 'sleeping') {
    const zzz = ['💤', '💤💤', '💤💤💤', '💤💤', '💤']
    let idx = 0
    scene.time.addEvent({ delay: 1500, loop: true, callback: () => {
      idx = (idx + 1) % zzz.length; bubbleText.setText(zzz[idx])
    }})
  }

  return bubbleText
}
```

- [ ] **Step 4: Create GameScene (port from demo)**

`src/game/GameScene.ts`:
— Port the verified `demo/index.html` Phaser logic into a TypeScript class-based scene. This is the largest file. Key differences from demo:
- Uses `bridge.emit()` instead of `document.getElementById` for React communication
- Reads `useGameStore.getState().inputFocused` to skip keyboard when chat input focused
- Fetches resident data from API on create instead of hardcoded array

```typescript
import Phaser from 'phaser'
import { bridge } from './phaserBridge'
import { applyStatusVisuals, STATUS_CONFIG } from './StatusVisuals'
import { useGameStore } from '../stores/gameStore'

const TILE_SIZE = 32
const PLAYER_SPEED = 160
const NPC_INTERACT_DISTANCE = 60

const TILESET_KEYS = [
  'blocks_1', 'walls', 'interiors_pt1', 'interiors_pt2', 'interiors_pt3',
  'interiors_pt4', 'interiors_pt5', 'CuteRPG_Field_B', 'CuteRPG_Field_C',
  'CuteRPG_Harbor_C', 'CuteRPG_Village_B', 'CuteRPG_Forest_B', 'CuteRPG_Desert_C',
  'CuteRPG_Mountains_B', 'CuteRPG_Desert_B', 'CuteRPG_Forest_C',
]

interface ResidentData {
  slug: string; name: string; status: string; sprite_key: string;
  tile_x: number; tile_y: number; meta_json: { role?: string };
  token_cost_per_turn: number; star_rating: number; heat: number;
}

let gameInstance: Phaser.Game | null = null

export function initGame(container: HTMLElement) {
  if (gameInstance) return
  const zoom = Math.max(1, window.innerWidth / 4400)
  gameInstance = new Phaser.Game({
    type: Phaser.AUTO,
    width: container.clientWidth / zoom,
    height: container.clientHeight / zoom,
    parent: container,
    pixelArt: true,
    physics: { default: 'arcade', arcade: { gravity: { y: 0 } } },
    scene: [MainScene],
    scale: { zoom },
  })
}

class MainScene extends Phaser.Scene {
  private player!: Phaser.Physics.Arcade.Sprite
  private cursors!: Phaser.Types.Input.Keyboard.CursorKeys
  private wasd!: Record<string, Phaser.Input.Keyboard.Key>
  private eKey!: Phaser.Input.Keyboard.Key
  private npcSprites: Phaser.Physics.Arcade.Sprite[] = []
  private residents: ResidentData[] = []

  preload() {
    const base = '/assets/village/tilemap/'
    for (const key of TILESET_KEYS) {
      const filename = key === 'walls' ? 'Room_Builder_32x32.png'
        : key === 'blocks_1' ? 'blocks_1.png'
        : `${key}.png`
      this.load.image(key, base + filename)
    }
    this.load.tilemapTiledJSON('map', base + 'tilemap.json')
    this.load.atlas('player_atlas', '/assets/village/agents/埃迪/texture.png', '/assets/village/agents/sprite.json')
  }

  async create() {
    // Fetch residents from API
    const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    try {
      const resp = await fetch(`${API}/residents`)
      this.residents = await resp.json()
    } catch { this.residents = [] }

    // Load resident sprites
    for (const r of this.residents) {
      if (!this.textures.exists(r.sprite_key)) {
        this.load.atlas(r.sprite_key, `/assets/village/agents/${r.sprite_key}/texture.png`, '/assets/village/agents/sprite.json')
      }
    }
    this.load.start()
    this.load.once('complete', () => this.setupWorld())
  }

  private setupWorld() {
    // Build tilemap (identical to demo)
    const map = this.make.tilemap({ key: 'map' })
    const tilesets = {
      blocks: map.addTilesetImage('blocks', 'blocks_1'),
      walls: map.addTilesetImage('Room_Builder_32x32', 'walls'),
      ...Object.fromEntries(['interiors_pt1','interiors_pt2','interiors_pt3','interiors_pt4','interiors_pt5',
        'CuteRPG_Field_B','CuteRPG_Field_C','CuteRPG_Harbor_C','CuteRPG_Village_B','CuteRPG_Forest_B',
        'CuteRPG_Desert_C','CuteRPG_Mountains_B','CuteRPG_Desert_B','CuteRPG_Forest_C',
      ].map(k => [k, map.addTilesetImage(k, k)])),
    }
    const allTs = Object.values(tilesets).filter(Boolean) as Phaser.Tilemaps.Tileset[]
    const mainTs = allTs.filter(t => t.name !== 'blocks')

    const layers = ['Bottom Ground','Exterior Ground','Exterior Decoration L1','Exterior Decoration L2',
      'Interior Ground','Wall','Interior Furniture L1','Interior Furniture L2 ','Foreground L1','Foreground L2']
    layers.forEach(name => {
      const layer = map.createLayer(name, name === 'Wall' ? [tilesets.CuteRPG_Field_C!, tilesets.walls!] : mainTs, 0, 0)
      if (name.startsWith('Foreground')) layer?.setDepth(2)
    })
    const collisionLayer = map.createLayer('Collisions', tilesets.blocks!, 0, 0)
    collisionLayer?.setCollisionByExclusion([-1])
    collisionLayer?.setVisible(false)

    // Player
    this.player = this.physics.add.sprite(76 * TILE_SIZE, 50 * TILE_SIZE, 'player_atlas', 'down')
      .setSize(24, 24).setOffset(4, 8).setDepth(1)
    this.player.displayWidth = 40; this.player.scaleY = this.player.scaleX
    if (collisionLayer) this.physics.add.collider(this.player, collisionLayer)

    for (const dir of ['left','right','down','up']) {
      this.anims.create({
        key: `player-${dir}-walk`,
        frames: this.anims.generateFrameNames('player_atlas', { prefix: `${dir}-walk.`, start: 0, end: 3, zeroPad: 3 }),
        frameRate: 8, repeat: -1,
      })
    }

    // NPCs
    for (const r of this.residents) {
      const x = r.tile_x * TILE_SIZE + TILE_SIZE / 2
      const y = r.tile_y * TILE_SIZE + TILE_SIZE
      const sprite = this.physics.add.sprite(x, y, r.sprite_key, 'down')
        .setSize(24, 24).setOffset(4, 8).setDepth(1).setImmovable(true)
      sprite.displayWidth = 40; sprite.scaleY = sprite.scaleX;
      (sprite as any).residentData = r

      applyStatusVisuals(this, sprite, r.status, x, y)

      this.add.text(x, y - 32, r.name, {
        font: 'bold 13px system-ui', color: '#ffffff',
        backgroundColor: '#18181bcc', padding: { x: 6, y: 2 },
      }).setOrigin(0.5).setDepth(3)

      this.npcSprites.push(sprite)
    }

    // Camera
    this.cameras.main.startFollow(this.player, true, 0.1, 0.1)
    this.cameras.main.setBounds(0, 0, map.widthInPixels, map.heightInPixels)

    // Input
    this.cursors = this.input.keyboard!.createCursorKeys()
    this.wasd = this.input.keyboard!.addKeys({
      up: Phaser.Input.Keyboard.KeyCodes.W, down: Phaser.Input.Keyboard.KeyCodes.S,
      left: Phaser.Input.Keyboard.KeyCodes.A, right: Phaser.Input.Keyboard.KeyCodes.D,
    }) as any
    this.eKey = this.input.keyboard!.addKey(Phaser.Input.Keyboard.KeyCodes.E)
  }

  update() {
    if (!this.player?.body) return
    if (useGameStore.getState().inputFocused) {
      this.player.body.setVelocity(0, 0); this.player.anims.stop(); return
    }

    this.player.body.setVelocity(0, 0)
    const l = this.cursors.left.isDown || this.wasd.left.isDown
    const r = this.cursors.right.isDown || this.wasd.right.isDown
    const u = this.cursors.up.isDown || this.wasd.up.isDown
    const d = this.cursors.down.isDown || this.wasd.down.isDown

    if (l) { (this.player.body as any).setVelocityX(-PLAYER_SPEED); this.player.anims.play('player-left-walk', true) }
    else if (r) { (this.player.body as any).setVelocityX(PLAYER_SPEED); this.player.anims.play('player-right-walk', true) }
    else if (u) { (this.player.body as any).setVelocityY(-PLAYER_SPEED); this.player.anims.play('player-up-walk', true) }
    else if (d) { (this.player.body as any).setVelocityY(PLAYER_SPEED); this.player.anims.play('player-down-walk', true) }
    else { this.player.anims.stop() }

    this.player.body.velocity.normalize().scale(PLAYER_SPEED)

    // NPC proximity
    let nearest: ResidentData | null = null
    let nearestDist = Infinity
    for (const npc of this.npcSprites) {
      const dist = Phaser.Math.Distance.Between(this.player.x, this.player.y, npc.x, npc.y)
      if (dist < NPC_INTERACT_DISTANCE && dist < nearestDist) {
        nearestDist = dist; nearest = (npc as any).residentData
      }
    }
    bridge.emit('npc:nearby', nearest)

    if (Phaser.Input.Keyboard.JustDown(this.eKey) && nearest) {
      const cfg = STATUS_CONFIG[nearest.status]
      if (cfg?.canChat) bridge.emit('npc:interact', nearest)
    }
  }
}
```

- [ ] **Step 5: Copy assets**

```bash
cp -r demo/assets/village/ frontend/public/assets/village/
```

- [ ] **Step 6: Verify frontend dev server**

```bash
cd frontend && npm run dev
```
Open `http://localhost:5173/login`, register, verify game loads.

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat: Phaser game integrated into React with status visuals, bridge events"
```

---

## Task 7: ChatDrawer + NpcTooltip React Components + WebSocket

**Files:**
- Create: `frontend/src/components/ChatDrawer.tsx`
- Create: `frontend/src/components/NpcTooltip.tsx`
- Create: `frontend/src/services/ws.ts`

- [ ] **Step 1: Create WebSocket service**

`src/services/ws.ts`:
```typescript
import { useGameStore } from '../stores/gameStore'

let socket: WebSocket | null = null

export function connectWS() {
  const token = useGameStore.getState().token
  if (!token) return
  const API_WS = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace('http', 'ws')
  socket = new WebSocket(`${API_WS}/ws?token=${token}`)

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'coin_update') {
      useGameStore.getState().updateBalance(data.balance)
    }
    // Other message types handled by ChatDrawer via onMessage callback
    wsListeners.forEach((cb) => cb(data))
  }

  socket.onclose = () => {
    // Reconnect after 3 seconds
    setTimeout(connectWS, 3000)
  }
}

const wsListeners: Set<(data: any) => void> = new Set()
export function onWSMessage(cb: (data: any) => void) {
  wsListeners.add(cb)
  return () => wsListeners.delete(cb)
}

export function sendWS(data: object) {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(data))
  }
}
```

- [ ] **Step 2: Create NpcTooltip**

`src/components/NpcTooltip.tsx`:
```typescript
import { useEffect, useState } from 'react'
import { bridge } from '../game/phaserBridge'
import { STATUS_CONFIG } from '../game/StatusVisuals'
import { useGameStore } from '../stores/gameStore'

export function NpcTooltip() {
  const [npc, setNpc] = useState<any>(null)
  const chatOpen = useGameStore((s) => s.chatOpen)

  useEffect(() => bridge.on('npc:nearby', setNpc), [])

  if (!npc || chatOpen) return null
  const cfg = STATUS_CONFIG[npc.status] || STATUS_CONFIG.idle

  return (
    <div style={{
      position: 'fixed', top: 60, right: 12, zIndex: 15, minWidth: 180,
      background: '#18181bf5', color: '#d4d4d8', fontSize: 13,
      padding: '10px 14px', borderRadius: 10, border: '1px solid var(--border)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 22 }}>🧑‍💻</span>
        <div>
          <div style={{ color: '#fafafa', fontWeight: 700, fontSize: 14 }}>{npc.name}</div>
          <div style={{ color: '#71717a', fontSize: 12 }}>{npc.meta_json?.role}</div>
        </div>
        <span style={{ marginLeft: 'auto', fontSize: 11 }}>{cfg.label}</span>
      </div>
      <div style={{ color: '#52525b', fontSize: 11, marginTop: 6, textAlign: 'center' }}>
        {cfg.canChat
          ? <span>按 <kbd style={{ background: '#27272a', padding: '1px 5px', borderRadius: 3, color: '#fafafa' }}>E</kbd> 开始对话</span>
          : npc.status === 'sleeping' ? '💤 正在沉睡，无法对话' : '💬 正在和其他人聊天'}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create ChatDrawer**

`src/components/ChatDrawer.tsx`:
```typescript
import { useEffect, useRef, useState } from 'react'
import { bridge } from '../game/phaserBridge'
import { useGameStore } from '../stores/gameStore'
import { sendWS, onWSMessage } from '../services/ws'

interface Msg { role: 'user' | 'npc'; sender: string; text: string }

export function ChatDrawer() {
  const { chatOpen, chatResident, openChat, closeChat, setInputFocused } = useGameStore()
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState('')
  const messagesRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Listen for NPC interaction from Phaser
  useEffect(() => bridge.on('npc:interact', (npc: any) => {
    openChat({ slug: npc.slug, name: npc.name, role: npc.meta_json?.role || '' })
    sendWS({ type: 'start_chat', resident_slug: npc.slug })
    setMessages([])
    setStreaming('')
  }), [openChat])

  // Listen for WS messages
  useEffect(() => onWSMessage((data) => {
    if (data.type === 'chat_reply') {
      if (data.done) {
        setMessages((prev) => [...prev, { role: 'npc', sender: useGameStore.getState().chatResident?.name || '', text: streaming }])
        setStreaming('')
      } else {
        setStreaming((s) => s + data.text)
      }
    }
  }), [streaming])

  const send = () => {
    if (!input.trim() || !chatResident) return
    setMessages((prev) => [...prev, { role: 'user', sender: '你', text: input }])
    sendWS({ type: 'chat_msg', text: input })
    setInput('')
    setStreaming('')
  }

  const close = () => {
    sendWS({ type: 'end_chat' })
    closeChat()
  }

  useEffect(() => {
    messagesRef.current?.scrollTo(0, messagesRef.current.scrollHeight)
  }, [messages, streaming])

  // Escape to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape' && chatOpen) close() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [chatOpen])

  return (
    <div style={{
      position: 'fixed', top: 48, right: 0, bottom: 0, width: 380, zIndex: 20,
      background: 'var(--bg-card)', borderLeft: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      transform: chatOpen ? 'translateX(0)' : 'translateX(100%)',
      transition: 'transform 0.3s ease',
    }}>
      {/* Header */}
      <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ width: 40, height: 40, background: 'var(--bg-input)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>🧑‍💻</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>{chatResident?.name}</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{chatResident?.role}</div>
        </div>
        <div onClick={close} style={{ color: 'var(--text-muted)', fontSize: 18, cursor: 'pointer', padding: '4px 8px', borderRadius: 6 }}>✕</div>
      </div>

      {/* Messages */}
      <div ref={messagesRef} style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {messages.map((m, i) => (
          <div key={i} style={{
            maxWidth: '85%', padding: '10px 14px', borderRadius: 12, fontSize: 13, lineHeight: 1.6,
            ...(m.role === 'user'
              ? { background: 'var(--accent-red)', color: 'white', alignSelf: 'flex-end', borderBottomRightRadius: 4 }
              : { background: 'var(--bg-input)', color: '#d4d4d8', alignSelf: 'flex-start', borderBottomLeftRadius: 4 }),
          }}>
            {m.role === 'npc' && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{m.sender}</div>}
            {m.text}
          </div>
        ))}
        {streaming && (
          <div style={{ maxWidth: '85%', padding: '10px 14px', borderRadius: 12, fontSize: 13, lineHeight: 1.6, background: 'var(--bg-input)', color: '#d4d4d8', alignSelf: 'flex-start', borderBottomLeftRadius: 4 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{chatResident?.name}</div>
            {streaming}<span style={{ animation: 'blink 1s infinite' }}>▌</span>
          </div>
        )}
      </div>

      {/* Input */}
      <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8 }}>
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onFocus={() => setInputFocused(true)}
          onBlur={() => setInputFocused(false)}
          onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Enter') send() }}
          placeholder="输入消息..."
          style={{
            flex: 1, background: 'var(--bg-input)', border: '1px solid var(--border)',
            color: 'var(--text-primary)', padding: '10px 14px', borderRadius: 'var(--radius)',
            fontSize: 13, outline: 'none',
          }}
        />
        <button onClick={send} style={{
          background: 'var(--accent-red)', color: 'white', border: 'none',
          padding: '10px 16px', borderRadius: 'var(--radius)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
        }}>发送</button>
        <span style={{ color: 'var(--text-muted)', fontSize: 11, alignSelf: 'center' }}>1🪙</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Connect WebSocket on login**

Update `src/pages/GamePage.tsx` — add to the `useEffect`:
```typescript
import { connectWS } from '../services/ws'

useEffect(() => {
  connectWS()
  import('../game/GameScene').then(({ initGame }) => {
    if (containerRef.current) initGame(containerRef.current)
  })
}, [])
```

- [ ] **Step 5: End-to-end test**

1. Start backend: `cd backend && uvicorn app.main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Open `http://localhost:5173/login`
4. Register → enter city → walk to NPC → press E → type message → see LLM reply → see coin deducted

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: ChatDrawer + NpcTooltip + WebSocket integration, end-to-end chat with LLM"
```

---

## Task 8: Docker Compose for Local Dev

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/.env.example`

- [ ] **Step 1: Create docker-compose.yml**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: skills_world
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

volumes:
  pgdata:
```

- [ ] **Step 2: Create `.env.example`**

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/skills_world
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=change-me-in-production
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
ANTHROPIC_API_KEY=sk-ant-...
```

- [ ] **Step 3: Verify full stack**

```bash
docker compose up -d
cd backend && alembic upgrade head && python -m seed.seed_residents
uvicorn app.main:app --reload &
cd ../frontend && npm run dev
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml backend/.env.example
git commit -m "chore: docker-compose for PostgreSQL + Redis, env example"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] 像素地图渲染 → Task 6 (Phaser game scene)
- [x] 玩家移动/碰撞 → Task 6 (PlayerController in GameScene)
- [x] 走近居民交互 → Task 6 + 7 (NpcTooltip + bridge events)
- [x] 居民状态视觉系统 → Task 6 (StatusVisuals.ts)
- [x] 对话 prompt 三层组装 → Task 4 (prompt.py)
- [x] 对话 LLM 调用 → Task 4 (client.py + handler.py)
- [x] 对话历史保存 → Task 4 (Message model + handler)
- [x] Soul Coin 余额管理 → Task 4 (coin_service.py)
- [x] 对话扣费 + 创作者奖励 → Task 4 (handler.py charge + reward)
- [x] 注册/登录 → Task 2 (auth)
- [x] WebSocket 状态同步 → Task 4 + 7
- [ ] Skill 上传/导入 → Plan 2 (Forge)
- [ ] 炼化器 → Plan 2 (Forge)
- [ ] 个人主页 → Plan 3 (Profile)
- [ ] 居民搜索 → Plan 4 (Social)
- [ ] 公告板 → Plan 4 (Social)
- [ ] 对话评分 → Plan 3 (P1 feature)
- [ ] 每日登录奖励 → Plan 4 (P1 feature)

**Placeholder scan:** No TBDs, all code blocks complete.

**Type consistency:** Verified — `ResidentData` fields match `Resident` ORM, `STATUS_CONFIG` keys match status strings, WebSocket protocol types consistent between `handler.py` and `ws.ts`.
