# Judging Map

The submission is designed backward from the four equally weighted Challenge criteria. WebMCP leverage is treated as the tie-breaker and therefore the primary product constraint.

| Criterion | Product evidence | Submission evidence |
|---|---|---|
| WebMCP leverage | Shared live page, state-dependent tools, visible evidence focus, preview → stage → approve → commit → verify | Tool trace beside the page, staged diff, approval boundary, before/after shared state |
| Execution | Anonymous Judge Mode, isolated deterministic town, one-click reset, fallback behavior, stable critical path | Public URL, test instructions, browser matrix, five-run reliability results, failure demo |
| Potential impact | Reduces navigation through map, graph, economy, and event panels while preserving human judgment | Timed ordinary-UI versus WebMCP benchmark with clicks, page changes, errors, and completion rate |
| Creativity and ambition | Human-agent co-governance of a persistent AI society where interventions affect residents, relationships, economy, and events | Three-minute end-to-end civic intervention story and concise architecture explanation |

## Evidence maturity

| Evidence | Day-0 status | Required before submission |
|---|---|---|
| Pre-challenge baseline | Proven by the GitHub-signed merge commit SHA and timestamp | Annotated tag resolves to the SHA |
| Public `/challenge` experience | Implemented in source | Deployed and directly reachable without login |
| Site Tool discovery | Registration path implemented; discovery unverified | Three consecutive ChatGPT in-app-browser successes |
| Chrome compatibility | Registration path implemented; compatibility unverified | Three consecutive Chrome 149 flag-enabled successes |
| Ordinary-browser fallback | Covered by unit tests | Manual Safari/Chrome/Firefox smoke |
| Visible tool activity | Implemented in source and unit tested | Captured in screenshots and final video |
| Full civic hero flow | Not part of Day 0 | Diagnose through verified outcome, plus reset |
| Quantified impact | Measurement design complete | Five ordinary-UI and five WebMCP trials |

No submission copy should promote a source-level or unit-tested item to “deployed” or “verified” without the corresponding live evidence.

## Benchmark record

Use one consistent task:

> Find the most urgent town problem and prepare a safe intervention costing no more than 300 SC.

Record each run in a worksheet with:

- Method: ordinary UI or WebMCP.
- Tester and run number.
- Completion time in seconds.
- Page changes and clicks.
- Wrong resident or district selection.
- Whether the final plan met the budget and safety constraints.
- Whether approval and verification completed correctly.

Report medians and raw results; do not cherry-pick the fastest run.
