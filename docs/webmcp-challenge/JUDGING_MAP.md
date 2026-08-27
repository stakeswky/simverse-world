# Civic Copilot Judging Map

The submission is evaluated against one locked task:

> Find the town's most urgent problem and create a safe intervention under 300 SC. Do not close the harbor or rewrite resident preferences.

The five state-dependent Site Tools are the product surface. The legacy status probe is diagnostics-only and is not hero-flow evidence.

| Criterion | Product evidence | Test node id | E2E evidence | Live screenshot |
|---|---|---|---|---|
| WebMCP leverage | Exact state-dependent catalogue: investigate, preview, commit the trusted approved diff, verify, reset | `frontend/src/webmcp/challengeContract.test.ts` — locks the exact catalogue and schemas | `frontend/e2e/challenge-flow.spec.ts` — real modelContext host, 10/10 closed loops, zero duplicate or stale tools | `LIVE_GATE.md` records the Day-0 status probe; final five-tool mutation screenshots remain pending until the exact commit is deployed |
| Execution | Deterministic isolated Challenge Town, ordinary-UI fallback, one-time approval, receipt-bound verification, reset to the locked hash | `backend/tests/challenge/test_contract.py` — route contract, authorization, replay, reset, and output allowlists | `E2E_EVIDENCE.md` — 10 full flows and 10 reset/hash checks in real Chromium | Day-0 discovery is public; final mutation-host evidence is intentionally not claimed yet |
| Potential impact | The ordinary page and Site Tools solve the same task, allowing a paired time/click comparison | `frontend/src/pages/ChallengePage.test.tsx` — approved-only ordinary commit path | `BENCHMARK.md` — five alternating ordinary and five WebMCP runs; medians 423.6 ms/6 clicks versus 242.8 ms/2 clicks | Public benchmark screenshots are captured only after the final deployment identity is proven |
| Creativity and ambition | Prediction is compared with both the 72-hour Actual outcome and a paired No-action control in one civic-governance story | `backend/tests/challenge/test_engine.py` — deterministic forecast, actual, control, and fixture invariants | `challenge-flow.spec.ts` captures prediction, actual, control, receipt, and reset | Final hero-flow screenshots remain pending until live verification |

## Evidence ladder

Evidence is promoted only in this order:

1. **Automated contracts** — unit and contract assertions for exact schemas, state transitions, authorization, and safe output.
2. **Local real services** — FastAPI with real Redis for one-time approval, replay, compare-and-set, and reset behavior.
3. **E2E real Chromium** — the actual built page, real API, modelContext test host, ordinary fallback, and lifecycle transitions.
4. **Day-0 public live** — three ChatGPT and three Chrome status-probe runs plus ordinary fallback, recorded in `LIVE_GATE.md`.
5. **Final mutation live** — the exact deployed backend/frontend identity and three complete investigate-to-reset lifecycles. This is pending until deployment.

Source-level, unit-test, local-browser, and Day-0 status evidence must not be described as final mutation live evidence.

## Quantified evidence

- [Closed-loop E2E evidence](E2E_EVIDENCE.md)
- [Paired benchmark with every raw run](BENCHMARK.md)
- [Public Day-0 gate](LIVE_GATE.md)
- [Locked fixture and expected outcome](FIXTURE_LOCK.md)
- [Security and authority boundary](SECURITY.md)

The benchmark includes all ten runs and reports medians; no run is discarded or cherry-picked.
