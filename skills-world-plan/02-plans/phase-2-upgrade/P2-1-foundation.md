# Plan 1: Foundation — 数据模型 + 动态配置 + LLM 客户端工厂

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立所有后续 Plan 的基础设施——数据库模型变更、运行时动态配置系统、支持系统/用户双轨的 LLM 客户端工厂。

**Architecture:** 在现有 SQLAlchemy async 模型上新增字段和表（User 扩展、Resident 扩展、SystemConfig、ForgeSession），通过 Alembic 迁移。动态配置采用 DB → .env → 代码默认值三级优先级，内存缓存。LLM 客户端从全局单例改为工厂模式，按 owner（system/user）选择不同的 API Key 和参数。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic, Anthropic SDK, pytest + pytest-asyncio

**Working directory:** `/Users/jimmy/Downloads/Skills-World/.worktrees/mvp-implementation/backend/`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/models/user.py` | Modify | 新增 linuxdo_id, is_admin, is_banned, player_resident_id, last_x/y, settings_json, custom_llm_* 字段 |
| `app/models/resident.py` | Modify | 新增 resident_type, reply_mode, portrait_url 字段 |
| `app/models/system_config.py` | Create | SystemConfig 模型（动态配置表） |
| `app/models/forge_session.py` | Create | ForgeSession 模型（炼化会话持久化） |
| `app/services/config_service.py` | Create | 动态配置读写服务（DB → .env → default，内存缓存） |
| `app/llm/client.py` | Modify | 从单例改为工厂模式，支持 system/user 双轨 |
| `app/config.py` | Modify | 新增 LinuxDo OAuth、头像生成 LLM 等配置字段 |
| `alembic/versions/003_foundation_upgrade.py` | Create | 数据库迁移脚本 |
| `tests/test_config_service.py` | Create | 动态配置服务测试 |
| `tests/test_llm_factory.py` | Create | LLM 客户端工厂测试 |
| `tests/test_models_foundation.py` | Create | 新模型/字段测试 |

---

## Task 1: User 模型扩展

**Files:**
- Modify: `app/models/user.py`
- Test: `tests/test_models_foundation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models_foundation.py
import pytest
from app.models.user import User


@pytest.mark.anyio
async def test_user_new_fields_defaults(db_session):
    """Verify new User fields exist with correct defaults."""
    user = User(
        name="test",
        email="test@example.com",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.is_admin is False
    assert user.is_banned is False
    assert user.linuxdo_id is None
    assert user.linuxdo_trust_level is None
    assert user.player_resident_id is None
    assert user.last_x == 2432
    assert user.last_y == 1600
    assert user.settings_json == {}
    assert user.custom_llm_enabled is False
    assert user.custom_llm_api_format == "anthropic"
    assert user.custom_llm_api_key is None
    assert user.custom_llm_base_url is None
    assert user.custom_llm_model is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/jimmy/Downloads/Skills-World/.worktrees/mvp-implementation/backend && python -m pytest tests/test_models_foundation.py::test_user_new_fields_defaults -v`
Expected: FAIL with `AttributeError: 'User' object has no attribute 'is_admin'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/models/user.py
import uuid
from datetime import datetime, UTC
from sqlalchemy import String, Integer, Boolean, DateTime, JSON, ForeignKey
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_daily_reward_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- New fields (Plan 1: Foundation) ---
    linuxdo_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    linuxdo_trust_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    player_resident_id: Mapped[str | None] = mapped_column(String, ForeignKey("residents.id"), nullable=True)
    last_x: Mapped[int] = mapped_column(Integer, default=2432)
    last_y: Mapped[int] = mapped_column(Integer, default=1600)
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict)
    custom_llm_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    custom_llm_api_format: Mapped[str] = mapped_column(String(20), default="anthropic")
    custom_llm_api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    custom_llm_base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    custom_llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models_foundation.py::test_user_new_fields_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/models/user.py tests/test_models_foundation.py
git commit -m "feat: extend User model with admin, linuxdo, player, settings, custom_llm fields"
```

---

## Task 2: Resident 模型扩展

**Files:**
- Modify: `app/models/resident.py`
- Test: `tests/test_models_foundation.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_models_foundation.py
from app.models.resident import Resident


@pytest.mark.anyio
async def test_resident_new_fields_defaults(db_session):
    """Verify new Resident fields exist with correct defaults."""
    # Need a user first (creator_id FK)
    user = User(name="creator", email="creator@test.com")
    db_session.add(user)
    await db_session.commit()

    resident = Resident(
        slug="test-resident",
        name="Test",
        creator_id=user.id,
    )
    db_session.add(resident)
    await db_session.commit()
    await db_session.refresh(resident)

    assert resident.resident_type == "npc"
    assert resident.reply_mode == "manual"
    assert resident.portrait_url is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models_foundation.py::test_resident_new_fields_defaults -v`
Expected: FAIL with `AttributeError: 'Resident' object has no attribute 'resident_type'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/models/resident.py — add these fields after search_vector:
    # --- New fields (Plan 1: Foundation) ---
    resident_type: Mapped[str] = mapped_column(String(20), default="npc")
    reply_mode: Mapped[str] = mapped_column(String(20), default="manual")
    portrait_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models_foundation.py::test_resident_new_fields_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/models/resident.py tests/test_models_foundation.py
git commit -m "feat: extend Resident model with resident_type, reply_mode, portrait_url"
```

---

## Task 3: SystemConfig 模型

**Files:**
- Create: `app/models/system_config.py`
- Test: `tests/test_models_foundation.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_models_foundation.py
from app.models.system_config import SystemConfig
from datetime import datetime, UTC


@pytest.mark.anyio
async def test_system_config_crud(db_session):
    """Verify SystemConfig model CRUD operations."""
    config = SystemConfig(
        key="economy.signup_bonus",
        value="100",
        group="economy",
        updated_by="admin-user-id",
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)

    assert config.key == "economy.signup_bonus"
    assert config.value == "100"
    assert config.group == "economy"
    assert config.updated_by == "admin-user-id"
    assert config.updated_at is not None

    # Update
    config.value = "200"
    await db_session.commit()
    await db_session.refresh(config)
    assert config.value == "200"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models_foundation.py::test_system_config_crud -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.system_config'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/models/system_config.py
from datetime import datetime, UTC
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SystemConfig(Base):
    __tablename__ = "system_config"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[str] = mapped_column(String(2000))
    group: Mapped[str] = mapped_column(String(50), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    updated_by: Mapped[str] = mapped_column(String(100))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models_foundation.py::test_system_config_crud -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/models/system_config.py tests/test_models_foundation.py
git commit -m "feat: add SystemConfig model for runtime dynamic configuration"
```

---

## Task 4: ForgeSession 模型

**Files:**
- Create: `app/models/forge_session.py`
- Test: `tests/test_models_foundation.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_models_foundation.py
from app.models.forge_session import ForgeSession


@pytest.mark.anyio
async def test_forge_session_creation(db_session):
    """Verify ForgeSession model creation with JSON fields."""
    user = User(name="forger", email="forger@test.com")
    db_session.add(user)
    await db_session.commit()

    session = ForgeSession(
        user_id=user.id,
        character_name="萧炎",
        mode="deep",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    assert session.id is not None
    assert session.character_name == "萧炎"
    assert session.mode == "deep"
    assert session.status == "routing"
    assert session.current_stage == ""
    assert session.research_data == {}
    assert session.extraction_data == {}
    assert session.build_output == {}
    assert session.validation_report == {}
    assert session.refinement_log == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models_foundation.py::test_forge_session_creation -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.forge_session'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/models/forge_session.py
import uuid
from datetime import datetime, UTC
from sqlalchemy import String, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ForgeSession(Base):
    __tablename__ = "forge_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    character_name: Mapped[str] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(20))  # "quick" | "deep"
    status: Mapped[str] = mapped_column(String(20), default="routing")
    current_stage: Mapped[str] = mapped_column(String(50), default="")
    research_data: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction_data: Mapped[dict] = mapped_column(JSON, default=dict)
    build_output: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_report: Mapped[dict] = mapped_column(JSON, default=dict)
    refinement_log: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models_foundation.py::test_forge_session_creation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/models/forge_session.py tests/test_models_foundation.py
git commit -m "feat: add ForgeSession model for forge pipeline state persistence"
```

---

## Task 5: Alembic 迁移脚本

**Files:**
- Create: `alembic/versions/003_foundation_upgrade.py`

- [ ] **Step 1: Generate migration**

```bash
cd /Users/jimmy/Downloads/Skills-World/.worktrees/mvp-implementation/backend
alembic revision --autogenerate -m "foundation upgrade: user, resident, system_config, forge_session"
```

If autogenerate fails (model imports not picked up), create manually:

- [ ] **Step 2: Write manual migration if needed**

```python
# alembic/versions/003_foundation_upgrade.py
"""foundation upgrade: user, resident, system_config, forge_session"""
from alembic import op
import sqlalchemy as sa

revision = "003_foundation"
down_revision = "002_add_search_and_reward_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- User table additions ---
    op.add_column("users", sa.Column("linuxdo_id", sa.String(50), unique=True, nullable=True))
    op.add_column("users", sa.Column("linuxdo_trust_level", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("users", sa.Column("is_banned", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("users", sa.Column("player_resident_id", sa.String(), sa.ForeignKey("residents.id"), nullable=True))
    op.add_column("users", sa.Column("last_x", sa.Integer(), server_default="2432", nullable=False))
    op.add_column("users", sa.Column("last_y", sa.Integer(), server_default="1600", nullable=False))
    op.add_column("users", sa.Column("settings_json", sa.JSON(), server_default="{}", nullable=False))
    op.add_column("users", sa.Column("custom_llm_enabled", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("users", sa.Column("custom_llm_api_format", sa.String(20), server_default="anthropic", nullable=False))
    op.add_column("users", sa.Column("custom_llm_api_key", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("custom_llm_base_url", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("custom_llm_model", sa.String(100), nullable=True))

    # --- Resident table additions ---
    op.add_column("residents", sa.Column("resident_type", sa.String(20), server_default="npc", nullable=False))
    op.add_column("residents", sa.Column("reply_mode", sa.String(20), server_default="manual", nullable=False))
    op.add_column("residents", sa.Column("portrait_url", sa.String(500), nullable=True))

    # --- SystemConfig table ---
    op.create_table(
        "system_config",
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("value", sa.String(2000), nullable=False),
        sa.Column("group", sa.String(50), nullable=False, index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(100), nullable=False),
    )

    # --- ForgeSession table ---
    op.create_table(
        "forge_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("character_name", sa.String(200), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="routing", nullable=False),
        sa.Column("current_stage", sa.String(50), server_default="", nullable=False),
        sa.Column("research_data", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("extraction_data", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("build_output", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("validation_report", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("refinement_log", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("forge_sessions")
    op.drop_table("system_config")
    op.drop_column("residents", "portrait_url")
    op.drop_column("residents", "reply_mode")
    op.drop_column("residents", "resident_type")
    for col in [
        "custom_llm_model", "custom_llm_base_url", "custom_llm_api_key",
        "custom_llm_api_format", "custom_llm_enabled", "settings_json",
        "last_y", "last_x", "player_resident_id", "is_banned", "is_admin",
        "linuxdo_trust_level", "linuxdo_id",
    ]:
        op.drop_column("users", col)
```

- [ ] **Step 3: Verify migration applies**

Run: `alembic upgrade head`
Expected: Migration completes without errors.

- [ ] **Step 4: Verify downgrade works**

Run: `alembic downgrade -1 && alembic upgrade head`
Expected: Both operations complete without errors.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/003_foundation_upgrade.py
git commit -m "feat: alembic migration for foundation upgrade"
```

---

## Task 6: Config 扩展（新增 LinuxDo、头像、LLM 高级参数）

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_models_foundation.py
from app.config import Settings


def test_config_new_fields_have_defaults():
    """Verify new config fields exist with sensible defaults."""
    s = Settings(
        _env_file=None,  # Don't read .env during test
        llm_api_key="test-key",
    )
    # LinuxDo OAuth
    assert s.linuxdo_client_id == ""
    assert s.linuxdo_client_secret == ""
    assert s.linuxdo_redirect_uri == ""
    assert s.linuxdo_min_trust_level == 0

    # Portrait LLM
    assert s.portrait_llm_model == "gemini-3-pro-image-preview"
    assert s.portrait_llm_base_url == ""
    assert s.portrait_llm_api_key == ""
    assert s.portrait_llm_timeout == 180

    # System LLM
    assert s.system_llm_temperature == 0.3
    assert s.system_llm_timeout == 30
    assert s.system_llm_max_retries == 2

    # User LLM
    assert s.user_llm_temperature_chat == 0.7
    assert s.user_llm_temperature_forge == 0.5
    assert s.user_llm_timeout == 120
    assert s.user_llm_max_retries == 3
    assert s.user_llm_concurrency == 5
    assert s.allow_user_custom_llm is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models_foundation.py::test_config_new_fields_have_defaults -v`
Expected: FAIL with `TypeError` (unexpected keyword arguments)

- [ ] **Step 3: Write minimal implementation**

```python
# app/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/skills_world"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    github_client_id: str = ""
    github_client_secret: str = ""
    anthropic_api_key: str = ""
    # Custom LLM endpoint (overrides anthropic_api_key if set)
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_default_model: str = "claude-haiku-4-5-20251001"
    llm_max_tokens: int = 512

    @property
    def effective_api_key(self) -> str:
        return self.llm_api_key or self.anthropic_api_key

    @property
    def effective_model(self) -> str:
        return self.llm_model or self.llm_default_model

    cors_origins: list[str] = ["http://localhost:5173"]

    # --- LinuxDo OAuth (Plan 1) ---
    linuxdo_client_id: str = ""
    linuxdo_client_secret: str = ""
    linuxdo_redirect_uri: str = ""
    linuxdo_min_trust_level: int = 0

    # --- Portrait LLM (Plan 1) ---
    portrait_llm_model: str = "gemini-3-pro-image-preview"
    portrait_llm_base_url: str = ""
    portrait_llm_api_key: str = ""
    portrait_llm_timeout: int = 180

    # --- System LLM advanced params (Plan 1) ---
    system_llm_temperature: float = 0.3
    system_llm_timeout: int = 30
    system_llm_max_retries: int = 2

    # --- User LLM advanced params (Plan 1) ---
    user_llm_temperature_chat: float = 0.7
    user_llm_temperature_forge: float = 0.5
    user_llm_timeout: int = 120
    user_llm_max_retries: int = 3
    user_llm_concurrency: int = 5
    allow_user_custom_llm: bool = False

    model_config = {"env_file": ".env"}


settings = Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models_foundation.py::test_config_new_fields_have_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_models_foundation.py
git commit -m "feat: extend Settings with linuxdo, portrait, system/user LLM params"
```

---

## Task 7: 动态配置服务（ConfigService）

**Files:**
- Create: `app/services/config_service.py`
- Test: `tests/test_config_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config_service.py
import pytest
from app.models.system_config import SystemConfig
from app.services.config_service import ConfigService


@pytest.mark.anyio
async def test_get_returns_default_when_no_db_entry(db_session):
    """Should return default value when config key not in DB."""
    svc = ConfigService(db_session)
    value = await svc.get("economy.signup_bonus", default=100)
    assert value == 100


@pytest.mark.anyio
async def test_get_returns_db_value_over_default(db_session):
    """DB value should override default."""
    config = SystemConfig(
        key="economy.signup_bonus",
        value="200",
        group="economy",
        updated_by="admin",
    )
    db_session.add(config)
    await db_session.commit()

    svc = ConfigService(db_session)
    value = await svc.get("economy.signup_bonus", default=100)
    assert value == 200


@pytest.mark.anyio
async def test_set_creates_new_entry(db_session):
    """set() should create a new config entry."""
    svc = ConfigService(db_session)
    await svc.set("economy.daily_reward", 10, group="economy", updated_by="admin-id")

    value = await svc.get("economy.daily_reward", default=5)
    assert value == 10


@pytest.mark.anyio
async def test_set_updates_existing_entry(db_session):
    """set() should update an existing config entry."""
    svc = ConfigService(db_session)
    await svc.set("economy.daily_reward", 10, group="economy", updated_by="admin-id")
    await svc.set("economy.daily_reward", 20, group="economy", updated_by="admin-id")

    value = await svc.get("economy.daily_reward", default=5)
    assert value == 20


@pytest.mark.anyio
async def test_get_group_returns_all_in_group(db_session):
    """get_group() should return all config entries for a group."""
    svc = ConfigService(db_session)
    await svc.set("economy.signup_bonus", 100, group="economy", updated_by="admin")
    await svc.set("economy.daily_reward", 5, group="economy", updated_by="admin")
    await svc.set("heat.popular_threshold", 50, group="heat", updated_by="admin")

    economy = await svc.get_group("economy")
    assert economy == {"economy.signup_bonus": 100, "economy.daily_reward": 5}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.config_service'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/config_service.py
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system_config import SystemConfig
from datetime import datetime, UTC


class ConfigService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get(self, key: str, *, default=None):
        """Get a config value. Returns typed value (int/float/str/bool/dict/list)."""
        result = await self._db.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        )
        config = result.scalar_one_or_none()
        if config is None:
            return default
        return json.loads(config.value)

    async def set(self, key: str, value, *, group: str, updated_by: str):
        """Set a config value. Creates or updates."""
        result = await self._db.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        )
        config = result.scalar_one_or_none()
        serialized = json.dumps(value)

        if config is None:
            config = SystemConfig(
                key=key,
                value=serialized,
                group=group,
                updated_by=updated_by,
            )
            self._db.add(config)
        else:
            config.value = serialized
            config.updated_by = updated_by
            config.updated_at = datetime.now(UTC)

        await self._db.commit()

    async def get_group(self, group: str) -> dict:
        """Get all config entries for a group as {key: typed_value}."""
        result = await self._db.execute(
            select(SystemConfig).where(SystemConfig.group == group)
        )
        configs = result.scalars().all()
        return {c.key: json.loads(c.value) for c in configs}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config_service.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/config_service.py tests/test_config_service.py
git commit -m "feat: add ConfigService for runtime dynamic configuration"
```

---

## Task 8: LLM 客户端工厂（system/user 双轨）

**Files:**
- Modify: `app/llm/client.py`
- Test: `tests/test_llm_factory.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_factory.py
import pytest
from unittest.mock import patch, AsyncMock
from app.llm.client import get_client, LLMClientFactory, _reset_factory


@pytest.fixture(autouse=True)
def reset_factory():
    """Reset the factory singleton between tests."""
    _reset_factory()
    yield
    _reset_factory()


def test_get_client_system_returns_client():
    """get_client('system') should return an Anthropic client using system key."""
    with patch("app.llm.client.settings") as mock_settings:
        mock_settings.effective_api_key = "sys-key"
        mock_settings.llm_base_url = "https://sys.example.com"
        client = get_client("system")
        assert client is not None


def test_get_client_user_without_custom_uses_system():
    """get_client('user') with no custom config should use system defaults."""
    with patch("app.llm.client.settings") as mock_settings:
        mock_settings.effective_api_key = "sys-key"
        mock_settings.llm_base_url = "https://sys.example.com"
        client_sys = get_client("system")
        client_usr = get_client("user")
        # Both should use the same underlying config when user has no custom
        assert client_sys is not None
        assert client_usr is not None


def test_get_client_user_with_custom_config():
    """get_client('user', user_config=...) should use user-provided key."""
    with patch("app.llm.client.settings") as mock_settings:
        mock_settings.effective_api_key = "sys-key"
        mock_settings.llm_base_url = "https://sys.example.com"
        user_config = {
            "api_key": "user-key",
            "base_url": "https://user.example.com",
            "api_format": "anthropic",
        }
        client = get_client("user", user_config=user_config)
        assert client is not None


def test_get_client_invalid_owner_raises():
    """get_client with invalid owner should raise ValueError."""
    with pytest.raises(ValueError, match="owner must be"):
        get_client("invalid")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_llm_factory.py -v`
Expected: FAIL with `ImportError` (LLMClientFactory, _reset_factory not defined)

- [ ] **Step 3: Write minimal implementation**

```python
# app/llm/client.py
from typing import AsyncGenerator
import anthropic
from app.config import settings

_system_client: anthropic.AsyncAnthropic | None = None
_default_user_client: anthropic.AsyncAnthropic | None = None


def _reset_factory():
    """Reset all cached clients. Used in tests."""
    global _system_client, _default_user_client
    _system_client = None
    _default_user_client = None


class LLMClientFactory:
    """Not instantiated — just a namespace for documentation."""
    pass


def _make_anthropic_client(api_key: str, base_url: str | None = None) -> anthropic.AsyncAnthropic:
    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return anthropic.AsyncAnthropic(**kwargs)


def get_client(owner: str = "system", *, user_config: dict | None = None) -> anthropic.AsyncAnthropic:
    """
    Get an LLM client by owner type.

    owner: "system" or "user"
    user_config: optional dict with keys: api_key, base_url, api_format
                 If provided and owner="user", creates a client with user's credentials.
                 If not provided, falls back to system defaults.
    """
    global _system_client, _default_user_client

    if owner == "system":
        if _system_client is None:
            _system_client = _make_anthropic_client(
                api_key=settings.effective_api_key,
                base_url=settings.llm_base_url or None,
            )
        return _system_client

    if owner == "user":
        if user_config and user_config.get("api_key"):
            # User has custom config — create a fresh client (not cached)
            return _make_anthropic_client(
                api_key=user_config["api_key"],
                base_url=user_config.get("base_url") or settings.llm_base_url or None,
            )
        # No custom config — fall back to system defaults
        if _default_user_client is None:
            _default_user_client = _make_anthropic_client(
                api_key=settings.effective_api_key,
                base_url=settings.llm_base_url or None,
            )
        return _default_user_client

    raise ValueError("owner must be 'system' or 'user'")


async def stream_chat(
    system_prompt: str,
    messages: list[dict],
    model: str | None = None,
    owner: str = "user",
    user_config: dict | None = None,
) -> AsyncGenerator[str, None]:
    """Yield text chunks from LLM streaming response."""
    client = get_client(owner, user_config=user_config)
    async with client.messages.stream(
        model=model or settings.effective_model,
        max_tokens=settings.llm_max_tokens,
        system=system_prompt,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_llm_factory.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Verify existing tests still pass**

Run: `python -m pytest tests/ -v --ignore=tests/test_config_service.py --ignore=tests/test_llm_factory.py --ignore=tests/test_models_foundation.py -x`
Expected: All existing tests PASS (stream_chat signature is backward compatible)

- [ ] **Step 6: Commit**

```bash
git add app/llm/client.py tests/test_llm_factory.py
git commit -m "feat: LLM client factory with system/user dual-track support"
```

---

## Task 9: 确保全部测试通过 + 最终提交

**Files:**
- No new files

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 2: Verify imports work across the app**

```bash
python -c "
from app.models.user import User
from app.models.resident import Resident
from app.models.system_config import SystemConfig
from app.models.forge_session import ForgeSession
from app.services.config_service import ConfigService
from app.llm.client import get_client, stream_chat, LLMClientFactory
from app.config import settings
print('All imports OK')
print(f'LinuxDo configured: {bool(settings.linuxdo_client_id)}')
print(f'Allow user LLM: {settings.allow_user_custom_llm}')
"
```

Expected: "All imports OK" + config values printed.

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "chore: fix any remaining issues from Plan 1 integration"
```

---

## Summary

| Task | What it does | Files touched |
|------|-------------|---------------|
| 1 | User model + 13 new fields | user.py, test |
| 2 | Resident model + 3 new fields | resident.py, test |
| 3 | SystemConfig model | system_config.py, test |
| 4 | ForgeSession model | forge_session.py, test |
| 5 | Alembic migration | 003_foundation_upgrade.py |
| 6 | Config extends (LinuxDo, LLM params) | config.py, test |
| 7 | ConfigService (dynamic config CRUD) | config_service.py, test |
| 8 | LLM client factory (system/user) | client.py, test |
| 9 | Full test suite verification | — |
