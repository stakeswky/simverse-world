"""Phase 7 — the live-endpoint conformance harness scores a runtime by driving it
over real HTTP.

Verified against the reference runtime server (in-process ASGI transport + fake
completer), proving the harness derives the gate hooks from a real round-trip and
produces a SELECTED verdict. When a commercial endpoint is configured (its
base_url set), the same harness scores it via ``scripts/p7_score_endpoint.py`` —
no code change, no fabricated score.
"""
import json

import httpx
import pytest

from app.lab import adapter_gate as gate
from app.lab.runtime_ref.server import create_app
from app.lab.runtime_ref.http_candidate import HttpEndpointCandidate
from app.lab.runtime_ref.candidate import LICENSE_MANIFEST
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
        {"plan": "search", "tool": "web.search", "query": "cyberpunk", "conclusion": ""},
        {"plan": "done", "tool": None, "query": "", "conclusion": "neon"},
    ]
    state = {"n": 0}

    async def _complete(messages):
        i = min(state["n"], len(script) - 1)
        state["n"] += 1
        return json.dumps(script[i]), 7
    return lambda: _complete


@pytest.mark.anyio
async def test_http_candidate_scores_live_reference_server(db_session, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "lab_grant_secret", "test-secret", raising=False)
    monkeypatch.setattr(settings, "lab_policy_version", "lab-policy-v1", raising=False)

    app = create_app(completer_factory=_fake_completer_factory(), max_steps=3)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://ref.test")
    monkeypatch.setattr("app.http.get_client", lambda: client)

    adapter = SimverseRefAdapter()
    adapter.base_url = "http://ref.test"

    spec = RunSpec(run_id="probe", task_id="probe-t", researcher_slug="gate",
                   brief="research cyberpunk", scopes=["web_search", "browse", "code"], budget_usd=0.5)
    candidate = HttpEndpointCandidate(adapter, name="simverse_ref",
                                      license_manifest_path=LICENSE_MANIFEST)
    await candidate.prepare(spec)

    # The hooks were derived from a REAL round-trip against the live server.
    assert candidate.emit_tool_intent()[0] == "web.search"
    assert len(candidate.provider_events()) >= 3

    results = await gate.run_conformance(candidate, db=db_session)
    verdict = gate.score_candidate("simverse_ref", results)
    by = {r.key: r for r in results}
    assert by["broker_mediation"].score >= gate.MANDATORY_THRESHOLD
    assert by["disconnect_replay_cancel"].score >= gate.MANDATORY_THRESHOLD
    assert by["isolated_deployment"].score >= gate.MANDATORY_THRESHOLD
    assert verdict.passed_mandatory and verdict.selected
    await client.aclose()
