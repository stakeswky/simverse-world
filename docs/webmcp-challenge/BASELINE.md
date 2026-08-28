# WebMCP Challenge Baseline

This document separates the pre-existing Simverse World product from work created for the 2026 OpenAI WebMCP Challenge.

## Authoritative pre-challenge commit

| Field | Value |
|---|---|
| Repository | `stakeswky/simverse-world` |
| Baseline SHA | [`de98dc4b47c67cd30ff2c3809493489577a3e4cf`](https://github.com/stakeswky/simverse-world/commit/de98dc4b47c67cd30ff2c3809493489577a3e4cf) |
| Commit time | `2026-08-25T06:10:41Z` |
| Challenge submission period start | `2026-08-25T18:00:00Z` (`11:00 PT`) |
| Lead time | The baseline commit predates the submission period by `11h 49m 19s` |
| GitHub verification | Verified merge commit for [PR #14](https://github.com/stakeswky/simverse-world/pull/14) |
| Baseline tag name | `webmcp-challenge-baseline-2026-08-25` |

The commit SHA is the canonical evidence. The annotated tag must resolve to exactly that SHA; its later tagger date does not change the timestamp of the commit it identifies.

Verify locally:

```bash
git rev-parse webmcp-challenge-baseline-2026-08-25^{}
git show -s --format='%H%n%aI%n%cI%n%s' de98dc4b47c67cd30ff2c3809493489577a3e4cf
```

## Features that existed before the challenge

The baseline already contained a deployed, persistent AI town. These capabilities are product context, not Challenge work:

- A 2D town map with player movement and buildings.
- Autonomous AI residents with personalities, memories, reflection, relationships, conversations, and daily actions.
- Economy and community systems, including shops, commissions, markets, caravans, seasons, debates, town hall, bulletins, and time capsules.
- Public `/town` and read-only `/watch` views.
- An Agent Player API and hosted Agent controller for approved external agents.
- A relationship graph, Forge resident creation flow, and an administrative console.
- Existing authentication, authorization, WebSocket updates, database models, background workers, and Cloudflare deployment.

Repository evidence for the pre-existing product is available in [`README.md`](../../README.md), [`docs/ROADMAP.md`](../ROADMAP.md), and [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) at the baseline SHA.

## Work added after the challenge began

Challenge work is isolated on `challenge/webmcp-civic-copilot` and uses scoped `feat(webmcp):`, `test(webmcp):`, `docs(webmcp):`, or `fix(webmcp):` commits.

The Day-0 increment consists only of:

- A public `/challenge` probe page.
- A feature-detected WebMCP adapter under `frontend/src/webmcp/`.
- One read-only tool: `simverse_get_challenge_status`.
- A visible Agent Activity receipt produced by an actual tool invocation.
- `VITE_WEBMCP_ENABLED` as a build-time release gate.
- Focused unit, route, fallback, idempotency, and leakage tests.
- The challenge product, security, judging, testing, tool, and demo documentation in this directory.

It does **not** change the NPC scheduler, economy rules, database schema, Agent Player API, or production-town state.

## Audit links

- [Challenge branch commit history](https://github.com/stakeswky/simverse-world/commits/challenge/webmcp-civic-copilot)
- [Baseline to challenge branch comparison](https://github.com/stakeswky/simverse-world/compare/de98dc4b47c67cd30ff2c3809493489577a3e4cf...challenge/webmcp-civic-copilot)
- [Open a review comparison against master](https://github.com/stakeswky/simverse-world/compare/master...challenge/webmcp-civic-copilot)

Every later WebMCP pull request must link this baseline, identify its challenge-only files, list verification evidence, and state whether any screenshot or video frame includes pre-existing functionality.

## Submission freeze procedure

At feature freeze, record the final submission SHA and generate the authoritative diff:

```bash
git fetch origin --tags
git diff --stat webmcp-challenge-baseline-2026-08-25...<submission-sha>
git log --oneline webmcp-challenge-baseline-2026-08-25..<submission-sha>
git diff --name-status webmcp-challenge-baseline-2026-08-25...<submission-sha>
```

The final submission notes must label all demo footage as either pre-existing product context or Challenge-created WebMCP behavior.
