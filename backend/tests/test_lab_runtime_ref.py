"""Phase 7 (recovery plan) — the Simverse reference runtime is a REAL, gate-
admissible adapter candidate.

The agent loop is driven by an injected completer (a deterministic fake here; the
real LLM in production), so these tests are hermetic. They prove:

* the loop produces a protocol-shaped step sequence + a terminal artifact and
  INTENDS tool calls only (never executes them);
* the candidate derived from that real run PASSES the adapter conformance gate —
  every mandatory dimension >= 0.6 and total >= 80 — so it would be SELECTED.

A separate opt-in check (`test_ref_agent_real_llm`, skipped without
LAB_REF_REAL_LLM) drives the loop against the real LLM to prove the endpoint works.
"""
import json
import os

import pytest

from app.lab import adapter_gate as gate
from app.lab.runtime_ref.agent import RefAgent
from app.lab.runtime_ref.candidate import SimverseRefCandidate


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def configured_test_egress(monkeypatch):
    monkeypatch.setenv("LAB_EGRESS_ENABLED", "true")
    monkeypatch.setenv("LAB_EGRESS_SEARCH_ENDPOINT", "http://search.test")


def _fake_completer(script):
    calls = {"n": 0}

    async def _complete(messages):
        i = min(calls["n"], len(script) - 1)
        calls["n"] += 1
        return json.dumps(script[i]), 42
    return _complete


@pytest.mark.anyio
async def test_agent_loop_produces_steps_and_intends_tools():
    completer = _fake_completer([
        {"plan": "search primary sources", "tool": "web.search", "query": "cyberpunk aesthetics", "conclusion": ""},
        {"plan": "synthesize", "tool": None, "query": "", "conclusion": "cyberpunk = neon + noir + high-tech-low-life"},
    ])
    agent = RefAgent(complete=completer, max_steps=3)
    result = await agent.run(brief="research cyberpunk aesthetics", scopes=["web_search", "browse"])

    phases = [s.phase for s in result.steps]
    assert "think" in phases and "tool_call" in phases and "message" in phases
    assert result.tool_intents == [("web.search", {"query": "cyberpunk aesthetics"})]
    assert result.artifacts and result.artifacts[0].kind == "text"
    assert "cyberpunk" in result.artifacts[0].text_md
    assert result.model_tokens == 84  # 2 rounds * 42


@pytest.mark.anyio
async def test_agent_only_intends_granted_tools():
    completer = _fake_completer([
        {"plan": "run code", "tool": "code.run", "query": "print(1)", "conclusion": ""},
        {"plan": "done", "tool": None, "query": "", "conclusion": "done"},
    ])
    agent = RefAgent(complete=completer, max_steps=2)
    result = await agent.run(brief="x", scopes=["web_search"])
    assert result.tool_intents == []  # code.run refused — not in granted scopes


@pytest.mark.anyio
async def test_reference_runtime_passes_the_conformance_gate(db_session, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "lab_grant_secret", "test-secret", raising=False)
    monkeypatch.setattr(settings, "lab_policy_version", "lab-policy-v1", raising=False)

    completer = _fake_completer([
        {"plan": "search", "tool": "web.search", "query": "conformance sources", "conclusion": ""},
        {"plan": "conclude", "tool": None, "query": "", "conclusion": "found the sources"},
    ])
    result = await RefAgent(complete=completer, max_steps=3).run(
        brief="probe", scopes=["web_search", "browse", "code"])
    candidate = SimverseRefCandidate(result)

    results = await gate.run_conformance(candidate, db=db_session)
    verdict = gate.score_candidate(candidate.name, results, tie_break={
        "credential_surface": "one model-endpoint secret", "ops_burden": "low"})

    by = {r.key: r for r in results}
    assert by["broker_mediation"].score >= gate.MANDATORY_THRESHOLD, by["broker_mediation"].evidence
    assert by["disconnect_replay_cancel"].score >= gate.MANDATORY_THRESHOLD, by["disconnect_replay_cancel"].evidence
    assert by["isolated_deployment"].score >= gate.MANDATORY_THRESHOLD, by["isolated_deployment"].evidence
    assert verdict.passed_mandatory and not verdict.eliminated
    assert verdict.total >= gate.SELECTION_THRESHOLD, f"total={verdict.total}"
    assert verdict.selected


@pytest.mark.anyio
@pytest.mark.skipif(not os.environ.get("LAB_REF_REAL_LLM"),
                    reason="opt-in: set LAB_REF_REAL_LLM=1 to drive the real LLM endpoint")
async def test_ref_agent_real_llm():
    """Opt-in: drive the loop against the project's real Anthropic-compatible
    endpoint, proving the runtime works end to end with a live model."""
    from app.config import settings
    from app.llm.client import get_client
    from app.lab.runtime_ref.agent import anthropic_completer
    completer = anthropic_completer(get_client("system"), settings.llm_model)
    result = await RefAgent(complete=completer, max_steps=2).run(
        brief="research cyberpunk aesthetics in one line", scopes=["web_search"])
    assert result.steps and result.artifacts
    assert result.model_tokens > 0  # real tokens burned
