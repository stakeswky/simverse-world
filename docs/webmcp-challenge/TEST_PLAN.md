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

## Option B Phase 6 backend contract and baseline comparison

Recorded on `2026-08-27`. The authoritative pre-Option-B failure baseline is
GitHub Actions source SHA
`de98dc4b47c67cd30ff2c3809493489577a3e4cf`, run `32968059066`, job
`98175015320`. Its exact 48 sorted node IDs are checked in at
`docs/webmcp-challenge/BACKEND_BASELINE_FAILURES.txt`.

| Gate | Actual result |
|---|---|
| `python -m pytest tests/challenge -q` | PASS — 255 passed, 4 environment-gated real-Redis skips, exit 0 |
| `python -m pytest tests/test_env_example_consistency.py -q` | PASS — 23 passed, exit 0 |
| Combined Challenge + environment-example replay | PASS — 278 passed, 4 environment-gated real-Redis skips, exit 0 |
| `python -m pytest tests -q --timeout=120 --timeout-method=signal` | EXPECTED NONZERO — 48 failed, 4471 passed, 6 skipped, 57 deselected |
| Baseline group | 48 nodes; SHA-256 `16967ca0fd38fa8a827014ff1dbc43eb043008139c8c5d2aa676ce1532504919` |
| Current group | 48 nodes; SHA-256 `16967ca0fd38fa8a827014ff1dbc43eb043008139c8c5d2aa676ce1532504919` |
| Removed group (`baseline - current`) | 0 nodes — empty |
| New group (`current - baseline`) | 0 nodes — empty |

The current group is reproduced below so the comparison remains reviewable
without relying on the temporary pytest log:

```text
tests/test_lab_budgets_wiring.py::test_default_limits_do_not_terminate_happy_path
tests/test_lab_budgets_wiring.py::test_egress_bytes_exhaustion_terminates_run
tests/test_lab_budgets_wiring.py::test_egress_requests_exhaustion_terminates_run
tests/test_lab_control_v2_regressions.py::test_durable_cancel_is_polled_after_redis_loss_and_runner_restart
tests/test_lab_control_v2_regressions.py::test_global_epoch_rejects_every_stale_effect_class
tests/test_lab_control_v2_regressions.py::test_global_kill_closes_admission_advances_epoch_and_fans_out_both_planes
tests/test_lab_control_v2_regressions.py::test_global_kill_fault_quarantines_only_the_injected_target
tests/test_lab_control_v2_regressions.py::test_global_kill_nominal_has_no_quarantine
tests/test_lab_gateway_v2_supervision.py::test_http_adapter_v2_round_trip_never_uses_step_stream
tests/test_lab_gateway_v2_supervision.py::test_oversized_broker_result_is_terminal_and_effect_runs_once
tests/test_lab_gateway_v2_supervision.py::test_v2_approval_timeout_delivers_canonical_denied_result
tests/test_lab_gateway_v2_supervision.py::test_v2_orchestrator_execute_full_sentinel_round_trip
tests/test_lab_http_candidate.py::test_http_candidate_scores_live_reference_server
tests/test_lab_oci_executor_spec.py::test_run_bounds_captured_output_to_cap
tests/test_lab_orchestrator_oci_routing.py::test_fs_write_routes_to_mock_even_with_oci_enabled
tests/test_lab_orchestrator_oci_routing.py::test_second_action_in_same_run_is_quarantined_after_teardown_failure
tests/test_lab_outbox_runner_v2_regressions.py::test_runner_claims_only_owned_topics_and_publisher_receives_full_envelope
tests/test_lab_outbox_runner_v2_regressions.py::test_runner_service_starts_only_runner_owned_dispatch_topics
tests/test_lab_outbox_runner_v2_regressions.py::test_topic_registry_has_exactly_one_trust_plane_owner
tests/test_lab_protocol_v2_regressions.py::test_broker_sentinel_reaches_final_artifact_with_result_provenance
tests/test_lab_protocol_v2_regressions.py::test_real_broker_outcome_resumes_the_same_runtime_turn[denied]
tests/test_lab_protocol_v2_regressions.py::test_real_broker_outcome_resumes_the_same_runtime_turn[failed]
tests/test_lab_protocol_v2_regressions.py::test_real_broker_outcome_resumes_the_same_runtime_turn[succeeded]
tests/test_lab_protocol_v2_regressions.py::test_runtime_pauses_on_intent_without_fake_observation_final_or_artifact
tests/test_lab_protocol_v2_regressions.py::test_scoped_auth_exact_retry_is_idempotent_but_cross_binding_replay_is_denied
tests/test_lab_release_gate.py::test_every_release_run_requires_disposable_and_image_identity_inputs
tests/test_lab_release_gate.py::test_request_hash_is_canonical_and_unresolved_d0_is_rejected
tests/test_lab_retention.py::test_cleanup_writes_outbox_event_with_full_payload
tests/test_lab_runtime_ref.py::test_agent_loop_produces_steps_and_intends_tools
tests/test_lab_runtime_ref_server.py::test_adapter_drives_server_end_to_end
tests/test_lab_runtime_ref_server.py::test_server_protocol_roundtrip
tests/test_lab_runtime_v2_http_auth.py::test_control_surfaces_require_runtime_control_before_lookup
tests/test_lab_runtime_v2_http_auth.py::test_create_is_fail_closed_and_accepts_current_and_next_keys
tests/test_lab_runtime_v2_http_auth.py::test_goal_and_result_loop_preserves_auth_before_lookup
tests/test_lab_runtime_v2_loop.py::test_goal_receipt_and_paused_turn_survive_runtime_restart
tests/test_lab_runtime_v2_loop.py::test_handshake_is_authenticated_and_hashes_the_frozen_protocol
tests/test_lab_runtime_v2_loop.py::test_non_success_result_is_terminal_without_success_artifact[denied]
tests/test_lab_runtime_v2_loop.py::test_non_success_result_is_terminal_without_success_artifact[failed]
tests/test_lab_runtime_v2_loop.py::test_result_binding_redaction_and_receipt_survive_restart
tests/test_lab_runtime_v2_loop.py::test_result_effect_recovers_when_receipt_commit_fails
tests/test_lab_runtime_v2_loop.py::test_result_payload_uses_protocol_command_size_cap
tests/test_lab_runtime_v2_loop.py::test_result_receipt_retry_does_not_consume_the_next_intent
tests/test_lab_runtime_v2_loop.py::test_result_rejects_wrong_turn_and_second_action_binding
tests/test_lab_runtime_v2_loop.py::test_runtime_store_migrates_phase2_durable_volume
tests/test_lab_runtime_v2_supervision_contract.py::test_runtime_v2_artifact_decoder_accepts_exact_nullable_wire_fields
tests/test_lab_terminal_writer_audit.py::test_d1a_comparison_preserves_one_financial_domain
tests/test_lab_terminal_writer_audit.py::test_terminal_writer_inventory_has_no_unknown_or_missing_sites
tests/test_map_integration.py::test_import_resident_emits_canonical_location_id
```

The removed and new groups are both intentionally empty. The first full run
found one new environment-example consistency failure for the Challenge cookie
and origin settings; documenting those production settings removed it before
the recorded comparison above.

## Option B Phase 6 five-tool frontend contract

Recorded on `2026-08-27` with Node `22.23.2` and npm `10.9.8`. The new aggregate contract first
failed because `WEBMCP_TOOLS.md` still described only the Day-0 probe and
obsolete planned names; it passed after the document was replaced with the
implemented five-tool state surface.

| Gate | Actual result |
|---|---|
| `vitest run src/webmcp/challengeContract.test.ts` | PASS — 1 file, 8 tests |
| `npm run test` | PASS — 77 files, 416 tests |
| `npm run lint` | PASS — exit 0 |
| `npx tsc --noEmit` | PASS — exit 0 |
| Default `npm run build` | PASS — 934 modules transformed |
| `VITE_WEBMCP_ENABLED=true npm run build` | PASS — 934 modules transformed |
| Built-asset secret-marker scan | PASS — zero matches |
| Final five-name scan | PASS — all five names in the enabled `ChallengePage` chunk |
| Legacy status-name scan | PASS — found only in the `registerChallengeStatusTool` diagnostics chunk |

The aggregate contract locks exact names/descriptions/schemas/annotations,
description and input-schema budgets, five compact success outputs, fixed safe
invalid/aborted errors, visible Agent Activity updates, every state surface,
old-handler staleness (including an old registration that resolves after a
newer epoch), teardown unregistration, unsupported-host fallback, and the
documentation catalogue. Existing `ChallengePage` tests in the full gate
also lock ordinary UI fallback, `diagnostics=1` isolation, and full-document
route-exit links.

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

### Real Redis CAS evidence

Recorded on `2026-08-27` against `redis://127.0.0.1:6379/15` with Redis
`8.10.1`. Colima could not start because its existing VZ disk was reported as
already attached, so the required gate used a temporary Homebrew Redis process
bound only to `127.0.0.1`, with persistence disabled. This remains real Redis
server evidence; fakeredis is not used by these nodes.

| Node id | Required invariant | Actual result |
|---|---|---|
| `tests/challenge/test_concurrency_real_redis.py::test_real_redis_two_concurrent_commits_consume_approval_once` | one commit success, loser `APPROVAL_REPLAYED`, one receipt, one budget delta, one commit audit | PASS |
| `tests/challenge/test_concurrency_real_redis.py::test_real_redis_commit_racing_revoke_has_one_winner` | exactly one race winner; committed or revoked state is internally complete; replay has zero successes | PASS |
| `tests/challenge/test_concurrency_real_redis.py::test_real_redis_commit_racing_reset_has_one_winner` | exactly one race winner; old session/approval are both retained or both replaced; replay has zero successes | PASS |
| `tests/challenge/test_concurrency_real_redis.py::test_real_redis_watch_retry_rereads_state_and_reinvokes_mutator` | Redis server raises the real `WATCH` conflict; retry observes budgets `[300, 250]` and commits `249` | PASS |

Required-gate evidence is stored in
`/tmp/simverse-option-b-real-redis.log` and
`/tmp/simverse-option-b-real-redis.exit`: `4 passed`, exit `0`, and no
`skipped` marker. The fixture rejects non-loopback hosts, URL/query database
overrides, and any client whose resolved database is not 15. Each test
pre-registers random `real-<uuid>` keys and deletes only those exact DB 15
keys; namespace and `DBSIZE` snapshots must return to their pre-test values,
while DB 0 must remain unchanged. The recorded isolated run began and ended
with DB 15 and DB 0 both at `DBSIZE 0`.

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
