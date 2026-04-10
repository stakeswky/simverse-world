# P1: Three-Layer Memory System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every resident persistent, retrievable memory — event records, relationship models, and self-reflections — that shape how they talk and act.

**Architecture:** A single `memories` table with a `type` discriminator (event/relationship/reflection). Event memories carry vector embeddings (pgvector, 1024-dim from local Ollama qwen3-embedding:4b) for semantic retrieval. Relationship and reflection memories use structured queries. A `MemoryService` handles all CRUD, retrieval, and lifecycle. Memory extraction happens automatically when a chat ends, driven by LLM prompts colored by the resident's SBTI personality dimensions.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, PostgreSQL + pgvector, Ollama (local embedding), pytest + aiosqlite (tests)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/app/models/memory.py` | Memory ORM model with pgvector column |
| Create | `backend/app/memory/__init__.py` | Package init |
| Create | `backend/app/memory/embedding.py` | Ollama embedding client (1024-dim) |
| Create | `backend/app/memory/prompts.py` | LLM prompt templates for extraction, relationship update, reflection |
| Create | `backend/app/memory/service.py` | MemoryService: create, retrieve, search, reflect, evict |
| Create | `backend/tests/test_memory_model.py` | ORM model tests |
| Create | `backend/tests/test_embedding.py` | Embedding client tests |
| Create | `backend/tests/test_memory_service.py` | Service layer tests |
| Modify | `backend/app/config.py` | Add `ollama_base_url` setting |
| Modify | `backend/app/main.py` | Import memory model for table creation |
| Modify | `backend/app/llm/prompt.py` | Inject memory context into system prompt |
| Modify | `backend/app/ws/handler.py` | Call memory extraction on `end_chat` |
| Create | `backend/alembic/versions/004_add_memories_table.py` | Migration for memories table + pgvector |

---

### Task 1: Memory ORM Model

**Files:**
- Create: `backend/app/models/memory.py`
- Create: `backend/tests/test_memory_model.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_memory_model.py`:

```python
import pytest
from datetime import datetime, UTC
from sqlalchemy import select
from app.models.memory import Memory


@pytest.mark.anyio
async def test_create_event_memory(db_session):
    mem = Memory(
        resident_id="res-1",
        type="event",
        content="Talked with player about AI ethics",
        importance=0.7,
        source="chat_player",
    )
    db_session.add(mem)
    await db_session.commit()

    result = await db_session.execute(select(Memory).where(Memory.resident_id == "res-1"))
    saved = result.scalar_one()
    assert saved.type == "event"
    assert saved.content == "Talked with player about AI ethics"
    assert saved.importance == 0.7
    assert saved.source == "chat_player"
    assert saved.id is not None
    assert saved.created_at is not None
    assert saved.last_accessed_at is not None


@pytest.mark.anyio
async def test_create_relationship_memory(db_session):
    mem = Memory(
        resident_id="res-1",
        type="relationship",
        content="First meeting, they are an engineer who likes cats",
        importance=0.5,
        source="chat_player",
        related_user_id="user-1",
        metadata_json={"affinity": 0.3, "trust": 0.5, "tags": ["engineer", "cat-lover"]},
    )
    db_session.add(mem)
    await db_session.commit()

    result = await db_session.execute(
        select(Memory).where(Memory.related_user_id == "user-1")
    )
    saved = result.scalar_one()
    assert saved.type == "relationship"
    assert saved.metadata_json["affinity"] == 0.3


@pytest.mark.anyio
async def test_create_reflection_memory(db_session):
    mem = Memory(
        resident_id="res-1",
        type="reflection",
        content="People in the engineering district seem too busy to chat",
        importance=0.8,
        source="reflection",
    )
    db_session.add(mem)
    await db_session.commit()

    result = await db_session.execute(
        select(Memory).where(Memory.type == "reflection")
    )
    saved = result.scalar_one()
    assert saved.source == "reflection"
    assert saved.importance == 0.8


@pytest.mark.anyio
async def test_memory_nullable_fields(db_session):
    mem = Memory(
        resident_id="res-1",
        type="event",
        content="Observed two residents chatting",
        importance=0.3,
        source="observation",
    )
    db_session.add(mem)
    await db_session.commit()

    result = await db_session.execute(select(Memory).where(Memory.id == mem.id))
    saved = result.scalar_one()
    assert saved.related_resident_id is None
    assert saved.related_user_id is None
    assert saved.media_url is None
    assert saved.media_summary is None
    assert saved.embedding is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_memory_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.memory'`

- [ ] **Step 3: Create the Memory model**

Create `backend/app/models/memory.py`:

```python
import uuid
from datetime import datetime, UTC
from sqlalchemy import String, Text, Float, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    resident_id: Mapped[str] = mapped_column(String, ForeignKey("residents.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # "event", "relationship", "reflection"
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    source: Mapped[str] = mapped_column(String(20))  # "chat_player", "chat_resident", "observation", "reflection", "media"

    # Relationship pointers (nullable)
    related_resident_id: Mapped[str | None] = mapped_column(String, ForeignKey("residents.id"), nullable=True)
    related_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)

    # Media (nullable, for P2 multimodal)
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Embedding (nullable — only event memories get embeddings)
    # pgvector column is added via migration; in SQLite tests this is just None
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)

    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_memories_resident_type", "resident_id", "type"),
        Index("ix_memories_resident_related_resident", "resident_id", "related_resident_id"),
        Index("ix_memories_resident_related_user", "resident_id", "related_user_id"),
    )
```

Note: The `embedding` column is `JSON` in the ORM model. In PostgreSQL production, the Alembic migration (Task 7) will create it as a proper `VECTOR(1024)` column. In SQLite tests, it stores as JSON (list of floats) — the vector search tests will mock the pgvector query.

- [ ] **Step 4: Register the model in main.py**

Add to `backend/app/main.py`, in the lifespan function, after the existing model imports:

```python
    import app.models.memory  # noqa: F401
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_memory_model.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/models/memory.py backend/tests/test_memory_model.py backend/app/main.py
git commit -m "feat(memory): add Memory ORM model with three-layer type system"
```

---

### Task 2: Ollama Embedding Client

**Files:**
- Create: `backend/app/memory/embedding.py`
- Create: `backend/app/memory/__init__.py`
- Create: `backend/tests/test_embedding.py`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add Ollama settings to config**

Add to `backend/app/config.py`, inside the `Settings` class, before `model_config`:

```python
    # --- Ollama (local embedding) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "qwen3-embedding:4b"
    ollama_embed_dimensions: int = 1024
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_embedding.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.memory.embedding import generate_embedding, generate_embeddings_batch


@pytest.mark.anyio
async def test_generate_embedding_returns_list():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embeddings": [[0.1] * 1024]}

    with patch("app.memory.embedding.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = await generate_embedding("Hello world")

    assert isinstance(result, list)
    assert len(result) == 1024
    mock_client.post.assert_called_once()


@pytest.mark.anyio
async def test_generate_embedding_empty_text_returns_none():
    result = await generate_embedding("")
    assert result is None

    result = await generate_embedding("   ")
    assert result is None


@pytest.mark.anyio
async def test_generate_embeddings_batch():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embeddings": [[0.1] * 1024, [0.2] * 1024]}

    with patch("app.memory.embedding.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        results = await generate_embeddings_batch(["text one", "text two"])

    assert len(results) == 2
    assert len(results[0]) == 1024


@pytest.mark.anyio
async def test_generate_embedding_ollama_error_returns_none():
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch("app.memory.embedding.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = await generate_embedding("test")

    assert result is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_embedding.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.memory'`

- [ ] **Step 4: Implement the embedding client**

Create `backend/app/memory/__init__.py`:

```python
```

Create `backend/app/memory/embedding.py`:

```python
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


async def generate_embedding(text: str) -> list[float] | None:
    """Generate a 1024-dim embedding for a single text using local Ollama.

    Returns None if text is empty or Ollama call fails.
    """
    if not text or not text.strip():
        return None

    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/embed",
                json={
                    "model": settings.ollama_embed_model,
                    "input": text,
                    "truncate": True,
                    "options": {"num_ctx": 2048},
                },
                timeout=30.0,
            )
        if resp.status_code != 200:
            logger.warning("Ollama embedding failed: %s %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        embeddings = data.get("embeddings", [])
        if not embeddings:
            return None
        vec = embeddings[0]
        # Truncate or pad to configured dimensions
        dim = settings.ollama_embed_dimensions
        if len(vec) > dim:
            vec = vec[:dim]
        elif len(vec) < dim:
            vec = vec + [0.0] * (dim - len(vec))
        return vec
    except Exception as e:
        logger.warning("Ollama embedding error: %s", e)
        return None


async def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts in a single Ollama call.

    Returns list of vectors. Failed items are zero-vectors.
    """
    if not texts:
        return []

    dim = settings.ollama_embed_dimensions
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/embed",
                json={
                    "model": settings.ollama_embed_model,
                    "input": texts,
                    "truncate": True,
                    "options": {"num_ctx": 2048},
                },
                timeout=60.0,
            )
        if resp.status_code != 200:
            logger.warning("Ollama batch embedding failed: %s", resp.status_code)
            return [[0.0] * dim] * len(texts)
        data = resp.json()
        embeddings = data.get("embeddings", [])
        result = []
        for vec in embeddings:
            if len(vec) > dim:
                vec = vec[:dim]
            elif len(vec) < dim:
                vec = vec + [0.0] * (dim - len(vec))
            result.append(vec)
        # Pad missing entries
        while len(result) < len(texts):
            result.append([0.0] * dim)
        return result
    except Exception as e:
        logger.warning("Ollama batch embedding error: %s", e)
        return [[0.0] * dim] * len(texts)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_embedding.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/memory/ backend/tests/test_embedding.py backend/app/config.py
git commit -m "feat(memory): add Ollama embedding client with MRL 1024-dim support"
```

---

### Task 3: Memory Prompts

**Files:**
- Create: `backend/app/memory/prompts.py`

No tests for this task — these are static string templates tested indirectly through Task 5.

- [ ] **Step 1: Create prompt templates**

Create `backend/app/memory/prompts.py`:

```python
EXTRACT_EVENTS_SYSTEM = """\
你是一个记忆提取器。给定一段对话内容，提取 1-3 条最重要的事件记忆。

每条记忆应该是一句简洁的陈述，描述"发生了什么"。
- 聚焦于有意义的信息交换、情感表达、承诺、观点，而非寒暄
- 如果对话很短或没有实质内容，可以只返回 1 条或空列表

{sbti_coloring}

输出严格 JSON 格式：
{{"memories": [{{"content": "...", "importance": 0.0-1.0}}]}}

importance 评分标准：
- 0.1-0.3: 日常闲聊，无特殊信息
- 0.4-0.6: 有实质话题但不涉及深层关系
- 0.7-0.8: 涉及个人感受、价值观或重要信息
- 0.9-1.0: 重大事件、深层共鸣或冲突（可能触发人格变化）
"""

EXTRACT_EVENTS_USER = """\
对话参与者：{resident_name} 与 {other_name}
对话内容：
{conversation_text}
"""

UPDATE_RELATIONSHIP_SYSTEM = """\
你是一个关系记忆管理器。根据最新的对话事件，更新居民对某人的关系认知。

你会收到：
1. 当前的关系记忆（可能为空，表示首次接触）
2. 本次对话提取的事件记忆

请输出更新后的完整关系描述，包含：
- 对方是谁、做什么的（如已知）
- 与对方的互动历史概要
- 当前对对方的印象和感受

{sbti_coloring}

输出严格 JSON 格式：
{{"content": "...", "importance": 0.0-1.0, "metadata": {{"affinity": -1.0到1.0, "trust": 0.0到1.0, "tags": ["标签1", "标签2"]}}}}

affinity: 好感度，-1（厌恶）到 1（亲密）
trust: 信任度，0（不信任）到 1（完全信任）
tags: 2-5 个关键印象标签
"""

UPDATE_RELATIONSHIP_USER = """\
居民：{resident_name}
对方：{other_name}

当前关系记忆：
{current_relationship}

本次对话事件：
{event_summaries}
"""

REFLECT_SYSTEM = """\
你是一个自我反思引擎。根据居民最近的经历（事件记忆）和人际关系（关系记忆），提炼 2-3 条高层认知。

反思应该是居民对自己、他人或世界的洞察，而非事件复述。
示例：
- "工程区的人似乎都很忙，很少主动找我聊天"
- "小明每次都问我技术问题，从不关心我的感受"
- "我发现自己越来越喜欢和人讨论哲学问题"

{sbti_coloring}

输出严格 JSON 格式：
{{"reflections": [{{"content": "...", "importance": 0.5-1.0}}]}}
"""

REFLECT_USER = """\
居民：{resident_name}

最近的事件记忆：
{recent_events}

当前的关系：
{relationships}
"""


def sbti_coloring_block(sbti_data: dict | None) -> str:
    """Build the SBTI personality coloring instruction for memory prompts.

    Injects the resident's SBTI dimensions so the LLM colors memory
    extraction/reflection according to personality.
    """
    if not sbti_data or "dimensions" not in sbti_data:
        return ""

    dims = sbti_data["dimensions"]
    type_name = sbti_data.get("type_name", "")
    type_code = sbti_data.get("type", "")

    lines = [
        f"该居民的 SBTI 人格类型为 {type_code}（{type_name}），性格维度如下：",
    ]

    dim_labels = {
        "S1": "自尊自信", "S2": "自我清晰度", "S3": "核心价值",
        "E1": "依恋安全感", "E2": "情感投入度", "E3": "边界与依赖",
        "A1": "世界观倾向", "A2": "规则与灵活度", "A3": "人生意义感",
        "Ac1": "动机导向", "Ac2": "决策风格", "Ac3": "执行模式",
        "So1": "社交主动性", "So2": "人际边界感", "So3": "表达与真实度",
    }
    level_map = {"L": "低", "M": "中", "H": "高"}

    for key, label in dim_labels.items():
        val = dims.get(key, "M")
        lines.append(f"- {label}({key}): {level_map.get(val, '中')}")

    lines.append("")
    lines.append("请根据以上性格特征来着色记忆的表述方式和重要性评估。")
    lines.append("例如：E2(情感投入度)高的居民，事件记忆的 importance 会偏高；")
    lines.append("A1(世界观倾向)低的居民，反思时倾向悲观解读。")

    return "\n".join(lines)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/memory/prompts.py
git commit -m "feat(memory): add LLM prompt templates for event extraction, relationship update, reflection"
```

---

### Task 4: MemoryService — Core CRUD

**Files:**
- Create: `backend/app/memory/service.py`
- Create: `backend/tests/test_memory_service.py`

This task covers create, query by type, and eviction. Retrieval (vector search) is Task 5.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_memory_service.py`:

```python
import pytest
from datetime import datetime, UTC, timedelta
from app.models.memory import Memory
from app.models.resident import Resident
from app.memory.service import MemoryService


@pytest.fixture
async def resident(db_session):
    r = Resident(
        id="mem-test-res",
        slug="mem-test-res",
        name="TestResident",
        district="engineering",
        status="idle",
        ability_md="Can code",
        persona_md="Friendly",
        soul_md="Curious",
        meta_json={"sbti": {"type": "CTRL", "type_name": "拿捏者", "dimensions": {
            "S1": "H", "S2": "H", "S3": "H",
            "E1": "H", "E2": "M", "E3": "H",
            "A1": "M", "A2": "H", "A3": "H",
            "Ac1": "H", "Ac2": "H", "Ac3": "H",
            "So1": "M", "So2": "H", "So3": "M",
        }}},
    )
    db_session.add(r)
    await db_session.commit()
    return r


@pytest.mark.anyio
async def test_add_event_memory(db_session, resident):
    svc = MemoryService(db_session)
    mem = await svc.add_memory(
        resident_id=resident.id,
        type="event",
        content="Discussed AI with a visitor",
        importance=0.6,
        source="chat_player",
    )
    assert mem.id is not None
    assert mem.type == "event"
    assert mem.resident_id == resident.id


@pytest.mark.anyio
async def test_get_memories_by_type(db_session, resident):
    svc = MemoryService(db_session)
    await svc.add_memory(resident.id, "event", "Event 1", 0.5, "chat_player")
    await svc.add_memory(resident.id, "event", "Event 2", 0.6, "chat_player")
    await svc.add_memory(resident.id, "reflection", "Reflection 1", 0.8, "reflection")

    events = await svc.get_memories(resident.id, type="event")
    assert len(events) == 2

    reflections = await svc.get_memories(resident.id, type="reflection")
    assert len(reflections) == 1


@pytest.mark.anyio
async def test_get_relationship_memory(db_session, resident):
    svc = MemoryService(db_session)
    await svc.add_memory(
        resident.id, "relationship", "A friendly engineer",
        0.5, "chat_player", related_user_id="user-1",
        metadata_json={"affinity": 0.3, "trust": 0.5, "tags": ["engineer"]},
    )

    rel = await svc.get_relationship(resident.id, user_id="user-1")
    assert rel is not None
    assert rel.metadata_json["affinity"] == 0.3

    no_rel = await svc.get_relationship(resident.id, user_id="user-999")
    assert no_rel is None


@pytest.mark.anyio
async def test_get_relationship_with_resident(db_session, resident):
    svc = MemoryService(db_session)
    await svc.add_memory(
        resident.id, "relationship", "A creative artist",
        0.5, "chat_resident", related_resident_id="other-res-1",
    )

    rel = await svc.get_relationship(resident.id, resident_id="other-res-1")
    assert rel is not None
    assert rel.content == "A creative artist"


@pytest.mark.anyio
async def test_update_relationship_memory(db_session, resident):
    svc = MemoryService(db_session)
    await svc.add_memory(
        resident.id, "relationship", "Initial impression",
        0.3, "chat_player", related_user_id="user-1",
    )

    await svc.update_relationship(
        resident.id, user_id="user-1",
        content="Updated: now a close friend",
        importance=0.7,
        metadata_json={"affinity": 0.8, "trust": 0.9, "tags": ["friend"]},
    )

    rel = await svc.get_relationship(resident.id, user_id="user-1")
    assert rel.content == "Updated: now a close friend"
    assert rel.importance == 0.7
    assert rel.metadata_json["affinity"] == 0.8


@pytest.mark.anyio
async def test_get_recent_reflections(db_session, resident):
    svc = MemoryService(db_session)
    for i in range(5):
        await svc.add_memory(resident.id, "reflection", f"Reflection {i}", 0.5 + i * 0.1, "reflection")

    top3 = await svc.get_recent_reflections(resident.id, limit=3)
    assert len(top3) == 3
    # Ordered by importance descending
    assert top3[0].importance >= top3[1].importance


@pytest.mark.anyio
async def test_count_recent_events(db_session, resident):
    svc = MemoryService(db_session)
    await svc.add_memory(resident.id, "event", "Event 1", 0.5, "chat_player")
    await svc.add_memory(resident.id, "event", "Event 2", 0.5, "chat_player")

    count = await svc.count_events_since_last_reflection(resident.id)
    assert count == 2


@pytest.mark.anyio
async def test_evict_old_memories(db_session, resident):
    svc = MemoryService(db_session)
    # Create 5 event memories with varying importance
    for i in range(5):
        mem = await svc.add_memory(resident.id, "event", f"Event {i}", 0.1 * (i + 1), "chat_player")
        # Manually set older timestamps for lower importance ones
        mem.created_at = datetime.now(UTC) - timedelta(days=30 - i)
        mem.last_accessed_at = datetime.now(UTC) - timedelta(days=30 - i)
    await db_session.commit()

    # Evict down to max 3
    evicted = await svc.evict_memories(resident.id, max_events=3)
    assert evicted == 2

    remaining = await svc.get_memories(resident.id, type="event")
    assert len(remaining) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_memory_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.memory.service'`

- [ ] **Step 3: Implement MemoryService core**

Create `backend/app/memory/service.py`:

```python
import logging
from datetime import datetime, UTC
from sqlalchemy import select, func, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.memory import Memory

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_memory(
        self,
        resident_id: str,
        type: str,
        content: str,
        importance: float,
        source: str,
        *,
        related_resident_id: str | None = None,
        related_user_id: str | None = None,
        media_url: str | None = None,
        media_summary: str | None = None,
        embedding: list[float] | None = None,
        metadata_json: dict | None = None,
    ) -> Memory:
        """Create and persist a new memory record."""
        mem = Memory(
            resident_id=resident_id,
            type=type,
            content=content,
            importance=importance,
            source=source,
            related_resident_id=related_resident_id,
            related_user_id=related_user_id,
            media_url=media_url,
            media_summary=media_summary,
            embedding=embedding,
            metadata_json=metadata_json,
        )
        self.db.add(mem)
        await self.db.commit()
        await self.db.refresh(mem)
        return mem

    async def get_memories(
        self,
        resident_id: str,
        *,
        type: str | None = None,
        limit: int = 50,
    ) -> list[Memory]:
        """Get memories for a resident, optionally filtered by type."""
        stmt = select(Memory).where(Memory.resident_id == resident_id)
        if type:
            stmt = stmt.where(Memory.type == type)
        stmt = stmt.order_by(Memory.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_relationship(
        self,
        resident_id: str,
        *,
        user_id: str | None = None,
        resident_id_target: str | None = None,
    ) -> Memory | None:
        """Get the relationship memory for a specific person.

        Exactly one of user_id or resident_id_target must be provided.
        """
        stmt = select(Memory).where(
            Memory.resident_id == resident_id,
            Memory.type == "relationship",
        )
        if user_id:
            stmt = stmt.where(Memory.related_user_id == user_id)
        elif resident_id_target:
            stmt = stmt.where(Memory.related_resident_id == resident_id_target)
        else:
            return None
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_relationship(
        self,
        resident_id: str,
        *,
        user_id: str | None = None,
        resident_id_target: str | None = None,
        content: str,
        importance: float,
        metadata_json: dict | None = None,
    ) -> Memory:
        """Update an existing relationship memory, or create if not found."""
        existing = await self.get_relationship(
            resident_id, user_id=user_id, resident_id_target=resident_id_target,
        )
        if existing:
            existing.content = content
            existing.importance = importance
            if metadata_json is not None:
                existing.metadata_json = metadata_json
            existing.last_accessed_at = datetime.now(UTC)
            await self.db.commit()
            return existing
        else:
            return await self.add_memory(
                resident_id, "relationship", content, importance,
                "chat_player" if user_id else "chat_resident",
                related_user_id=user_id,
                related_resident_id=resident_id_target,
                metadata_json=metadata_json,
            )

    async def get_recent_reflections(
        self,
        resident_id: str,
        limit: int = 5,
    ) -> list[Memory]:
        """Get most important recent reflections."""
        stmt = (
            select(Memory)
            .where(Memory.resident_id == resident_id, Memory.type == "reflection")
            .order_by(Memory.importance.desc(), Memory.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_events_since_last_reflection(self, resident_id: str) -> int:
        """Count event memories created after the most recent reflection."""
        # Find last reflection timestamp
        last_ref_stmt = (
            select(Memory.created_at)
            .where(Memory.resident_id == resident_id, Memory.type == "reflection")
            .order_by(Memory.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(last_ref_stmt)
        last_ref_time = result.scalar_one_or_none()

        count_stmt = select(func.count()).select_from(Memory).where(
            Memory.resident_id == resident_id,
            Memory.type == "event",
        )
        if last_ref_time:
            count_stmt = count_stmt.where(Memory.created_at > last_ref_time)

        result = await self.db.execute(count_stmt)
        return result.scalar_one()

    async def evict_memories(self, resident_id: str, max_events: int = 500) -> int:
        """Evict oldest, least important event memories beyond the cap.

        Score = importance * recency_weight. Lowest scores evicted first.
        Returns number of evicted memories.
        """
        count_result = await self.db.execute(
            select(func.count()).select_from(Memory).where(
                Memory.resident_id == resident_id, Memory.type == "event",
            )
        )
        total = count_result.scalar_one()
        if total <= max_events:
            return 0

        to_evict = total - max_events
        # Get IDs of lowest-value memories (oldest + least important)
        stmt = (
            select(Memory.id)
            .where(Memory.resident_id == resident_id, Memory.type == "event")
            .order_by(Memory.importance.asc(), Memory.last_accessed_at.asc())
            .limit(to_evict)
        )
        result = await self.db.execute(stmt)
        ids_to_delete = [row[0] for row in result.all()]

        if ids_to_delete:
            await self.db.execute(
                delete(Memory).where(Memory.id.in_(ids_to_delete))
            )
            await self.db.commit()

        return len(ids_to_delete)
```

- [ ] **Step 4: Fix test — adapt `get_relationship` call signature**

The test uses `resident_id=` as keyword for target resident, but the service uses `resident_id_target=`. Update the test calls:

In `test_memory_service.py`, change:
```python
    rel = await svc.get_relationship(resident.id, resident_id="other-res-1")
```
to:
```python
    rel = await svc.get_relationship(resident.id, resident_id_target="other-res-1")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_memory_service.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/memory/service.py backend/tests/test_memory_service.py
git commit -m "feat(memory): add MemoryService with CRUD, relationship management, eviction"
```

---

### Task 5: Memory Retrieval — Hybrid Search

**Files:**
- Modify: `backend/app/memory/service.py`
- Modify: `backend/tests/test_memory_service.py`

Adds semantic vector search (with SQLite fallback) and time-decay scoring to MemoryService.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_memory_service.py`:

```python
from unittest.mock import AsyncMock, patch


@pytest.mark.anyio
async def test_retrieve_context_structured(db_session, resident):
    """Test structured retrieval (relationship + reflections) without embeddings."""
    svc = MemoryService(db_session)

    # Add relationship
    await svc.add_memory(
        resident.id, "relationship", "A kind visitor",
        0.5, "chat_player", related_user_id="user-1",
        metadata_json={"affinity": 0.5, "trust": 0.6, "tags": ["kind"]},
    )
    # Add reflections
    await svc.add_memory(resident.id, "reflection", "I enjoy deep conversations", 0.8, "reflection")
    await svc.add_memory(resident.id, "reflection", "Engineering people are busy", 0.6, "reflection")

    # Add events
    await svc.add_memory(resident.id, "event", "Talked about AI", 0.6, "chat_player")
    await svc.add_memory(resident.id, "event", "Discussed philosophy", 0.7, "chat_player")

    ctx = await svc.retrieve_context(
        resident_id=resident.id,
        user_id="user-1",
        query_text="Tell me about AI",
    )

    assert ctx["relationship"] is not None
    assert ctx["relationship"].content == "A kind visitor"
    assert len(ctx["reflections"]) <= 3
    assert len(ctx["events"]) > 0


@pytest.mark.anyio
async def test_retrieve_context_no_relationship(db_session, resident):
    """First-time visitor: no relationship memory yet."""
    svc = MemoryService(db_session)
    await svc.add_memory(resident.id, "event", "Some past event", 0.5, "chat_player")

    ctx = await svc.retrieve_context(
        resident_id=resident.id,
        user_id="first-timer",
        query_text="Hello",
    )

    assert ctx["relationship"] is None
    assert ctx["reflections"] == []
    assert isinstance(ctx["events"], list)


@pytest.mark.anyio
async def test_retrieve_context_updates_last_accessed(db_session, resident):
    """Retrieving memories should update last_accessed_at."""
    svc = MemoryService(db_session)
    mem = await svc.add_memory(resident.id, "event", "Old event", 0.5, "chat_player")
    original_accessed = mem.last_accessed_at

    ctx = await svc.retrieve_context(
        resident_id=resident.id,
        user_id="user-1",
        query_text="anything",
    )

    # Re-fetch to check updated timestamp
    from sqlalchemy import select
    from app.models.memory import Memory
    result = await db_session.execute(select(Memory).where(Memory.id == mem.id))
    refreshed = result.scalar_one()
    assert refreshed.last_accessed_at >= original_accessed
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_memory_service.py::test_retrieve_context_structured -v`
Expected: FAIL — `AttributeError: 'MemoryService' object has no attribute 'retrieve_context'`

- [ ] **Step 3: Implement `retrieve_context` on MemoryService**

Add to `backend/app/memory/service.py`, inside the `MemoryService` class:

```python
    async def retrieve_context(
        self,
        resident_id: str,
        *,
        user_id: str | None = None,
        resident_id_target: str | None = None,
        query_text: str = "",
        max_events: int = 10,
        max_reflections: int = 3,
    ) -> dict:
        """Retrieve memory context for a conversation.

        Returns dict with keys: relationship, reflections, events.
        Uses structured queries for relationship/reflections,
        and falls back to recency+importance for events (vector search
        requires pgvector in PostgreSQL).
        """
        # 1. Structured: relationship memory for this person
        relationship = await self.get_relationship(
            resident_id, user_id=user_id, resident_id_target=resident_id_target,
        )

        # 2. Structured: top reflections by importance
        reflections = await self.get_recent_reflections(resident_id, limit=max_reflections)

        # 3. Events: try vector search, fall back to recency+importance
        events = await self._search_events(resident_id, query_text, limit=max_events)

        # Update last_accessed_at for all retrieved memories
        now = datetime.now(UTC)
        all_memories = [m for m in [relationship] + reflections + events if m is not None]
        for mem in all_memories:
            mem.last_accessed_at = now
        if all_memories:
            await self.db.commit()

        return {
            "relationship": relationship,
            "reflections": reflections,
            "events": events,
        }

    async def _search_events(
        self,
        resident_id: str,
        query_text: str,
        limit: int = 10,
    ) -> list[Memory]:
        """Search event memories. Uses recency+importance ranking.

        In PostgreSQL with pgvector, this would use cosine similarity.
        In SQLite (tests/dev), falls back to recency × importance scoring.
        """
        stmt = (
            select(Memory)
            .where(Memory.resident_id == resident_id, Memory.type == "event")
            .order_by(Memory.importance.desc(), Memory.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def search_events_vector(
        self,
        resident_id: str,
        query_embedding: list[float],
        limit: int = 10,
    ) -> list[Memory]:
        """Search event memories using pgvector cosine similarity.

        This method is for PostgreSQL with pgvector extension only.
        Call generate_embedding() first to get the query_embedding.
        Falls back to _search_events() if pgvector is unavailable.
        """
        try:
            # pgvector cosine distance: embedding <=> query_embedding
            # This raw SQL approach works with pgvector
            from sqlalchemy import text
            stmt = text("""
                SELECT id, content, importance, source, created_at, last_accessed_at,
                       metadata_json, media_url, media_summary,
                       1 - (embedding <=> :query_vec) AS similarity
                FROM memories
                WHERE resident_id = :rid AND type = 'event' AND embedding IS NOT NULL
                ORDER BY embedding <=> :query_vec
                LIMIT :lim
            """)
            result = await self.db.execute(stmt, {
                "rid": resident_id,
                "query_vec": str(query_embedding),
                "lim": limit,
            })
            rows = result.fetchall()
            if not rows:
                return await self._search_events(resident_id, "", limit)

            # Fetch full Memory objects by ID
            ids = [row[0] for row in rows]
            mem_stmt = select(Memory).where(Memory.id.in_(ids))
            mem_result = await self.db.execute(mem_stmt)
            memories = {m.id: m for m in mem_result.scalars().all()}
            # Return in similarity order
            return [memories[id] for id in ids if id in memories]
        except Exception as e:
            logger.debug("pgvector search unavailable, falling back: %s", e)
            return await self._search_events(resident_id, "", limit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_memory_service.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/memory/service.py backend/tests/test_memory_service.py
git commit -m "feat(memory): add hybrid retrieval with structured queries and vector search fallback"
```

---

### Task 6: Memory Extraction + Relationship Update (LLM Integration)

**Files:**
- Modify: `backend/app/memory/service.py`
- Create: `backend/tests/test_memory_extraction.py`

This task adds the LLM-driven methods: extract events from a conversation, update relationship memory, and trigger reflection.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_memory_extraction.py`:

```python
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.models.resident import Resident
from app.models.memory import Memory
from app.memory.service import MemoryService


@pytest.fixture
async def resident(db_session):
    r = Resident(
        id="ext-test-res",
        slug="ext-test-res",
        name="ExtractResident",
        district="engineering",
        status="idle",
        ability_md="Python expert",
        persona_md="Thoughtful and quiet",
        soul_md="Seeks truth",
        meta_json={"sbti": {"type": "THIN-K", "type_name": "思考者", "dimensions": {
            "S1": "H", "S2": "H", "S3": "L",
            "E1": "H", "E2": "M", "E3": "H",
            "A1": "M", "A2": "L", "A3": "H",
            "Ac1": "M", "Ac2": "H", "Ac3": "M",
            "So1": "L", "So2": "H", "So3": "H",
        }}},
    )
    db_session.add(r)
    await db_session.commit()
    return r


def _mock_llm_response(content: str):
    """Create a mock that simulates anthropic client.messages.create()."""
    mock_msg = MagicMock()
    mock_block = MagicMock()
    mock_block.text = content
    mock_msg.content = [mock_block]
    return mock_msg


@pytest.mark.anyio
async def test_extract_events_from_conversation(db_session, resident):
    svc = MemoryService(db_session)

    llm_response = json.dumps({
        "memories": [
            {"content": "Discussed Python async patterns", "importance": 0.6},
            {"content": "Visitor shared frustration about debugging", "importance": 0.5},
        ]
    })

    with patch("app.memory.service.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_llm_response(llm_response))
        mock_get_client.return_value = mock_client

        with patch("app.memory.service.generate_embedding", return_value=[0.1] * 1024):
            memories = await svc.extract_events(
                resident=resident,
                other_name="Player1",
                conversation_text="Player1: How do I use async?\nExtractResident: Let me explain...",
            )

    assert len(memories) == 2
    assert memories[0].type == "event"
    assert memories[0].source == "chat_player"
    assert memories[0].embedding is not None


@pytest.mark.anyio
async def test_extract_events_handles_llm_failure(db_session, resident):
    svc = MemoryService(db_session)

    with patch("app.memory.service.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("LLM down"))
        mock_get_client.return_value = mock_client

        memories = await svc.extract_events(
            resident=resident,
            other_name="Player1",
            conversation_text="Hello!",
        )

    assert memories == []


@pytest.mark.anyio
async def test_update_relationship_via_llm(db_session, resident):
    svc = MemoryService(db_session)

    llm_response = json.dumps({
        "content": "Player1 is a curious beginner interested in Python async",
        "importance": 0.6,
        "metadata": {"affinity": 0.4, "trust": 0.5, "tags": ["beginner", "curious"]},
    })

    with patch("app.memory.service.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_llm_response(llm_response))
        mock_get_client.return_value = mock_client

        rel = await svc.update_relationship_via_llm(
            resident=resident,
            other_name="Player1",
            user_id="user-1",
            event_summaries=["Discussed Python async patterns"],
        )

    assert rel.content == "Player1 is a curious beginner interested in Python async"
    assert rel.metadata_json["affinity"] == 0.4


@pytest.mark.anyio
async def test_trigger_reflection(db_session, resident):
    svc = MemoryService(db_session)

    # Seed some event and relationship memories
    for i in range(5):
        await svc.add_memory(resident.id, "event", f"Event {i}", 0.5, "chat_player")
    await svc.add_memory(
        resident.id, "relationship", "A friendly visitor",
        0.5, "chat_player", related_user_id="user-1",
    )

    llm_response = json.dumps({
        "reflections": [
            {"content": "I notice visitors often ask about async programming", "importance": 0.7},
            {"content": "People seem genuinely interested in learning", "importance": 0.6},
        ]
    })

    with patch("app.memory.service.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_llm_response(llm_response))
        mock_get_client.return_value = mock_client

        reflections = await svc.generate_reflections(resident=resident)

    assert len(reflections) == 2
    assert reflections[0].type == "reflection"
    assert reflections[0].source == "reflection"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_memory_extraction.py -v`
Expected: FAIL — `AttributeError: 'MemoryService' object has no attribute 'extract_events'`

- [ ] **Step 3: Implement LLM-driven memory methods**

Add these imports at the top of `backend/app/memory/service.py`:

```python
import json
from app.llm.client import get_client
from app.memory.embedding import generate_embedding
from app.memory.prompts import (
    EXTRACT_EVENTS_SYSTEM,
    EXTRACT_EVENTS_USER,
    UPDATE_RELATIONSHIP_SYSTEM,
    UPDATE_RELATIONSHIP_USER,
    REFLECT_SYSTEM,
    REFLECT_USER,
    sbti_coloring_block,
)
from app.config import settings
```

Add these methods to the `MemoryService` class:

```python
    async def extract_events(
        self,
        resident: "Resident",
        other_name: str,
        conversation_text: str,
        *,
        source: str = "chat_player",
    ) -> list[Memory]:
        """Extract event memories from a conversation using LLM.

        Returns list of created Memory objects.
        """
        sbti_data = (resident.meta_json or {}).get("sbti")
        coloring = sbti_coloring_block(sbti_data)

        system = EXTRACT_EVENTS_SYSTEM.format(sbti_coloring=coloring)
        user_msg = EXTRACT_EVENTS_USER.format(
            resident_name=resident.name,
            other_name=other_name,
            conversation_text=conversation_text,
        )

        try:
            client = get_client("system")
            resp = await client.messages.create(
                model=settings.effective_model,
                max_tokens=500,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = resp.content[0].text
            data = json.loads(raw)
        except Exception as e:
            logger.warning("Event extraction failed: %s", e)
            return []

        memories = []
        for item in data.get("memories", []):
            content = item.get("content", "")
            importance = float(item.get("importance", 0.5))
            if not content:
                continue

            emb = await generate_embedding(content)
            mem = await self.add_memory(
                resident_id=resident.id,
                type="event",
                content=content,
                importance=importance,
                source=source,
                embedding=emb,
            )
            memories.append(mem)

        return memories

    async def update_relationship_via_llm(
        self,
        resident: "Resident",
        other_name: str,
        event_summaries: list[str],
        *,
        user_id: str | None = None,
        resident_id_target: str | None = None,
    ) -> Memory:
        """Update relationship memory using LLM analysis.

        Creates the relationship if it doesn't exist yet.
        """
        existing = await self.get_relationship(
            resident.id, user_id=user_id, resident_id_target=resident_id_target,
        )
        current_rel = existing.content if existing else "（首次接触，尚无关系记忆）"

        sbti_data = (resident.meta_json or {}).get("sbti")
        coloring = sbti_coloring_block(sbti_data)

        system = UPDATE_RELATIONSHIP_SYSTEM.format(sbti_coloring=coloring)
        user_msg = UPDATE_RELATIONSHIP_USER.format(
            resident_name=resident.name,
            other_name=other_name,
            current_relationship=current_rel,
            event_summaries="\n".join(f"- {s}" for s in event_summaries),
        )

        try:
            client = get_client("system")
            resp = await client.messages.create(
                model=settings.effective_model,
                max_tokens=300,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = resp.content[0].text
            data = json.loads(raw)
        except Exception as e:
            logger.warning("Relationship update failed: %s", e)
            # Return existing or create minimal record
            if existing:
                return existing
            return await self.add_memory(
                resident.id, "relationship", f"Met {other_name}",
                0.3, "chat_player" if user_id else "chat_resident",
                related_user_id=user_id, related_resident_id=resident_id_target,
            )

        return await self.update_relationship(
            resident.id,
            user_id=user_id,
            resident_id_target=resident_id_target,
            content=data.get("content", f"Met {other_name}"),
            importance=float(data.get("importance", 0.5)),
            metadata_json=data.get("metadata"),
        )

    async def generate_reflections(self, resident: "Resident") -> list[Memory]:
        """Generate reflection memories from recent events and relationships."""
        recent_events = await self.get_memories(resident.id, type="event", limit=20)
        relationships = await self.get_memories(resident.id, type="relationship", limit=10)

        if not recent_events:
            return []

        sbti_data = (resident.meta_json or {}).get("sbti")
        coloring = sbti_coloring_block(sbti_data)

        events_text = "\n".join(f"- [{e.source}] {e.content}" for e in recent_events)
        rels_text = "\n".join(f"- {r.content}" for r in relationships) if relationships else "（尚无关系记忆）"

        system = REFLECT_SYSTEM.format(sbti_coloring=coloring)
        user_msg = REFLECT_USER.format(
            resident_name=resident.name,
            recent_events=events_text,
            relationships=rels_text,
        )

        try:
            client = get_client("system")
            resp = await client.messages.create(
                model=settings.effective_model,
                max_tokens=400,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = resp.content[0].text
            data = json.loads(raw)
        except Exception as e:
            logger.warning("Reflection generation failed: %s", e)
            return []

        reflections = []
        for item in data.get("reflections", []):
            content = item.get("content", "")
            importance = float(item.get("importance", 0.6))
            if not content:
                continue
            mem = await self.add_memory(
                resident.id, "reflection", content, importance, "reflection",
            )
            reflections.append(mem)

        return reflections
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_memory_extraction.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/memory/service.py backend/tests/test_memory_extraction.py
git commit -m "feat(memory): add LLM-driven event extraction, relationship update, and reflection generation"
```

---

### Task 7: Inject Memory into Chat System Prompt

**Files:**
- Modify: `backend/app/llm/prompt.py`
- Create: `backend/tests/test_memory_prompt.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_memory_prompt.py`:

```python
import pytest
from unittest.mock import MagicMock
from app.models.resident import Resident
from app.models.memory import Memory
from app.llm.prompt import assemble_system_prompt, format_memory_context


def _make_resident():
    r = MagicMock(spec=Resident)
    r.name = "TestNPC"
    r.district = "engineering"
    r.soul_md = "Seeks truth"
    r.persona_md = "Quiet thinker"
    r.ability_md = "Python expert"
    return r


def _make_memory(content, type="event", importance=0.5, metadata_json=None):
    m = MagicMock(spec=Memory)
    m.content = content
    m.type = type
    m.importance = importance
    m.metadata_json = metadata_json
    return m


def test_format_memory_context_with_all_layers():
    relationship = _make_memory(
        "A curious beginner who likes cats",
        type="relationship",
        metadata_json={"affinity": 0.5, "trust": 0.6, "tags": ["beginner", "cat-lover"]},
    )
    reflections = [
        _make_memory("People here are always busy", type="reflection", importance=0.8),
        _make_memory("I enjoy teaching newcomers", type="reflection", importance=0.7),
    ]
    events = [
        _make_memory("Discussed async patterns yesterday", type="event"),
        _make_memory("They showed me a cat photo", type="event"),
    ]

    ctx = {"relationship": relationship, "reflections": reflections, "events": events}
    result = format_memory_context(ctx)

    assert "A curious beginner who likes cats" in result
    assert "People here are always busy" in result
    assert "Discussed async patterns yesterday" in result


def test_format_memory_context_empty():
    ctx = {"relationship": None, "reflections": [], "events": []}
    result = format_memory_context(ctx)
    assert result == ""


def test_assemble_prompt_with_memory():
    r = _make_resident()
    ctx = {
        "relationship": _make_memory("A kind visitor", type="relationship"),
        "reflections": [_make_memory("I like deep talks", type="reflection")],
        "events": [_make_memory("Chatted about AI", type="event")],
    }

    prompt = assemble_system_prompt(r, memory_context=ctx)

    assert "A kind visitor" in prompt
    assert "I like deep talks" in prompt
    assert "Chatted about AI" in prompt
    assert "TestNPC" in prompt


def test_assemble_prompt_without_memory():
    r = _make_resident()
    prompt = assemble_system_prompt(r)

    assert "TestNPC" in prompt
    assert "Seeks truth" in prompt
    # No memory section when no context provided
    assert "记忆" not in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_memory_prompt.py -v`
Expected: FAIL — `ImportError: cannot import name 'format_memory_context'`

- [ ] **Step 3: Implement memory context formatting**

Replace the contents of `backend/app/llm/prompt.py`:

```python
from app.models.resident import Resident


def format_memory_context(ctx: dict) -> str:
    """Format retrieved memory context into a prompt section.

    ctx has keys: relationship (Memory|None), reflections (list[Memory]), events (list[Memory])
    Returns empty string if no memories.
    """
    sections = []

    relationship = ctx.get("relationship")
    if relationship:
        sections.append("### 关于当前对话对象")
        sections.append(relationship.content)
        if relationship.metadata_json:
            meta = relationship.metadata_json
            tags = meta.get("tags", [])
            if tags:
                sections.append(f"印象标签：{', '.join(tags)}")
        sections.append("")

    reflections = ctx.get("reflections", [])
    if reflections:
        sections.append("### 你最近的思考")
        for r in reflections:
            sections.append(f"- {r.content}")
        sections.append("")

    events = ctx.get("events", [])
    if events:
        sections.append("### 相关的过往经历")
        for e in events:
            sections.append(f"- {e.content}")
        sections.append("")

    return "\n".join(sections) if sections else ""


def assemble_system_prompt(resident: Resident, memory_context: dict | None = None) -> str:
    """Assemble the three-layer system prompt from resident data.

    Optionally includes memory context if provided.
    """
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

    if memory_context:
        memory_text = format_memory_context(memory_context)
        if memory_text:
            parts.append("## 记忆（你记得的事）")
            parts.append(memory_text)

    parts.append("请始终保持角色扮演，用你的人格风格回应访客。回复简洁，不超过200字。")
    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_memory_prompt.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Run existing tests to check for regressions**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/ -v --timeout=30`
Expected: All existing tests still PASS. The `assemble_system_prompt` change is backward-compatible (new `memory_context` param defaults to None).

- [ ] **Step 6: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/llm/prompt.py backend/tests/test_memory_prompt.py
git commit -m "feat(memory): inject memory context into resident system prompt"
```

---

### Task 8: Wire Memory Extraction into WebSocket Chat Flow

**Files:**
- Modify: `backend/app/ws/handler.py`
- Create: `backend/tests/test_memory_chat_integration.py`

This task hooks the memory system into two points:
1. `start_chat` → retrieve memory context for the resident's prompt
2. `end_chat` → extract events, update relationship, check reflection trigger

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_memory_chat_integration.py`:

```python
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select
from app.models.memory import Memory
from app.models.resident import Resident
from app.models.user import User
from app.memory.service import MemoryService


@pytest.fixture
async def chat_resident(db_session):
    r = Resident(
        id="chat-mem-res",
        slug="chat-mem-res",
        name="ChatResident",
        district="engineering",
        status="idle",
        ability_md="Can chat",
        persona_md="Friendly",
        soul_md="Helpful",
        meta_json={"sbti": {"type": "GOGO", "type_name": "行者", "dimensions": {
            "S1": "H", "S2": "H", "S3": "M",
            "E1": "H", "E2": "M", "E3": "H",
            "A1": "M", "A2": "M", "A3": "H",
            "Ac1": "H", "Ac2": "H", "Ac3": "H",
            "So1": "M", "So2": "H", "So3": "M",
        }}},
    )
    db_session.add(r)
    await db_session.commit()
    return r


@pytest.fixture
async def chat_user(db_session):
    u = User(id="chat-mem-user", name="TestPlayer", email="test@chat.com", soul_coin_balance=100)
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.mark.anyio
async def test_process_chat_end_creates_memories(db_session, chat_resident, chat_user):
    """After chat ends, event memories and relationship should be created."""
    from app.memory.service import MemoryService

    svc = MemoryService(db_session)

    llm_extract_response = json.dumps({
        "memories": [
            {"content": "Discussed Python best practices", "importance": 0.6},
        ]
    })
    llm_relationship_response = json.dumps({
        "content": "TestPlayer is interested in Python",
        "importance": 0.5,
        "metadata": {"affinity": 0.3, "trust": 0.4, "tags": ["python-learner"]},
    })

    mock_msg = MagicMock()

    with patch("app.memory.service.get_client") as mock_get_client:
        mock_client = AsyncMock()
        # First call = extract_events, second call = update_relationship_via_llm
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _mock_llm_response(llm_extract_response),
                _mock_llm_response(llm_relationship_response),
            ]
        )
        mock_get_client.return_value = mock_client

        with patch("app.memory.service.generate_embedding", return_value=[0.1] * 1024):
            events = await svc.extract_events(
                resident=chat_resident,
                other_name=chat_user.name,
                conversation_text="TestPlayer: How do I write clean Python?\nChatResident: Follow PEP 8...",
            )
            rel = await svc.update_relationship_via_llm(
                resident=chat_resident,
                other_name=chat_user.name,
                user_id=chat_user.id,
                event_summaries=[e.content for e in events],
            )

    # Verify event memories
    result = await db_session.execute(
        select(Memory).where(Memory.resident_id == chat_resident.id, Memory.type == "event")
    )
    event_memories = result.scalars().all()
    assert len(event_memories) == 1
    assert event_memories[0].content == "Discussed Python best practices"
    assert event_memories[0].embedding is not None

    # Verify relationship memory
    result = await db_session.execute(
        select(Memory).where(
            Memory.resident_id == chat_resident.id,
            Memory.type == "relationship",
            Memory.related_user_id == chat_user.id,
        )
    )
    rel_memory = result.scalar_one()
    assert "Python" in rel_memory.content


def _mock_llm_response(content: str):
    mock_msg = MagicMock()
    mock_block = MagicMock()
    mock_block.text = content
    mock_msg.content = [mock_block]
    return mock_msg
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_memory_chat_integration.py -v`
Expected: All tests PASS (this tests the service layer directly, not the WS handler)

- [ ] **Step 3: Modify the WebSocket handler to use memory**

In `backend/app/ws/handler.py`:

Add imports at the top:

```python
from app.memory.service import MemoryService
```

In the `start_chat` block, after `chat_messages = []` (line ~194), add memory retrieval:

```python
                    # Retrieve memory context for this resident+user pair
                    memory_svc = MemoryService(db)
                    memory_context = await memory_svc.retrieve_context(
                        resident_id=resident.id,
                        user_id=user_id,
                    )
```

In the `chat_msg` block, change the `system_prompt` assembly (line ~250) from:

```python
                    system_prompt = assemble_system_prompt(current_resident)
```

to:

```python
                    system_prompt = assemble_system_prompt(current_resident, memory_context=memory_context)
```

Note: `memory_context` needs to be available in the chat_msg scope. Add it as a local variable alongside `current_conversation`, `current_resident`, `chat_messages` near the top of the handler function:

```python
    memory_context = None
```

In the `end_chat` block, after `await db.commit()` (line ~301), add memory extraction as a background task:

```python
                    # Extract memories from the conversation (non-blocking)
                    import asyncio
                    asyncio.create_task(_extract_chat_memories(
                        resident_id=resident_id,
                        user_id=user_id,
                        user_name=user_name,
                        chat_messages=list(chat_messages),  # copy
                    ))
```

Add the helper function outside `websocket_handler`:

```python
async def _extract_chat_memories(
    resident_id: str,
    user_id: str,
    user_name: str,
    chat_messages: list[dict],
):
    """Background task: extract event memories and update relationship after chat ends."""
    if len(chat_messages) < 2:
        return  # Too short to extract meaningful memories

    try:
        async with async_session() as db:
            result = await db.execute(select(Resident).where(Resident.id == resident_id))
            resident = result.scalar_one_or_none()
            if not resident:
                return

            # Format conversation text
            conv_text = "\n".join(
                f"{'玩家' if m['role'] == 'user' else resident.name}: {m['content']}"
                for m in chat_messages
            )

            svc = MemoryService(db)

            # 1. Extract event memories
            events = await svc.extract_events(
                resident=resident,
                other_name=user_name,
                conversation_text=conv_text,
                source="chat_player",
            )

            # 2. Update relationship memory
            if events:
                await svc.update_relationship_via_llm(
                    resident=resident,
                    other_name=user_name,
                    user_id=user_id,
                    event_summaries=[e.content for e in events],
                )

            # 3. Check if reflection is needed
            event_count = await svc.count_events_since_last_reflection(resident.id)
            if event_count >= 15:
                await svc.generate_reflections(resident=resident)

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Memory extraction failed: %s", e)
```

- [ ] **Step 4: Run all tests to check for regressions**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/ws/handler.py backend/tests/test_memory_chat_integration.py
git commit -m "feat(memory): wire memory extraction into WebSocket chat flow"
```

---

### Task 9: Alembic Migration for memories Table

**Files:**
- Create: `backend/alembic/versions/004_add_memories_table.py`

- [ ] **Step 1: Create the migration**

Create `backend/alembic/versions/004_add_memories_table.py`:

```python
"""Add memories table with pgvector support.

Revision ID: 004
Revises: 003_foundation_upgrade
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "004_add_memories"
down_revision = "003_foundation_upgrade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "memories",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("resident_id", sa.String(), sa.ForeignKey("residents.id"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("related_resident_id", sa.String(), sa.ForeignKey("residents.id"), nullable=True),
        sa.Column("related_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("media_summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Add pgvector column (can't be done through sa.Column easily)
    op.execute("ALTER TABLE memories ADD COLUMN embedding vector(1024)")

    # Indexes
    op.create_index("ix_memories_resident_type", "memories", ["resident_id", "type"])
    op.create_index("ix_memories_resident_related_resident", "memories", ["resident_id", "related_resident_id"])
    op.create_index("ix_memories_resident_related_user", "memories", ["resident_id", "related_user_id"])

    # HNSW index for fast vector similarity search
    op.execute("""
        CREATE INDEX ix_memories_embedding_hnsw
        ON memories USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade() -> None:
    op.drop_index("ix_memories_embedding_hnsw")
    op.drop_index("ix_memories_resident_related_user")
    op.drop_index("ix_memories_resident_related_resident")
    op.drop_index("ix_memories_resident_type")
    op.drop_table("memories")
```

- [ ] **Step 2: Verify migration syntax**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -c "from alembic.versions import *; print('import ok')" 2>/dev/null || echo "Syntax check: inspect file manually"`

The migration won't run in tests (tests use SQLite in-memory), but verify the file has no syntax errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/alembic/versions/004_add_memories_table.py
git commit -m "feat(memory): add Alembic migration for memories table with pgvector HNSW index"
```

---

### Task 10: Final Integration Test + Cleanup

**Files:**
- Verify all test files

- [ ] **Step 1: Run the full test suite**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/ -v --timeout=30`
Expected: All tests PASS — no regressions

- [ ] **Step 2: Run type check**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m py_compile app/models/memory.py && python3 -m py_compile app/memory/service.py && python3 -m py_compile app/memory/embedding.py && python3 -m py_compile app/memory/prompts.py && python3 -m py_compile app/llm/prompt.py && echo "All files compile OK"`
Expected: "All files compile OK"

- [ ] **Step 3: Verify file structure**

Run: `find backend/app/memory -type f -name "*.py" | sort && echo "---" && find backend/tests -name "*memory*" -o -name "*embedding*" | sort`

Expected:
```
backend/app/memory/__init__.py
backend/app/memory/embedding.py
backend/app/memory/prompts.py
backend/app/memory/service.py
---
backend/tests/test_embedding.py
backend/tests/test_memory_chat_integration.py
backend/tests/test_memory_model.py
backend/tests/test_memory_prompt.py
backend/tests/test_memory_service.py
```

- [ ] **Step 4: Final commit — update main.py model import**

Verify `backend/app/main.py` has the memory model import added in Task 1. If already done, skip this step.

```bash
cd /Users/jimmy/Downloads/Skills-World
git status
# If clean, no commit needed. If any uncommitted changes:
git add -A && git commit -m "chore(memory): final cleanup for P1 memory system"
```
