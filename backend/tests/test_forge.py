import pytest

@pytest.fixture
async def auth_headers(client):
    """Create a user and return auth headers."""
    resp = await client.post("/auth/register", json={
        "name": "ForgeUser", "email": "forge@test.com", "password": "pass123"
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.anyio
async def test_forge_start_creates_session(client, auth_headers):
    resp = await client.post("/forge/start", json={"name": "测试居民"},
                             headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "forge_id" in data
    assert data["step"] == 1
    assert data["question"]  # Q2 question text

@pytest.mark.anyio
async def test_forge_answer_advances_step(client, auth_headers):
    start = await client.post("/forge/start", json={"name": "测试居民"},
                              headers=auth_headers)
    forge_id = start.json()["forge_id"]

    resp = await client.post("/forge/answer", json={
        "forge_id": forge_id,
        "answer": "擅长后端架构设计，Go 和 Rust 都很熟"
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["step"] == 2
    assert data["next_step"] == 3

@pytest.mark.anyio
async def test_forge_status_returns_session(client, auth_headers):
    start = await client.post("/forge/start", json={"name": "测试居民"},
                              headers=auth_headers)
    forge_id = start.json()["forge_id"]

    resp = await client.get(f"/forge/status/{forge_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "collecting"
    assert data["name"] == "测试居民"

@pytest.mark.anyio
async def test_forge_answers_advance_to_generating(
    client, auth_headers, db_engine
):
    # The final answer schedules the background LLM pipeline
    # (run_generation_pipeline). Offline, the real Anthropic client hangs into
    # teardown ("task pending" error). Mock the LLM at the client boundary:
    # the call parks on an event so status stays deterministically
    # "generating", then raises so the background task drains before teardown.
    import asyncio
    from unittest.mock import MagicMock, patch
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    release = asyncio.Event()
    llm_calls: list[dict] = []
    background_tasks: list[asyncio.Task] = []

    def capture_background_task(coro) -> None:
        background_tasks.append(asyncio.create_task(coro))

    async def fake_create(*args, **kwargs):
        llm_calls.append(kwargs)
        await release.wait()
        raise RuntimeError("offline test: no LLM available")

    mock_llm = MagicMock()
    mock_llm.messages.create = fake_create

    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    with (
        patch("app.forge.legacy_pipeline.get_client", return_value=mock_llm),
        patch("app.routers.forge.async_session", session_factory),
        patch("app.routers.forge._spawn_bg", side_effect=capture_background_task),
    ):
        start = await client.post("/forge/start", json={"name": "张三"},
                                  headers=auth_headers)
        forge_id = start.json()["forge_id"]

        answers = [
            "后端架构，擅长高并发系统",
            "话少但犀利，评审会喜欢抛致命问题",
            "相信代码是艺术品，经历过创业失败",
            "跳过",
        ]
        for answer in answers:
            resp = await client.post("/forge/answer", json={
                "forge_id": forge_id, "answer": answer,
            }, headers=auth_headers)
            assert resp.status_code == 200

        # After Q5, status should be "generating" (pipeline parked at the LLM)
        resp = await client.get(f"/forge/status/{forge_id}", headers=auth_headers)
        data = resp.json()
        assert data["status"] in {"generating", "running"}

        # Drain the background task before teardown: unblock the mocked LLM,
        # then await that exact task instead of racing a fixed polling loop.
        release.set()
        assert background_tasks, "background pipeline was not scheduled"
        await asyncio.wait_for(
            asyncio.gather(*background_tasks),
            timeout=30,
        )
        status_resp = await client.get(
            f"/forge/status/{forge_id}", headers=auth_headers
        )
        assert status_resp.json()["status"] == "error"
        assert llm_calls, "background pipeline never reached the (mocked) LLM"

@pytest.mark.anyio
async def test_score_content_completeness():
    from app.forge.legacy_helpers import _compute_star_rating_fallback

    # Sparse = 1 star
    assert _compute_star_rating_fallback("# 能力\n暂无", "# 人格\n暂无", "# 灵魂\n暂无") == 1

    # Moderate = 2 stars
    ability = "# 能力概览\n后端架构师\n## 专业能力\n- Go 微服务\n- 高并发设计\n- 数据库优化"
    persona = "# 人格档案\n## Layer 0\n- **理性**：数据驱动\n## Layer 1\n工程师"
    soul = "# 灵魂档案\n## Soul Layer 0\n- **追求真理**：不接受模糊"
    assert _compute_star_rating_fallback(ability, persona, soul) == 2

    # Rich = 3 stars
    rich_ability = ability + "\n- 分布式系统\n- 性能优化\n## 社交能力\n- 代码评审\n## 学习与适应\n- 快速学习新技术\n## 生活技能\n- 烹饪"
    rich_persona = persona + "\n## Layer 2\n犀利简洁\n## Layer 3\n理性决策\n## Layer 4\n导师型领导\n## Layer 5\n零容忍低质量代码"
    rich_soul = soul + "\n## Soul Layer 1\n创业经历塑造了我\n## Soul Layer 2\n极简主义美学\n## Soul Layer 3\n内敛但温暖\n## Soul Layer 4\n持续成长型思维"
    assert _compute_star_rating_fallback(rich_ability, rich_persona, rich_soul) == 3
