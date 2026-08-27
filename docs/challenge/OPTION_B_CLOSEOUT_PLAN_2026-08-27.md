# Simverse World Option B Release Candidate Closeout Plan

Generated: 2026-08-27 Asia/Shanghai

## 1. Objective and decision rule

This closeout turns `challenge/webmcp-civic-copilot` into an independently reviewable release candidate, or produces a precise `NO-GO` with all safe evidence completed.

The final decision is binary:

- `GO` only when G01 through G14 all pass for the exact deployed `RELEASE_SHA`.
- `NO-GO` when any mandatory gate fails or is blocked.

No unit, fake-host, loopback, historical, or previous-SHA result substitutes for the required real surface.

## 2. Frozen starting state

| Item | Reverified value |
|---|---|
| Intended worktree | `/Volumes/data/dev/simverse-world-option-b` |
| Branch | `challenge/webmcp-civic-copilot` |
| Starting HEAD | `cbbccc50af59380252972590545340f8f4cfc299` |
| Tracking HEAD | `cbbccc50af59380252972590545340f8f4cfc299` |
| GitHub branch HEAD | `cbbccc50af59380252972590545340f8f4cfc299` |
| Ahead / behind | `0 / 0` |
| Worktree | clean |
| PR | #15, OPEN, Draft, MERGEABLE, merge state UNSTABLE |
| Current checks | backend pytest FAIL; PG migration PASS; frontend PASS |
| Current backend CI | 48 failed, 4453 passed, 24 skipped, 57 deselected |
| Baseline backend CI | 48 failed, 4198 passed, 20 skipped, 57 deselected |
| Current and baseline failure identity | same 48 node IDs and same first failure signatures; still not releasable |
| Alembic head | `068_fix_theater_bounds` |
| Docker | available through `unix:///Users/jimmy/.colima/default/docker.sock` |
| Required test runtimes | Python 3.12; Node 22 for exact CI parity; Node 24 for the requested compatibility run |

The desktop-open worktree `/Volumes/data/dev/simverse-world` is detached at `7d8aaf4d87815a805c64f25aa220255f60c2261a` and contains unrelated user documentation changes. It is excluded from all writes, commits, builds, and cleanup.

## 3. Non-negotiable boundaries

- Do not merge PR #15 or merge to `master` or `main`.
- Do not force-push, rebase, amend, squash, or rewrite published history.
- Do not operate Devpost.
- Do not expose secrets, cookies, complete authorization headers, private identifiers, or production environment values.
- Do not add skips or xfails, remove tests, weaken assertions, or exclude failing tests from CI.
- Do not run `npm audit fix --force`.
- Do not change global production session TTL.
- Production writes are allowed only in the disposable anonymous Challenge session and must not address production town data.
- Do not overwrite old evidence or backups.
- Deployment starts only after local mandatory gates and exact-HEAD GitHub Actions are green.
- Any destructive database restore, schema downgrade, or unrecoverable production action stops for explicit authorization.

## 4. Current contract findings that control the closeout

### 4.1 Five-tool state machine

The production catalogue has no shared tool `version` field. `tool_version=0.1.0` belongs only to the diagnostics status probe.

| Tool | World effect | Approval | Replay or idempotency contract | Canonical result |
|---|---|---|---|---|
| `simverse_investigate_crisis` | world unchanged; evidence and audit stored in disposable session | none | repeatable; new evidence and audit, same world | investigation summary |
| `simverse_preview_intervention` | world unchanged; preview and audit stored in disposable session | none | rebuild replaces preview and invalidates old approval | preview summary |
| `simverse_commit_approved` | v7 to v8, budget 300 to 60 | required through trusted visible UI | one-time Redis WATCH/CAS; replay rejected | execution receipt |
| `simverse_verify_outcome` | v8 to v9 and advances 72 hours | consumes matching commit receipt, no new approval | second call rejected | verification result |
| `simverse_reset_town` | replaces anonymous session and restores v7 | none | old generation rejected; successful reset creates a new generation | reset result |

There is no WebMCP deny tool. The ordinary UI exposes `/challenge/revoke` for an existing approval. Therefore the request that every one of the five tools independently perform preview, approve, deny, and receipt conflicts with the frozen implementation contract. The closeout will not fabricate unsupported rows. It will test the exact per-tool contract and the complete chain, and G10 passes only if the acceptance language can be satisfied by the real chain without inventing evidence; otherwise G10 fails and the verdict is `NO-GO`.

### 4.2 Expiry contract

- Approval TTL is 90 seconds and is settled lazily by the next request.
- Session idle TTL is 15 minutes and absolute TTL is 20 minutes.
- Session TTL is a sliding idle deadline capped by the absolute deadline.
- Challenge has no reservation object; the correct expiry assertion is no world mutation, no success receipt, expired approval tombstone, cleared active capability, and an `approval_expired` audit event.
- Existing tests use fake clocks. This closeout must add or run real wall-clock browser/API evidence without changing production TTL.

### 4.3 CI and dependency security

- The 48 backend failures predate the challenge, but all remain release blockers under this closeout.
- CI authority is `.github/workflows/ci.yml`: Python 3.12, Node 22, SQLite/fakeredis full pytest, PGVector migration/register smoke, TypeScript, Vitest, ESLint JSON 0/0, and build.
- `npm audit --json` currently reports 1 low and 8 high affected nodes. The only production-reachable high is the direct `react-router-dom@7.14.0` chain through `react-router@7.14.0`; the compatible target is at least `7.18.2`. The other affected packages are development/build/test dependencies and still require compatible remediation or documented non-runtime proof.

## 5. Evidence layout

The external raw evidence root is:

`/tmp/simverse-option-b-closeout/$START_SHA/$UTC_TIMESTAMP/`

The repository evidence root begins as:

`docs/challenge/evidence/pending/`

After `RELEASE_SHA` is fixed, repository evidence is copied to:

`docs/challenge/evidence/$RELEASE_SHA/`

Every log record includes UTC start/end, exact SHA, command, runtime versions, exit code, result counts, raw log path, and SHA-256. Sensitive values are redacted before repository archival. `MANIFEST.sha256` is generated last and excludes itself from recursive input.

Every Markdown, text, JSON, and matrix artifact includes a UTC generation timestamp and the exact `RELEASE_SHA` it evaluates. `acceptance.json` is schema-checked for `verdict`, `branch`, `starting_sha`, `final_sha`, `pr`, `backend`, `frontend`, `gates`, `residual_risks`, and `generated_at`; its gate array must contain each G01-G14 ID exactly once with a valid status, evidence list, and notes.

The final repository evidence directory must contain this complete set:

- `README.md`
- `environment.md`
- `git-state.txt`
- `ci-summary.md`
- `ci-baseline-reconciliation.md`
- `backend-full-tests.txt`
- `backend-challenge-tests.txt`
- `frontend-tests.txt`
- `frontend-typecheck.txt`
- `frontend-lint.txt`
- `frontend-build.txt`
- `migration-smoke.txt`
- `npm-audit-summary.md`
- `deployment.md`
- `deployment-manifest.sha256`
- `public-manifest.sha256`
- `cors-health-checks.txt`
- `container-health.txt`
- `post-deploy-log-scan.txt`
- `chatgpt-browser-readonly-matrix.md`
- `chrome-149-matrix.md`
- `five-tool-write-matrix.md`
- `approval-expiry.md`
- `session-expiry.md`
- `rollback.md`
- `residual-risks.md`
- `acceptance.json`
- `MANIFEST.sha256`

## 6. Execution phases

### Step 0: Freeze and archive Phase 0 identity

1. Re-run all required local, tracking, remote, PR, check, branch, and worktree commands.
2. Compare local HEAD, configured upstream/tracking ref, `git ls-remote` branch HEAD, and PR head SHA independently. For every mismatch, fetch without resetting, identify every divergent commit and author/source, preserve the original starting SHA, and record whether the divergence is local-only, tracking-stale, remote-new, or PR-head mismatch.
3. Continue only when the current worktree is a clean fast-forward of the newest authoritative GitHub/PR branch head. Stop before edits if histories diverge, the PR points at another branch/SHA, or continuing would require reset, rebase, force-push, or overwriting another contributor.
4. Create the timestamped external evidence root and `docs/challenge/evidence/pending/`.
5. Save raw and redacted Git/PR state without changing repository runtime files.
6. Acceptance: exact starting identity is reproducible and unrelated dirty worktrees remain untouched.

### Step 1: Reproduce baseline and challenge CI in independent clean worktrees

1. Use a detached clean baseline worktree at `de98dc4b47c67cd30ff2c3809493489577a3e4cf`.
2. Use a detached clean current worktree at the frozen challenge HEAD.
3. Install with Python 3.12 using `pip install -e ".[dev]" pytest-timeout` and Node 22 using `npm ci`.
4. Reproduce the exact workflow environment and commands under Node 22, then run the requested frontend compatibility matrix again under exact Node 24. Node 24 does not replace Node 22 CI parity and Node 22 does not replace the requested Node 24 evidence.
5. Extract every failed pytest node, first stack, assertion, and stable root-cause signature.
6. Classify each node as `BASELINE_EXISTING`, `CHALLENGE_REGRESSION`, `STALE_TEST_EXPECTATION`, `ENVIRONMENT_ONLY`, `FLAKY`, or `UNKNOWN`.
7. Write `docs/challenge/CI_BASELINE_RECONCILIATION_2026-08-27.md`.
8. Acceptance: comparison is by node and cause, not count, and both worktrees remain source-clean.

### Step 2: Repair backend CI by root-cause cluster

Each cluster is a separate TDD unit. Before changing production code, add or identify the exact failing assertion, reproduce red in the challenge worktree, apply the minimum contract-correct patch, run the focused node set green, and run all affected neighboring tests. Runtime edits are forbidden until the cluster's implementation-versus-test authority decision is recorded in the reconciliation report.

The ordered clusters are:

1. egress request/byte accounting and default budget success;
2. executor locator canonical epoch and global-control propagation;
3. approval-timeout capability cleanup and oversized-result conflict;
4. RuntimeV2 handshake capability allowlist and protocol-v2 tool intent;
5. OCI configured output cap and orchestrator executor selection return type;
6. outbox cleanup-topic ownership and retention envelope;
7. runtime reference server/provider event flow and same-turn broker resume;
8. release-gate environment inputs and canonical request hash;
9. runtime HTTP auth response contract and state progression;
10. durable runtime store migration including `runtime_artifacts`;
11. nullable artifact wire decoding and command-size bounds;
12. terminal-writer inventory and financial-domain comparison;
13. resident import fail-open contract;
14. any remaining health or live-response drift shown by the reproduced logs.

Each cluster has one focused green gate and one conventional commit with real `Verified-by:` output. A cluster that cannot be made contract-correct without weakening security blocks later deployment.

### Step 3: Reconcile npm advisories without force upgrades

1. Save fresh root and frontend audit JSON; root is marked not applicable when no lockfile exists.
2. First update `react-router-dom` and `react-router` to a compatible release at or above 7.18.2.
3. Apply the smallest compatible direct-parent or lockfile refresh that resolves Babel, brace-expansion, js-yaml, nanoid, postcss, undici, and Vite advisories.
4. Do not use overrides unless the package manager cannot select a fixed compatible transitive version and the override is covered by tests.
5. Run route, navigation, Challenge lifecycle, complete frontend tests, CI ESLint JSON 0/0, typecheck, default and enabled builds, and production bundle inspection.
6. Write `docs/challenge/NPM_AUDIT_RECONCILIATION_2026-08-27.md` with one row per advisory and dependency path.
7. Acceptance: no production-reachable high or critical remains; retained dev-only findings have source and bundle proof.

### Step 4: Database and local release gate

1. Create an isolated empty PGVector database and Redis instance with a unique temporary container/project name, unique volumes, and non-shared host ports. Cleanup removes only those exact temporary resources.
2. Run `alembic upgrade head`, `alembic heads`, and `alembic current`; require `068_fix_theater_bounds`.
3. The repository has no authoritative downgrade smoke. Do not invent one or downgrade a shared or production database; record upgrade/current/heads as the supported smoke and mark downgrade not applicable with this source evidence.
4. Do not use the current `scripts/run-challenge-e2e.sh` invocation as empty-database proof because it targets the default Compose project and persistent `skills_world` volume. Run its browser assertions only after pointing all services at the dedicated temporary PGVector/Redis instances, or first add and test an isolation option.
5. Run backend full, Challenge focused, environment checks, frontend tests on Node 22 and Node 24, CI ESLint, typecheck, build, enabled build, E2E flow, evidence validators, secret scan, `git diff --check`, and status check.
6. Acceptance: every mandatory local gate is green on one source-clean SHA.

### Step 5: Commit, ordinary push, and exact-HEAD GitHub Actions

1. Commit by logical TDD cluster; never amend or squash.
2. Ordinary push only to `challenge/webmcp-civic-copilot`.
3. Verify local, tracking, and GitHub SHA equality and ahead/behind `0 / 0`.
4. Query branch protection required status checks through the GitHub API and record the response. Cross-check that set against the exact PR head's check runs; the current workflow jobs are backend pytest, PG migration/register smoke, and frontend, but workflow text alone does not define branch protection.
5. Wait for every required check attached to the exact commit SHA and reject stale green runs from another SHA.
6. If a job fails, archive its complete log, return to the relevant TDD cluster, rerun the complete local gate, and ordinary-push the fix.
7. Acceptance: all exact-HEAD required checks are success; PR remains open, draft, and unmerged.

### Step 6: Release identity, backups, and deployment

1. Read current production backend source manifest, image IDs, health, restart counts, Alembic revision, Cloudflare version, and public asset hashes.
2. Create new timestamped backend/config/database rollback material without overwriting `/opt/skills-world/backups/option-b-cbbccc50af59-20260827T095615Z`.
3. Validate dump readability and an isolated restore listing before deployment.
4. Create an independent clean deployment worktree checked out at `RELEASE_SHA`. Before invoking the backend deploy script, require `git diff --exit-code`, an empty `git status --short`, and exact `git rev-parse HEAD`. The script itself has no SHA guard and must never be run from a dirty or moving checkout.
5. Deploy backend from that worktree; bind SHA, tree, sorted source manifest, remote build-context manifest, and resulting image digests.
6. Run migrations and require API, agent-worker, hosted-agent-worker, DB, and Redis health with zero unexplained restarts.
7. Build and deploy frontend from the same deployment worktree; record Cloudflare Version ID and local/public asset manifests.
8. Run HTTP, CORS OPTIONS/actual request, CSP/cache, browser console/network, and post-deploy severe-log checks.
9. Roll back on any listed automatic rollback condition. A rollback forces `NO-GO`.

### Step 7: ChatGPT in-app Browser three-round read-only lifecycle

For each fresh lifecycle, sample the main history sequence `Challenge(1) -> Town(0) -> Back(1) -> Forward(0) -> Back(1)`. Refresh is a separate check after a Challenge return and must preserve exactly one callable tool. Record URL, title, exact tool set, input, JSON, timestamp, duplication, leakage, and visible receipt. Use a 2.5-second settle after returning to Challenge and 0.5 seconds on Town. Ordinary Chrome or Playwright cannot substitute.

### Step 8: Chrome 149 three-round lifecycle

Use exact Chrome for Testing 149.0.7827.155 with a fresh profile and the required WebMCP/Site Tools flags. Record full version, user agent, OS, profile, extensions, flags, tool counts, calls, screenshots, and navigation behavior for the same three-round matrix.

### Step 9: Five-tool isolated production flow

Use a fresh anonymous disposable Challenge session. Cross-check each discovered schema against frontend definitions and backend request models. Exercise the real chain:

Before invoking any tool, produce a four-way inventory from frontend registration code, backend request/schema and state machine, production Browser discovery, and tests/documents. The inventory records for every actual tool: name, version or explicit absence of a version field, description, full input schema, risk class/annotations, approval requirement, write target, idempotency-key or replay rule, canonical receipt/result fields, and read-only verification method. Any four-way mismatch fails discovery for that tool.

The disposable session evidence must prove it is the Challenge-only fixture/generation and cannot address a production town ID, account, tenant, or resident. Record pre/post production-town invariants or a server-side isolation assertion showing zero real-user and real-town writes. Cleanup is not complete until the disposable generation is reset/expired and the same production invariants remain unchanged.

1. investigate and read back unchanged world plus evidence/audit;
2. preview and read back immutable diff with no world mutation;
3. deny path by trusted UI approval followed by `/revoke`, proving no commit receipt or world mutation;
4. fresh preview and trusted approval;
5. commit, read back one receipt and one world transition, race/replay the same request, and prove one success;
6. verify from the matching receipt and prove a second verify is rejected;
7. navigate, refresh, Back, and Forward at approval/result boundaries and prove no duplicate submission;
8. reset, prove a new generation and the locked v7 hash, then prove the old generation is stale.

The evidence matrix has one row per tool and explicit A-G columns. Unsupported contract cells are not silently marked not applicable:

| Tool | A discovery/schema | B preview or pre-state | C approve path | D idempotency or replay | E deny path | F navigation | G cleanup | Strict G10 consequence |
|---|---|---|---|---|---|---|---|---|
| investigate | required | required | no product contract | repeated call must preserve world | no product contract | required | reset | FAIL if independent approval/deny/receipt is mandatory |
| preview | required | tool is preview | no product contract | rebuild invalidates prior approval | no product contract before approval exists | required | reset | FAIL if independent approval/deny/receipt is mandatory |
| commit | required | exact diff shown | trusted UI approval required | same capability replay and concurrent race | trusted UI revoke before commit | required | reset | can PASS full A-G chain |
| verify | required | committed receipt pre-state | matching receipt, no new human approval | second verify rejected | no product contract | required | reset | FAIL if independent approval/deny/receipt is mandatory |
| reset | required | terminal state and locked hash | no product contract | old generation rejected | no product contract | required | new generation is cleanup | FAIL if independent approval/deny/receipt is mandatory |

Because the user-defined G10 says all five tools must independently complete preview, approve, receipt, idempotency, deny, and cleanup, the current frozen contract cannot pass G10 without a deliberate product redesign. This closeout will first record the red contract tests for the missing semantics. It will not redesign the challenge authorization model unless a minimal change can preserve the authoritative security/spec contract; otherwise G10 is `FAIL` and the final verdict is `NO-GO` after all other safe gates are completed.

### Step 10: Real wall-clock approval and session expiry

Approval test: create a fresh preview and approval, record client/server time and the approve response's `approval_expires_at`, wait until the server deadline plus at least five wall-clock seconds without revoke/commit, use GET `/challenge/session` to trigger settlement, and verify PREVIEW_READY, no world change, no success receipt, no restored capability after navigation, and rejected replay. A controlled read-only server-side evidence collector may inspect only allowlisted fields `approval.status`, expiry action/reason, state before/after, and world versions; it must never print the Redis key, session ID, CSRF token, cookie, approval ID, or full JSON.

Session test: first search for a product-supported short-lived test session or isolated test parameter. If none exists, create a separate fresh Challenge session, record idle and absolute deadlines, prove it works before expiry, leave it idle for more than 15 minutes without changing global TTL, verify EXPIRED behavior and old capability rejection, create a new session, and prove no cross-session tool or idempotency leakage. Absolute deletion is additionally observed after 20 minutes if the test remains safe and evidence can be captured before deletion. If the production environment cannot support this without global configuration changes or unsafe internal access, mark G12 `BLOCKED` and continue all other safe gates.

### Step 11: Rollback readiness and final evidence

1. Verify backend source/image restore path, frontend prior-version redeploy path, database dump/read path, and migration compatibility decision.
2. Archive all required evidence files under `docs/challenge/evidence/$RELEASE_SHA/`.
3. Update `docs/challenge/LIVE_GATE.md` and `docs/challenge/TEST_PLAN.md` to point to the exact release evidence while preserving historical `docs/webmcp-challenge` records.
4. Generate redacted `acceptance.json` and `MANIFEST.sha256`.
5. Validate every evidence artifact for UTC timestamp and exact `RELEASE_SHA`, then schema-check `acceptance.json` and verify all file hashes in `MANIFEST.sha256`.
6. Write `docs/challenge/OPTION_B_FINAL_ACCEPTANCE_2026-08-27.md`.

The final report must contain exactly the requested 19 sections: Executive Decision; Scope; Execution Plan and Actual Execution; Git and Release Identity; Changes Made; CI Baseline Reconciliation; Final Test Results; Security and npm Audit; Deployment; ChatGPT Browser Read-only Matrix; Chrome 149 Matrix; Five-tool Write Matrix; Approval Expiry; Session Expiry; Rollback Readiness; Acceptance Gate Table; Residual Risks; Evidence Index; Final Statement. Its last statement uses only the requested fixed GO or NO-GO wording.

### Step 12: Report-only commit and final push

1. Treat the deployed runtime commit as `RELEASE_SHA`.
2. Commit only docs/evidence to create `REPORT_SHA`.
3. Verify `RELEASE_SHA..REPORT_SHA` contains no runtime, dependency, workflow, deployment-script, migration, or configuration change.
4. Ordinary-push, recheck local/tracking/GitHub equality, worktree cleanliness, PR open/unmerged state, and final checks.
5. If report work changes runtime, repeat local gates, CI, deployment, and live validation with the new runtime SHA.

## 7. Mandatory local gate command families

| Gate | Exact authority |
|---|---|
| Backend full | Python 3.12, CI SQLite URL, `pytest tests -q --timeout=120 --timeout-method=signal` |
| Challenge | `python -m pytest tests/challenge -q` plus real Redis DB15 gate with no skips |
| Environment | `python -m pytest tests/test_env_example_consistency.py -q` |
| PG migration | empty PGVector DB, `alembic upgrade head`, `heads`, `current` |
| Frontend tests | Node 22 exact CI run and separate Node 24 requested compatibility run, each from `npm ci` |
| TypeScript | `npx tsc --noEmit` and build's `tsc -b` |
| ESLint CI parity | JSON output over `src`, require zero errors and zero warnings |
| Builds | default and `VITE_WEBMCP_ENABLED=true` production builds |
| Browser E2E | `scripts/run-challenge-e2e.sh` flow and benchmark specs |
| Evidence | WebMCP docs and E2E drift validators |
| Security | full audit reconciliation, bundle reachability, secret-marker scan |
| Hygiene | `git diff --check`, exact SHA, clean status |

## 8. Browser and write-test evidence matrix

| Matrix | Required rounds | Pass condition |
|---|---:|---|
| ChatGPT in-app read-only | 3 | exact expected tool, `1 to 0 to 1 to 0 to 1`, refresh callable, no duplicates/leaks |
| Chrome 149 lifecycle | 3 | same lifecycle on exact 149, fresh profile, no duplicate/stale surface |
| Five-tool closed loop | 1 complete isolated chain plus replay/deny/expiry variants | real discovery, state-appropriate execution, trusted approval, read-back, receipt where defined, replay rejection, cleanup |
| Approval expiry | 1 fresh session | real wall clock, no mutation/receipt, expired audit/capability |
| Session expiry | 1 fresh session | natural idle expiry, old access rejected, new session isolated |

## 9. Acceptance gates

All G01 through G14 are evaluated independently as `PASS`, `FAIL`, or `BLOCKED`. Any result other than `PASS` produces `NO-GO`. The report never converts an inapplicable product contract into a pass without an explicit evidence-backed mapping.

| Gate | Required proof | Primary repository artifact | Failure/block rule |
|---|---|---|---|
| G01_GIT_IDENTITY | local/tracking/GitHub equality, 0/0, clean, PR unmerged | `git-state.txt` | any mismatch or unknown remote state |
| G02_BACKEND_FULL_CI | exact full pytest exit 0 locally and on exact-HEAD CI | `backend-full-tests.txt`, `ci-summary.md` | any failure |
| G03_CHALLENGE_CI | Challenge/environment/frontend/tests/lint/typecheck/build all pass | focused frontend/backend evidence files | any required command nonzero |
| G04_DATABASE_MIGRATION | empty PG upgrade/current/heads and production current | `migration-smoke.txt`, `deployment.md` | wrong head or unsafe/unverified migration |
| G05_SECURITY | no production-reachable high/critical and secret scan pass | `npm-audit-summary.md` | reachable high/critical or incomplete attribution |
| G06_DEPLOYMENT_IDENTITY | backend/frontend exact RELEASE_SHA and local/public manifest equality | deployment manifests | source or artifact mismatch |
| G07_RUNTIME_HEALTH | page/API/CORS/containers/restarts/logs all clean | health/container/log evidence | any listed runtime failure |
| G08_CHATGPT_BROWSER_READONLY | three fresh exact-SHA in-app rounds | `chatgpt-browser-readonly-matrix.md` | unavailable host is BLOCKED; any round failure is FAIL |
| G09_CHROME149_LIFECYCLE | exact Chrome 149 three rounds | `chrome-149-matrix.md` | wrong version is BLOCKED; any round failure is FAIL |
| G10_FIVE_WRITE_TOOLS | every user-required per-tool A-G cell supported and passed | `five-tool-write-matrix.md` | unsupported required cell or failed step is FAIL |
| G11_APPROVAL_EXPIRY | real wall-clock expiry with no write/receipt and safe audit proof | `approval-expiry.md` | fake clock, unsafe proof, mutation, or replay success |
| G12_SESSION_EXPIRY | natural/supported expiry, old rejection, new isolation | `session-expiry.md` | global TTL change prohibited; unsafe/unavailable path is BLOCKED |
| G13_ROLLBACK | readable snapshots and backend/frontend/DB restore paths | `rollback.md` | unreadable or incomplete restore path |
| G14_EVIDENCE_COMPLETENESS | full file set, redaction, hashes, manifest, third-party replayability | `README.md`, `MANIFEST.sha256`, `acceptance.json` | any mandatory artifact missing or unverifiable |

## 10. Final terminal summary contract

The final response includes: Verdict; Starting HEAD; `RELEASE_SHA`; `REPORT_SHA`; new commits; GitHub Actions; backend and frontend results; final npm audit; VM212 deployed SHA/manifests; Alembic revision; Cloudflare Version; ChatGPT 3/3; Chrome 149 3/3; five-tool result; 90-second approval expiry; session expiry; complete G01-G14 table; unresolved issues; evidence directory; report path; local/tracking/remote SHAs; ahead/behind; and final worktree cleanliness.

## 11. Plan self-check

- Spec coverage: every requested phase, evidence file, browser surface, expiry path, deployment identity, rollback path, and G01-G14 decision is mapped above.
- Placeholder scan: this plan contains no unfinished code or evidence claims; conditional outcomes are explicit pass/fail branches.
- Type consistency: tool schemas, TTLs, receipt behavior, CI runtimes, and deployment entrypoints were checked against the current worktree before writing.
- Step size: implementation is divided by independently testable failure cluster; operational gates are ordered and stop deployment on red.
- Scope: unrelated dirty worktrees, main/master merge, force-push, Devpost, global TTL, and production town data are excluded.
