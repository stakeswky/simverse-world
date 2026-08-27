"""Phase 7 — the reference runtime server speaks the Lab HTTP wire protocol, and
the SimverseRefAdapter drives it end to end.

Uses an in-process ASGI transport (no real socket) with a deterministic fake
completer, so it is hermetic but exercises the REAL server routes + the REAL
HttpAgentAdapter wire (start → goal → step_stream → collect_artifacts → health).
"""
import json

import httpx
import pytest

from app.lab.runtime_ref.server import create_app
from app.lab.sandbox.base import RunSpec
from app.lab.sandbox.simverse_ref import SimverseRefAdapter


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def configured_test_egress(monkeypatch):
    monkeypatch.setenv("LAB_EGRESS_ENABLED", "true")
    monkeypatch.setenv("LAB_EGRESS_SEARCH_ENDPOINT", "http://search.test")


def _fake_completer_factory():
    script = [
        {"plan": "search sources", "tool": "web.search", "query": "cyberpunk", "conclusion": ""},
        {"plan": "conclude", "tool": None, "query": "", "conclusion": "neon + noir"},
    ]
    state = {"n": 0}

    async def _complete(messages):
        i = min(state["n"], len(script) - 1)
        state["n"] += 1
        return json.dumps(script[i]), 10
    return lambda: _complete


def _asgi_client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://ref.test")


@pytest.mark.anyio
async def test_server_protocol_roundtrip():
    app = create_app(completer_factory=_fake_completer_factory(), max_steps=3)
    async with _asgi_client(app) as c:
        sid = (await c.post("/runs", json={"run_id": "r1", "scopes": ["web_search"]})).json()["session_id"]
        assert sid
        await c.post(f"/runs/{sid}/goal", json={"brief": "research cyberpunk", "scopes": ["web_search"]})
        after, done, seen = 0, False, []
        for _ in range(50):
            data = (await c.get(f"/runs/{sid}/steps", params={"after": after})).json()
            for st in data["steps"]:
                after = max(after, st["seq"])
                seen.append(st)
            if data["done"]:
                done = True
                break
        assert done
        phases = [s["phase"] for s in seen]
        assert "think" in phases and "tool_call" in phases and "message" in phases
        arts = (await c.get(f"/runs/{sid}/artifacts")).json()["artifacts"]
        assert arts and arts[0]["kind"] == "text" and "neon" in arts[0]["text_md"]
        health = (await c.get(f"/runs/{sid}/health")).json()
        assert health["alive"] is False


@pytest.mark.anyio
async def test_adapter_drives_server_end_to_end(monkeypatch):
    app = create_app(completer_factory=_fake_completer_factory(), max_steps=3)
    client = _asgi_client(app)
    monkeypatch.setattr("app.http.get_client", lambda: client)

    adapter = SimverseRefAdapter()
    adapter.base_url = "http://ref.test"  # configured → not fail-closed

    spec = RunSpec(run_id="r1", task_id="t1", researcher_slug="sage",
                   brief="research cyberpunk aesthetics", scopes=["web_search"], budget_usd=0.5)
    handle = await adapter.start(spec)
    await adapter.submit_goal(handle, spec.brief, spec.scopes)

    steps = []
    async for ev in adapter.step_stream(handle):
        steps.append(ev)
    assert any(s.phase == "tool_call" and s.tool == "web.search" for s in steps)

    arts = await adapter.collect_artifacts(handle)
    assert arts and arts[0].kind == "text" and "neon" in (arts[0].text_md or "")

    health = await adapter.health(handle)
    assert health["alive"] is False
    await client.aclose()


@pytest.mark.anyio
async def test_adapter_fail_closed_when_unconfigured():
    from app.lab.sandbox.base import LabAdapterUnconfigured
    adapter = SimverseRefAdapter()  # base_url empty
    assert adapter.base_url == ""
    with pytest.raises(LabAdapterUnconfigured):
        await adapter.start(RunSpec(run_id="r", task_id="t", researcher_slug="s",
                                    brief="x", scopes=[], budget_usd=0.1))
