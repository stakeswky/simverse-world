# CI Baseline Reconciliation — Option B Closeout

Generated: 2026-08-27T16:00:00Z  
Starting challenge SHA: `cbbccc50af59380252972590545340f8f4cfc299`  
Baseline SHA: `de98dc4b47c67cd30ff2c3809493489577a3e4cf`  
Evaluated runtime source SHA: `158401eef52e412ec7cde2f65c5ffd22547d934b`

## Decision

The original backend CI state was a real release blocker: the challenge and
baseline clean worktrees shared the same 48 failing node IDs and first-failure
signatures. The challenge introduced no unique backend failure, but pre-existing
failures were not waived. All 48 were repaired or reconciled and then rerun as
one exact node set: `48 passed, 3 warnings in 4.11s`. The subsequent full suite
passed: `4520 passed, 6 skipped, 57 deselected in 343.17s`.

The clean baseline worktree also timed out once in
`tests/test_m2_arcs.py::test_co_location_counter`. It was absent from the
challenge run and from the authoritative GitHub Actions baseline/current pair,
so it is classified `ENVIRONMENT_ONLY`, not a challenge regression.

## Reproduction identity

| Surface | Baseline | Challenge before repair | Final repaired tree |
|---|---:|---:|---:|
| Python | 3.12 | 3.12 | 3.12.13 |
| Backend result | 49 failed, 4215 passed, 2 skipped | 48 failed, 4471 passed, 6 skipped, 57 deselected | 4520 passed, 6 skipped, 57 deselected |
| Shared failing nodes | 48 | 48 | 0 |
| Challenge-only nodes | 0 | 0 | 0 |
| Baseline-only local node | 1 timeout | 0 | not reproduced |
| Original 48 focused rerun | not applicable | 48 failed | 48 passed |

Raw logs and hashes are retained under
`/tmp/simverse-option-b-closeout/cbbccc50af59380252972590545340f8f4cfc299/20260827T151010Z/`.

## Per-node reconciliation

`Classification` answers the baseline comparison question. `Authority` records
whether the minimum correction belonged in production code or in a stale test
fixture/assertion. No node was skipped, xfailed, deleted, or excluded.

| # | Failed node | Classification | Authority and stable root cause | Correction / focused proof |
|---:|---|---|---|---|
| 1 | `test_lab_budgets_wiring.py::test_default_limits_do_not_terminate_happy_path` | `BASELINE_EXISTING` | Stale fixture: broker now returns a trusted egress receipt, not a raw byte count. | Fixture returns `TrustedEgressResult`; budget cluster 3/3 green. |
| 2 | `test_lab_budgets_wiring.py::test_egress_bytes_exhaustion_terminates_run` | `BASELINE_EXISTING` | Same trusted-receipt drift. | Same focused proof. |
| 3 | `test_lab_budgets_wiring.py::test_egress_requests_exhaustion_terminates_run` | `BASELINE_EXISTING` | Same trusted-receipt drift. | Same focused proof. |
| 4 | `test_lab_control_v2_regressions.py::test_durable_cancel_is_polled_after_redis_loss_and_runner_restart` | `BASELINE_EXISTING` | Stale locator omitted the canonical runtime epoch. | Fixture uses the durable locator contract; supervision cluster 5/5 green. |
| 5 | `test_lab_control_v2_regressions.py::test_global_epoch_rejects_every_stale_effect_class` | `BASELINE_EXISTING` | Stale expected control/effect epoch binding. | Assertions distinguish runtime kill epoch from an existing executor job epoch. |
| 6 | `test_lab_control_v2_regressions.py::test_global_kill_closes_admission_advances_epoch_and_fans_out_both_planes` | `BASELINE_EXISTING` | Same locator/epoch drift. | Same focused proof. |
| 7 | `test_lab_control_v2_regressions.py::test_global_kill_fault_quarantines_only_the_injected_target` | `BASELINE_EXISTING` | Same locator/epoch drift. | Same focused proof. |
| 8 | `test_lab_control_v2_regressions.py::test_global_kill_nominal_has_no_quarantine` | `BASELINE_EXISTING` | Same locator/epoch drift. | Same focused proof. |
| 9 | `test_lab_gateway_v2_supervision.py::test_http_adapter_v2_round_trip_never_uses_step_stream` | `BASELINE_EXISTING` | Stale live-response/fail-closed configuration fixture. | Explicit current gateway boundary; runtime fixture cluster 32/32 green. |
| 10 | `test_lab_gateway_v2_supervision.py::test_oversized_broker_result_is_terminal_and_effect_runs_once` | `BASELINE_EXISTING` | Stale trusted egress and durable reservation assertions. | Current trusted result and released reservations asserted. |
| 11 | `test_lab_gateway_v2_supervision.py::test_v2_approval_timeout_delivers_canonical_denied_result` | `BASELINE_EXISTING` | Stale timeout assertion ignored durable capability cleanup. | Canonical denied result plus released reservation asserted. |
| 12 | `test_lab_gateway_v2_supervision.py::test_v2_orchestrator_execute_full_sentinel_round_trip` | `BASELINE_EXISTING` | Test crossed an unstubbed external pipeline instead of its declared fake boundary. | Explicit fake pipeline boundary; no E2E claim derived from it. |
| 13 | `test_lab_http_candidate.py::test_http_candidate_scores_live_reference_server` | `BASELINE_EXISTING` | Stale fail-closed egress configuration. | Module-scoped trusted egress configuration; runtime contract 20/20 green. |
| 14 | `test_lab_oci_executor_spec.py::test_run_bounds_captured_output_to_cap` | `BASELINE_EXISTING` | Implementation defect: output cap was frozen in a default argument before runtime configuration/monkeypatch. | Resolve cap inside the call; OCI cluster 3/3 green. |
| 15 | `test_lab_orchestrator_oci_routing.py::test_fs_write_routes_to_mock_even_with_oci_enabled` | `BASELINE_EXISTING` | Stale selector assertion ignored the current `(executor, prepare)` return contract. | Unpack and verify both values; OCI cluster green. |
| 16 | `test_lab_orchestrator_oci_routing.py::test_second_action_in_same_run_is_quarantined_after_teardown_failure` | `BASELINE_EXISTING` | Same selector return drift. | Same focused proof. |
| 17 | `test_lab_outbox_runner_v2_regressions.py::test_runner_claims_only_owned_topics_and_publisher_receives_full_envelope` | `BASELINE_EXISTING` | Stale cleanup topic names/owner after the artifact cleanup protocol split. | Current requested/completed topics and full envelope asserted. |
| 18 | `test_lab_outbox_runner_v2_regressions.py::test_runner_service_starts_only_runner_owned_dispatch_topics` | `BASELINE_EXISTING` | Same topic ownership drift. | Release/audit cluster 8/8 green. |
| 19 | `test_lab_outbox_runner_v2_regressions.py::test_topic_registry_has_exactly_one_trust_plane_owner` | `BASELINE_EXISTING` | Same topic ownership drift. | Same focused proof. |
| 20 | `test_lab_protocol_v2_regressions.py::test_broker_sentinel_reaches_final_artifact_with_result_provenance` | `BASELINE_EXISTING` | Stale inline artifact and broker-result fixture. | Nullable manifest wire fields and trusted result provenance asserted. |
| 21 | `test_lab_protocol_v2_regressions.py::test_real_broker_outcome_resumes_the_same_runtime_turn[denied]` | `BASELINE_EXISTING` | Stale real-broker fixture lacked the current trusted egress grant. | Trusted grant/usage fixture; same-turn result preserved. |
| 22 | `test_lab_protocol_v2_regressions.py::test_real_broker_outcome_resumes_the_same_runtime_turn[failed]` | `BASELINE_EXISTING` | Same trusted egress drift. | Same focused proof. |
| 23 | `test_lab_protocol_v2_regressions.py::test_real_broker_outcome_resumes_the_same_runtime_turn[succeeded]` | `BASELINE_EXISTING` | Same trusted egress drift. | Same focused proof. |
| 24 | `test_lab_protocol_v2_regressions.py::test_runtime_pauses_on_intent_without_fake_observation_final_or_artifact` | `BASELINE_EXISTING` | Stale RuntimeV2 capability/artifact expectation. | Frozen protocol-v2 intent and manifest contract asserted. |
| 25 | `test_lab_protocol_v2_regressions.py::test_scoped_auth_exact_retry_is_idempotent_but_cross_binding_replay_is_denied` | `BASELINE_EXISTING` | Stale authenticated HTTP response shape. | Current full health/liveness and binding response asserted. |
| 26 | `test_lab_release_gate.py::test_every_release_run_requires_disposable_and_image_identity_inputs` | `BASELINE_EXISTING` | Stale required-environment inventory. | Exact current 12-variable inventory and EdDSA requirements asserted. |
| 27 | `test_lab_release_gate.py::test_request_hash_is_canonical_and_unresolved_d0_is_rejected` | `BASELINE_EXISTING` | Implementation defect: Python canonical JSON lacked the trailing newline emitted by `jq -cS`, changing the D0 hash. | Canonical payload includes the newline; release/audit cluster green. |
| 28 | `test_lab_retention.py::test_cleanup_writes_outbox_event_with_full_payload` | `BASELINE_EXISTING` | Stale retention topic/envelope expectation. | Current cleanup-completed topic and payload asserted. |
| 29 | `test_lab_runtime_ref.py::test_agent_loop_produces_steps_and_intends_tools` | `BASELINE_EXISTING` | Stale fail-closed egress/provider fixture. | Explicit trusted egress fixture; runtime contract green. |
| 30 | `test_lab_runtime_ref_server.py::test_adapter_drives_server_end_to_end` | `BASELINE_EXISTING` | Implementation plus fixture drift: reference server advertised forbidden v2 upload capabilities and fixture lacked current auth/egress inputs. | Remove forbidden capabilities and align trusted inputs; runtime contract 20/20 green. |
| 31 | `test_lab_runtime_ref_server.py::test_server_protocol_roundtrip` | `BASELINE_EXISTING` | Same reference-server protocol drift. | Same focused proof. |
| 32 | `test_lab_runtime_v2_http_auth.py::test_control_surfaces_require_runtime_control_before_lookup` | `BASELINE_EXISTING` | Stale response body expected partial rather than current fail-closed full contract. | Full response shapes asserted. |
| 33 | `test_lab_runtime_v2_http_auth.py::test_create_is_fail_closed_and_accepts_current_and_next_keys` | `BASELINE_EXISTING` | Same HTTP auth response drift. | Current/next key and fail-closed behavior retained. |
| 34 | `test_lab_runtime_v2_http_auth.py::test_goal_and_result_loop_preserves_auth_before_lookup` | `BASELINE_EXISTING` | Same HTTP auth response drift. | Same focused proof. |
| 35 | `test_lab_runtime_v2_loop.py::test_goal_receipt_and_paused_turn_survive_runtime_restart` | `BASELINE_EXISTING` | Stale manifest/provider fixture after protocol-v2 artifact hardening. | Current manifest wire and trusted fixture asserted. |
| 36 | `test_lab_runtime_v2_loop.py::test_handshake_is_authenticated_and_hashes_the_frozen_protocol` | `BASELINE_EXISTING` | Implementation defect: handshake advertised forbidden upload capabilities. | Capability allowlist restored to the frozen protocol. |
| 37 | `test_lab_runtime_v2_loop.py::test_non_success_result_is_terminal_without_success_artifact[denied]` | `BASELINE_EXISTING` | Stale inline `text_md` artifact assertion. | Manifest fields and terminal non-success behavior asserted. |
| 38 | `test_lab_runtime_v2_loop.py::test_non_success_result_is_terminal_without_success_artifact[failed]` | `BASELINE_EXISTING` | Same artifact wire drift. | Same focused proof. |
| 39 | `test_lab_runtime_v2_loop.py::test_result_binding_redaction_and_receipt_survive_restart` | `BASELINE_EXISTING` | Stale provider/result fixture. | Current redacted binding and receipt persistence asserted. |
| 40 | `test_lab_runtime_v2_loop.py::test_result_effect_recovers_when_receipt_commit_fails` | `BASELINE_EXISTING` | Stale provider/result fixture. | Current recovery and one-effect semantics asserted. |
| 41 | `test_lab_runtime_v2_loop.py::test_result_payload_uses_protocol_command_size_cap` | `BASELINE_EXISTING` | Stale inline artifact payload expectation. | Frozen command-size cap applied to the current manifest wire. |
| 42 | `test_lab_runtime_v2_loop.py::test_result_receipt_retry_does_not_consume_the_next_intent` | `BASELINE_EXISTING` | Stale provider/result fixture. | Retry and next-intent ordering asserted. |
| 43 | `test_lab_runtime_v2_loop.py::test_result_rejects_wrong_turn_and_second_action_binding` | `BASELINE_EXISTING` | Stale provider/result fixture. | Current binding rejection retained. |
| 44 | `test_lab_runtime_v2_loop.py::test_runtime_store_migrates_phase2_durable_volume` | `BASELINE_EXISTING` | Implementation defect: v2-to-v3 migration altered `runtime_artifacts` before ensuring the legacy table existed. | Create legacy v2 table before ALTER; runtime contract green. |
| 45 | `test_lab_runtime_v2_supervision_contract.py::test_runtime_v2_artifact_decoder_accepts_exact_nullable_wire_fields` | `BASELINE_EXISTING` | Stale decoder expected removed inline content. | Exact nullable manifest wire fields asserted. |
| 46 | `test_lab_terminal_writer_audit.py::test_d1a_comparison_preserves_one_financial_domain` | `BASELINE_EXISTING` | Stale financial-domain comparison inventory. | Current domain ownership comparison asserted. |
| 47 | `test_lab_terminal_writer_audit.py::test_terminal_writer_inventory_has_no_unknown_or_missing_sites` | `BASELINE_EXISTING` | Stale audited-writer allowlist after reviewed production additions. | Add 25 current reviewed sites and remove one stale site. |
| 48 | `test_map_integration.py::test_import_resident_emits_canonical_location_id` | `BASELINE_EXISTING` | Test input indentation took a different parser path and mocked more than the fail-open SBTI boundary. | Canonical three-layer input; only SBTI fail-open mocked; 1/1 green. |

## Baseline-only local timeout

| Failed node | Classification | Reason | Disposition |
|---|---|---|---|
| `test_m2_arcs.py::test_co_location_counter` | `ENVIRONMENT_ONLY` | One 12-second timeout only in the detached baseline local run; absent from current, exact Actions comparison, and final suite. | Retained as an environmental observation; no product/test mutation made for it. |

## Final proof and warnings

- Original node set: `48 passed, 3 warnings in 4.11s`.
- Initial post-fix full backend: `4520 passed, 6 skipped, 57 deselected, 395
  warnings in 343.17s`.
- Final clean candidate `3da1dac7010db6db86ce68324fb79e322003556d`:
  `4520 passed, 6 skipped, 57 deselected, 40 warnings in 345.89s`.
- Real Redis Challenge gate with skip-fail enabled: `259 passed, 1 warning`.
- Empty PGVector migration and API registration smoke: head/current
  `068_fix_theater_bounds`, health and registration passed.
- Both warning summaries are deprecations/test-fixture notices (principally
  Pydantic class config, test JWT length, AsyncMock/SQLAlchemy fixture cleanup).
  They did not hide a failure and remain listed as residual maintenance, not
  converted into release success criteria. The final candidate count is the
  controlling number.
