# WebMCP Challenge Test Plan

## Automated Day-0 gates

Run from `frontend/`:

```bash
npm ci
npm run lint
npm run test
npx tsc -b
npm run build
```

Focused tests cover:

- Safe fallback when `document.modelContext` is absent.
- No registration when `VITE_WEBMCP_ENABLED` is not exactly `true`.
- One registration for repeated or concurrent mounts in the same `Document`.
- A fresh registration in a new `Document`, representing refresh.
- Safe retry after registration failure.
- Exact tool name, empty schema, `additionalProperties:false`, and `readOnlyHint:true`.
- Stable five-field success output.
- Runtime rejection of unexpected input.
- Fixed failure output with no JWT, `Authorization`, bearer value, internal path, or stack.
- Visible Agent Activity after actual execution.
- Anonymous `/challenge` routing and isolation from authenticated gameplay overlays.

## Option B Phase 4 security-negative matrix

Recorded on `2026-08-27`. Every required case has its own test node; no row is
represented only by a broad shared assertion.

| # | Node id | Expected code / outcome | Actual result |
|---:|---|---|---|
| 1 | `frontend/src/webmcp/challengeToolSurfaceManager.test.ts > ChallengeToolSurfaceManager > test_commit_tool_absent_before_approval` | `ABSENT_BEFORE_APPROVAL`; old handler becomes `STALE_TOOL_SURFACE` | PASS |
| 2 | `backend/tests/challenge/test_router.py::test_commit_without_approval_cookie` | `APPROVAL_REQUIRED` | PASS |
| 3 | `backend/tests/challenge/test_router.py::test_commit_rejects_approved_extra_field` | `INVALID_INPUT` | PASS |
| 4 | `backend/tests/challenge/test_authorization.py::test_approval_invalid_after_one_sc_change` | `PREVIEW_STALE`; no world change | PASS |
| 5 | `backend/tests/challenge/test_authorization.py::test_approval_invalid_after_resident_replacement` | `PREVIEW_STALE`; no world change | PASS |
| 6 | `backend/tests/challenge/test_authorization.py::test_approval_rejects_stale_world_version` | `STALE_WORLD_VERSION` | PASS |
| 7 | `backend/tests/challenge/test_authorization.py::test_approval_rejects_cross_session_preview` | `APPROVAL_MISMATCH` | PASS |
| 8 | `backend/tests/challenge/test_authorization.py::test_approval_expires_after_ninety_seconds` | `APPROVAL_EXPIRED`; state returns to `PREVIEW_READY` | PASS |
| 9 | `backend/tests/challenge/test_authorization.py::test_revoked_approval_cannot_commit` | `APPROVAL_REVOKED` | PASS |
| 10 | `backend/tests/challenge/test_router.py::test_consumed_approval_cannot_replay` | `APPROVAL_REPLAYED`; one receipt only | PASS |
| 11 | `backend/tests/challenge/test_concurrency.py::test_concurrent_commits_have_one_success` | one success; loser `APPROVAL_REPLAYED` | PASS |
| 12 | `frontend/src/webmcp/challengeTools.test.ts > challenge investigate tool > test_prompt_injection_does_not_change_surface` | `INVALID_INPUT`; surface unchanged | PASS |
| 13 | `frontend/src/components/challenge/HumanApprovalPanel.test.tsx > HumanApprovalPanel > test_programmatic_click_cannot_approve` | untrusted DOM click produces no approval | PASS |
| 14 | `backend/tests/challenge/test_router.py::test_mutation_without_csrf_is_rejected` | `INVALID_INPUT`; service not entered | PASS |
| 15 | `backend/tests/challenge/test_router.py::test_mutation_with_wrong_origin_is_rejected` | `INVALID_INPUT`; service not entered | PASS |
| 16 | `backend/tests/challenge/test_router.py::test_reset_invalidates_old_approval` | `APPROVAL_REQUIRED`; old session and approval deleted | PASS |
| 17 | `backend/tests/challenge/test_router.py::test_expired_session_rejects_old_receipt` | `CHALLENGE_SESSION_EXPIRED`; receipt not disclosed | PASS |
| 18 | `frontend/src/webmcp/challengeToolSurfaceManager.test.ts > ChallengeToolSurfaceManager > test_old_epoch_handler_returns_stale_surface` | `STALE_TOOL_SURFACE`; old action not called | PASS |
| 19 | `frontend/src/pages/ChallengePage.test.tsx > ChallengePage > test_no_webmcp_keeps_ordinary_ui_complete` | ordinary UI remains complete and reset works | PASS |
| 20 | `backend/tests/challenge/test_router.py::test_production_town_id_is_rejected` | `INVALID_INPUT`; service not entered | PASS |

Task gate evidence:

```text
backend authorization + concurrency + router: 68 passed
frontend challengeTools + surface manager + HumanApprovalPanel: 26 passed
ordinary-browser UI fixed node: 1 passed
```

## Production build

`VITE_WEBMCP_ENABLED` is a Vite build-time value. Enable it while building the exact artifact deployed to Cloudflare:

```bash
VITE_API_URL=https://api.simverse.world \
VITE_WEBMCP_ENABLED=true \
./deploy/frontend/deploy.sh
```

After deployment, fetch the page in a fresh profile and confirm the deployed asset is new. Do not treat a local build as live evidence.

## Manual browser matrix

| Check | ChatGPT desktop in-app browser | Chrome 149 with WebMCP flag | Ordinary browser |
|---|---:|---:|---:|
| `/challenge` opens without login | Required | Required | Required |
| Tool appears as available | 3 consecutive runs | 3 consecutive runs | Not applicable |
| Tool returns exact five fields | Required | Required | Not applicable |
| Page adds one visible activity receipt per call | Required | Required | Not applicable |
| Refresh makes the tool discoverable again | Required | Required | Page still works |
| No duplicate tool after SPA remount | Required | Required | Page still works |
| No JWT, headers, stack, or raw exception in failure | Required | Required | Required |

Recommended ChatGPT prompt:

> Open the current page's available Site Tools. Call `simverse_get_challenge_status` once and report its exact result. Do not use browser scraping for this check.

## Network and security inspection

During each tool call:

1. Keep DevTools Network open.
2. Confirm the execute handler sends no HTTP request.
3. Confirm no `Authorization` header or token appears in the result, activity record, console, or captured error.
4. Pass unexpected input in a local harness and confirm a fixed `invalid_input` response.
5. Force the status provider to throw in a unit test and confirm only the fixed safe error is returned.

## Evidence record

For every manual run, record:

- Desktop app or browser version.
- Model used.
- Deployed URL and deployment timestamp.
- Git commit SHA and asset hash.
- Invocation number, result, measured duration, and screenshot filename.
- Pass/fail and an issue link for any failure.

Do not continue to the mutation workflow until the public probe passes all six WebMCP discovery/invocation runs.

### Explicit live blocker: route lifecycle

The current OpenAI guide documents registration but does not define a removal API. Day 0 therefore uses ordinary document navigation in the Challenge header and deduplicates registrations within a document. Before any state-changing tool is added, verify all of these in both supported hosts:

1. Directly open `/challenge`, discover the tool, and call it.
2. Leave for `/town`; confirm the Challenge tool is no longer available.
3. Use browser Back to return; confirm exactly one working Challenge tool appears.
4. Repeat with Forward, refresh, and a programmatic same-document route transition.
5. Stop the sprint if a stale or duplicate tool remains; resolve the host lifecycle before adding mutations.

## Latest local evidence

Recorded on `2026-08-26` against the challenge worktree using Node `24.19.0` and npm `11.9.0`:

| Gate | Result |
|---|---|
| Selected WebMCP, page, and route regression suite | Pass — 3 files, 34 tests |
| Full frontend Vitest suite | Pass — 68 files, 336 tests |
| ESLint | Pass — zero reported errors or warnings |
| TypeScript project build (`tsc -b`) | Pass |
| Default production build | Pass — 922 modules transformed |
| `VITE_WEBMCP_ENABLED=true` production build | Pass — tool name and `modelContext` present in the lazy Challenge chunk |
| Built-asset secret-marker scan | Pass |

GitHub CI remains the authority for the repository's pinned Node 22 environment. Live ChatGPT and Chrome rows remain unverified until the exact commit is deployed publicly.

The recorded built-asset marker scan is reproducible after the enabled production build:

```bash
! rg -n 'jwt-secret-token|registration-secret|feature-secret|capability-secret|input-secret|internal/server/private' dist
```
