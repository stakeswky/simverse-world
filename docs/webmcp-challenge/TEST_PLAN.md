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
