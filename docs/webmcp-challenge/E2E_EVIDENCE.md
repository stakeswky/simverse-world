# Challenge browser E2E evidence

## Result

The reproducible Chromium gate passed on 2026-08-27 at `07:34:30Z` from source
HEAD `47c4173858a6edb4cccf561a5988f34073776b3a` (`test(challenge): lock
five-tool WebMCP contract`). The run used Node `v22.23.2`, npm `10.9.8`,
Playwright `1.62.1`, and Chromium `151.0.7922.34`.

That hash is the checked-out parent because the Task 6.3 tree was still the
working-tree diff under test when this evidence document was authored. The
task's fixed commit is verified by running the same complete script again after
commit; the fixed `/tmp/simverse-option-b-e2e-evidence.log` must then report the
new HEAD. This avoids an impossible self-referential commit hash and avoids
amending a tested commit.

```text
full_flow=10/10 reset_hash=10/10 replay_success=0 unauthorized_success=0 duplicate_tools=0
1 passed (16.5s)
playwright_exit=0 cleanup_exit=0
api_health=ok frontend_health=ok
api_drain=api drained pid=8860
frontend_drain=frontend drained pid=9033
```

The fixed machine-readable record path (overwritten by each later run) is
`/tmp/simverse-option-b-e2e-evidence.log`; Playwright's JSON report is
`/tmp/simverse-option-b-e2e-artifacts/report.json` (3,406 bytes).

## Real path exercised

`bash scripts/run-challenge-e2e.sh` started the repository's pgvector database
and Redis, applied every Alembic migration, started the real FastAPI process,
built the enabled Vite production bundle, served it with Vite preview, and ran
the flow in a real Chromium process. The test did not mock the API, store, DOM,
cookies, or browser clicks.

Stock Chromium does not provide the experimental `document.modelContext` API.
The spec therefore injects only a minimal host adapter that records the real
page's `registerTool` calls and invokes the registered handlers. Every session,
investigate, preview, approval, commit, verify, and reset request still crosses
the real browser/network/backend boundary. Approval is created by Playwright's
trusted checkbox and button click, not by calling a store or action directly.

The ten fresh-cookie runs each proved the full state/tool lifecycle, visible
six-resident harbor evidence, immutable diff, absent pre-approval commit tool,
403 unauthorized commit, one-time strict-path approval cookie, execution
receipt, 72-hour paired outcome, stale old handler, reset, and restored initial
hash. Run one additionally raced two identical commit tool executions and
proved exactly one successful commit plus one `APPROVAL_REPLAYED`. A separate
same-context phase performed ten more reset API calls and checked a new session
generation plus the original world hash each time.

The concurrent run also checks the public post-commit projection directly:
world version `8`, budget `60`, receipt budget tuple `300/-240/60`, exactly one
`employer-escrow-mediation` receipt event, and exactly one matching world event.
The unauthorized request is asserted as HTTP `403` as well as
`APPROVAL_REQUIRED`.

## Visual evidence

- `/tmp/simverse-option-b-e2e-artifacts/challenge-full-flow-10.png` — verified
  outcome block and paired timeline (112,222 bytes)
- `/tmp/simverse-option-b-e2e-artifacts/challenge-outcome-prediction.png` —
  Prediction article (24,154 bytes)
- `/tmp/simverse-option-b-e2e-artifacts/challenge-outcome-actual.png` — Actual
  after 72h article (10,255 bytes)
- `/tmp/simverse-option-b-e2e-artifacts/challenge-outcome-control.png` —
  No-action control article (9,264 bytes)
- `/tmp/simverse-option-b-e2e-artifacts/challenge-reset-10.png` — initial state
  after ten same-context resets (303,623 bytes)

The three outcome articles are separate screenshots because the shipped UI
intentionally presents that comparison as a horizontally scrollable strip at
the tested width. Each image is captured from its real DOM article; no visual
stitching or style override is used.

## Failed attempts retained as evidence

The gate was not promoted from partial success. Earlier runs exposed and then
fixed four reproducibility defects:

1. Alembic settings required `DEBUG=true` during migration.
2. Root compose used plain `postgres:16-alpine`, which lacks the migration's
   pgvector extension; it now matches CI and production on
   `pgvector/pgvector:pg16` without deleting the named volume.
3. Host `HTTP_PROXY`/`HTTPS_PROXY` intercepted loopback health probes; the
   script now fixes `NO_PROXY/no_proxy` and bounds every health curl to five
   seconds.
4. The first real Chromium run reached approval and then failed because a
   Node-side tool-name constant was referenced inside `page.evaluate`; the
   constant is now passed explicitly into the browser context.

After those corrections, the complete fixed-runtime script passed repeatedly;
the final run above is the evidence cited by this document.
