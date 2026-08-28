import json
import os
from pathlib import Path

import pytest

from scripts.run_lab_release_gate import (
    AC01_TO_AC20,
    COMMON_REQUIRED_ENV,
    GateError,
    PREPUSH_STEP,
    RUN_ALL_STEPS,
    canonical_json,
    is_secret_env_path,
    path_is_within,
    require_external_path,
    sha256_bytes,
    validate_d0,
    validate_manifest,
    validate_required_env,
    verify_dirty_manifest,
    validate_visual_receipt,
)


REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_RUN_ALL_STEP_IDS = [
    "run-all:ac01-terminalization",
    "run-all:ac04-writer-roles",
    "run-all:ac05-protocol-migration",
    "run-all:ac06-runtime-session",
    "run-all:ac07-runtime-result-loop",
    "run-all:ac10-executor-control",
    "run-all:ac11-delivery-recovery",
    "run-all:ac12-global-kill",
    "run-all:ac13-outbox-owners",
    "run-all:ac14-service-identity",
    "run-all:ac15-d0-topology",
    "run-all:ac16-db-roles",
    "run-all:ac17-v15-flow",
    "run-all:ac18-world-postgres",
    "run-all:ac19-visual-receipts",
    "run-all:ac20-asset-release",
    "run-all:backend-full",
    "run-all:frontend-full",
    "run-all:capacity",
]

EXPECTED_AC05_UNIT_TEST_PATHS = (
    "tests/test_lab_protocol_v2_regressions.py",
    "tests/test_lab_protocol_v2_consumer_gate.py",
)

EXPECTED_AC07_UNIT_TEST_PATHS = (
    "tests/test_lab_protocol_v2_regressions.py",
    "tests/test_lab_runtime_contract.py",
    "tests/test_lab_runtime_ref.py",
    "tests/test_lab_runtime_ref_server.py",
    "tests/test_lab_runtime_v2_http_auth.py",
    "tests/test_lab_runtime_v2_loop.py",
    "tests/test_lab_runtime_v2_store_auth.py",
    "tests/test_lab_runtime_v2_supervision_contract.py",
    "tests/test_lab_gateway_v2_supervision.py",
)


def test_manifest_is_the_unique_ac01_to_ac21_execution_source():
    result = validate_manifest()

    assert result["step_ids"] == EXPECTED_RUN_ALL_STEP_IDS
    assert set(result["ac_coverage"]) == AC01_TO_AC20
    assert all(len(owners) == 1 for owners in result["ac_coverage"].values())
    assert PREPUSH_STEP.step_id == "prepush:ac21-release"
    assert PREPUSH_STEP.step_id not in result["step_ids"]
    assert all(command.cwd in {"backend", "frontend"} for step in RUN_ALL_STEPS for command in step.commands)
    assert all(isinstance(command.argv, tuple) for step in RUN_ALL_STEPS for command in step.commands)


def test_ac05_manifest_covers_v2_admission_and_consumer_canary_gates():
    step = next(step for step in RUN_ALL_STEPS if step.step_id == "run-all:ac05-protocol-migration")

    unit_command, _postgres_command = step.commands
    assert tuple(arg for arg in unit_command.argv if arg.startswith("tests/")) == EXPECTED_AC05_UNIT_TEST_PATHS


def test_ac07_manifest_covers_the_complete_deterministic_p3_result_loop():
    step = next(step for step in RUN_ALL_STEPS if step.step_id == "run-all:ac07-runtime-result-loop")

    assert step.acs == ("AC07", "AC08", "AC09")
    assert step.required_env == (
        "LAB_POSTGRES_REQUIRED",
        "LAB_TEST_DATABASE_URL",
    )
    assert tuple(command.cwd for command in step.commands) == ("backend", "backend")

    unit_command, postgres_command = step.commands
    assert tuple(arg for arg in unit_command.argv if arg.startswith("tests/")) == EXPECTED_AC07_UNIT_TEST_PATHS
    assert unit_command.argv[-3:] == ("-k", "not real_llm", "-q")
    assert postgres_command.argv[-4:] == (
        "-m",
        "lab_postgres",
        "tests/integration/test_lab_supervision_v2_postgres.py",
        "-q",
    )


def test_every_release_run_requires_disposable_and_image_identity_inputs():
    assert COMMON_REQUIRED_ENV == {
        "LAB_RELEASE_GATE",
        "LAB_RELEASE_RUN_ID",
        "LAB_REDIS_DISPOSABLE_TOKEN",
        "LAB_RUNTIME_SERVICE_IMAGE_DIGEST",
        "LAB_EXECUTOR_SERVICE_IMAGE_DIGEST",
        "LAB_ARTIFACT_INGEST_IMAGE_DIGEST",
        "LAB_ARTIFACT_SCANNER_IMAGE_DIGEST",
        "LAB_ARTIFACT_CLEANUP_IMAGE_DIGEST",
        "LAB_ARTIFACT_RECEIPT_ALGORITHM",
        "LAB_ARTIFACT_INGEST_RECEIPT_ALGORITHM",
        "LAB_ARTIFACT_SCANNER_RECEIPT_ALGORITHM",
        "LAB_ARTIFACT_CLEANUP_RECEIPT_ALGORITHM",
    }

    required = validate_required_env(
        (),
        {
            name: (
                "true"
                if name == "LAB_RELEASE_GATE"
                else "EdDSA"
                if name.endswith("RECEIPT_ALGORITHM")
                else "present"
            )
            for name in COMMON_REQUIRED_ENV
        },
    )
    assert required == sorted(COMMON_REQUIRED_ENV)


def test_required_release_environment_fails_closed():
    with pytest.raises(GateError, match="missing required release environment"):
        validate_required_env(RUN_ALL_STEPS, {})


def test_evidence_and_trust_inputs_cannot_live_in_a_worktree(tmp_path):
    inside = REPO_ROOT / "backend"
    assert path_is_within(inside, REPO_ROOT)
    with pytest.raises(GateError, match="outside every Git worktree"):
        require_external_path(inside, REPO_ROOT, "evidence")


def test_secret_env_filter_allows_examples_only():
    assert is_secret_env_path("backend/.env") is True
    assert is_secret_env_path("deploy/backend/.env.production") is True
    assert is_secret_env_path("backend/.env.example") is False


def test_dirty_manifest_requires_external_pinned_evidence(tmp_path):
    inside = REPO_ROOT / "backend" / "fake-dirty-manifest.json"
    with pytest.raises(GateError, match="outside every Git worktree"):
        verify_dirty_manifest(REPO_ROOT, inside, expected_sha256="unused")

    external = tmp_path / "dirty-manifest.json"
    external.write_text("{}", encoding="utf-8")
    external.chmod(0o444)
    with pytest.raises(GateError, match="digest does not match"):
        verify_dirty_manifest(REPO_ROOT, external, expected_sha256="0" * 64)


def test_request_hash_is_canonical_and_unresolved_d0_is_rejected():
    request_path = REPO_ROOT / ".omx/approvals/lab-agent-services-d0.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))

    assert request["request_hash"] == sha256_bytes(canonical_json(request["request"]))
    with pytest.raises(GateError, match="not approval-eligible|unresolved"):
        validate_d0(REPO_ROOT, request_path, {})


def test_visual_receipt_requires_all_fifteen_passing_states(tmp_path):
    sha = "a" * 40
    states = [
        {
            "id": f"state-{index}",
            "verdict": "pass",
            "score": 90,
            "category_match": True,
            "overlap_count": 0,
            "overflow_count": 0,
            "min_touch_target_px": 44,
        }
        for index in range(15)
    ]
    receipt = tmp_path / "visual.json"
    receipt.write_text(json.dumps({
        "sha": sha,
        "states": states,
        "console_errors": [],
        "network_errors": [],
    }), encoding="utf-8")

    result = validate_visual_receipt(str(receipt), REPO_ROOT, sha)
    assert result["state_count"] == 15
    assert result["minimum_score"] == 90

    states[0]["overlap_count"] = 1
    receipt.write_text(json.dumps({
        "sha": sha,
        "states": states,
        "console_errors": [],
        "network_errors": [],
    }), encoding="utf-8")
    with pytest.raises(GateError, match="visual state failed"):
        validate_visual_receipt(str(receipt), REPO_ROOT, sha)


def test_release_gate_skip_hook_sets_nonzero_exit(monkeypatch):
    from tests import conftest

    class Reporter:
        stats = {"skipped": [object()]}

    class Plugins:
        @staticmethod
        def get_plugin(name):
            return Reporter() if name == "terminalreporter" else None

    class Session:
        config = type("Config", (), {"pluginmanager": Plugins()})()
        exitstatus = pytest.ExitCode.OK

    monkeypatch.setenv("LAB_RELEASE_GATE", "1")
    session = Session()
    conftest.pytest_sessionfinish(session, pytest.ExitCode.OK)

    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
