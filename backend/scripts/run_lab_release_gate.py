#!/usr/bin/env python3
"""Canonical, root-anchored Lab Agent release gate.

The AC matrix is documentation. This manifest is the sole executable command
source. Required infrastructure and evidence always fail closed.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlparse


class GateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Command:
    cwd: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class Step:
    step_id: str
    acs: tuple[str, ...]
    commands: tuple[Command, ...] = ()
    required_env: tuple[str, ...] = ()
    timeout_s: int = 900
    receipt_kind: str | None = None


PYTEST = (sys.executable, "-m", "pytest")

RUN_ALL_STEPS: tuple[Step, ...] = (
    Step(
        "run-all:ac01-terminalization",
        ("AC01", "AC02", "AC03"),
        (Command("backend", PYTEST + ("-m", "lab_postgres", "tests/integration/test_lab_terminalization_postgres.py", "-q")),),
        ("LAB_POSTGRES_REQUIRED", "LAB_TEST_DATABASE_URL"),
        1200,
    ),
    Step(
        "run-all:ac04-writer-roles",
        ("AC04",),
        (Command("backend", PYTEST + ("-m", "lab_postgres", "tests/integration/test_lab_writer_roles_postgres.py", "-q")),),
        ("LAB_FLEET_MANIFEST", "LAB_POSTGRES_REQUIRED", "LAB_TEST_DATABASE_URL"),
        900,
    ),
    Step(
        "run-all:ac05-protocol-migration",
        ("AC05",),
        (
            Command(
                "backend",
                PYTEST
                + (
                    "tests/test_lab_protocol_v2_regressions.py",
                    "tests/test_lab_protocol_v2_consumer_gate.py",
                    "-q",
                ),
            ),
            Command("backend", PYTEST + ("-m", "lab_postgres", "tests/integration/test_lab_migration_v2_postgres.py", "-q")),
        ),
        ("LAB_POSTGRES_REQUIRED", "LAB_TEST_DATABASE_URL"),
        1200,
    ),
    Step(
        "run-all:ac06-runtime-session",
        ("AC06",),
        (Command("backend", PYTEST + ("-m", "lab_postgres", "tests/integration/test_lab_runtime_v2_postgres.py", "-q")),),
        ("LAB_POSTGRES_REQUIRED", "LAB_TEST_DATABASE_URL", "LAB_RUNTIME_BASE_URL"),
        900,
    ),
    Step(
        "run-all:ac07-runtime-result-loop",
        ("AC07", "AC08", "AC09"),
        (
            Command(
                "backend",
                PYTEST
                + (
                    "tests/test_lab_protocol_v2_regressions.py",
                    "tests/test_lab_runtime_contract.py",
                    "tests/test_lab_runtime_ref.py",
                    "tests/test_lab_runtime_ref_server.py",
                    "tests/test_lab_runtime_v2_http_auth.py",
                    "tests/test_lab_runtime_v2_loop.py",
                    "tests/test_lab_runtime_v2_store_auth.py",
                    "tests/test_lab_runtime_v2_supervision_contract.py",
                    "tests/test_lab_gateway_v2_supervision.py",
                    "-k",
                    "not real_llm",
                    "-q",
                ),
            ),
            Command("backend", PYTEST + ("-m", "lab_postgres", "tests/integration/test_lab_supervision_v2_postgres.py", "-q")),
        ),
        ("LAB_POSTGRES_REQUIRED", "LAB_TEST_DATABASE_URL"),
        1200,
    ),
    Step(
        "run-all:ac10-executor-control",
        ("AC10",),
        (Command("backend", PYTEST + ("-m", "lab_oci", "tests/integration/test_lab_executor_control_oci.py", "-q")),),
        ("LAB_OCI_REQUIRED", "LAB_OCI_IMAGE", "LAB_EXECUTOR_BASE_URL"),
        1200,
    ),
    Step(
        "run-all:ac11-delivery-recovery",
        ("AC11",),
        (Command("backend", PYTEST + ("-m", "lab_redis and lab_postgres", "tests/integration/test_lab_delivery_recovery.py", "-q")),),
        ("LAB_POSTGRES_REQUIRED", "LAB_REDIS_REQUIRED", "LAB_TEST_DATABASE_URL", "LAB_TEST_REDIS_URL"),
        1200,
    ),
    Step(
        "run-all:ac12-global-kill",
        ("AC12",),
        (Command("backend", PYTEST + ("-m", "lab_staging", "tests/integration/test_lab_global_kill_staging.py", "-q")),),
        ("LAB_STAGING_REQUIRED", "LAB_KILL_DRILL", "LAB_RUNTIME_BASE_URL", "LAB_EXECUTOR_BASE_URL"),
        1200,
    ),
    Step(
        "run-all:ac13-outbox-owners",
        ("AC13",),
        (Command("backend", PYTEST + ("-m", "lab_postgres and lab_redis", "tests/integration/test_lab_outbox_owners.py", "-q")),),
        ("LAB_POSTGRES_REQUIRED", "LAB_REDIS_REQUIRED", "LAB_TEST_DATABASE_URL", "LAB_TEST_REDIS_URL"),
        900,
    ),
    Step(
        "run-all:ac14-service-identity",
        ("AC14",),
        (
            Command("backend", PYTEST + ("tests/test_lab_service_auth.py", "-q")),
            Command("backend", PYTEST + ("-m", "lab_staging", "tests/integration/test_lab_service_identity_staging.py", "-q")),
        ),
        (
            "LAB_STAGING_REQUIRED",
            "LAB_RUNTIME_BASE_URL",
            "LAB_EXECUTOR_BASE_URL",
            "LAB_ARTIFACT_INGEST_BASE_URL",
            "LAB_ARTIFACT_SCANNER_BASE_URL",
            "LAB_ARTIFACT_CLEANUP_BASE_URL",
        ),
        1200,
    ),
    Step(
        "run-all:ac15-d0-topology",
        ("AC15",),
        receipt_kind="d0",
        required_env=(
            "LAB_D0_ATTESTATION",
            "LAB_D0_TRUST_ROOT",
            "LAB_D0_APPROVER_POLICY",
            "LAB_NETWORK_POLICY_EVIDENCE",
        ),
    ),
    Step(
        "run-all:ac16-db-roles",
        ("AC16",),
        (Command("backend", PYTEST + ("-m", "lab_postgres", "tests/integration/test_lab_db_roles_postgres.py", "-q")),),
        ("LAB_POSTGRES_REQUIRED", "LAB_TEST_DATABASE_URL"),
        900,
    ),
    Step(
        "run-all:ac17-v15-flow",
        ("AC17",),
        (Command("backend", PYTEST + ("-m", "lab_staging", "tests/integration/test_lab_v15_release.py", "-q")),),
        ("LAB_STAGING_REQUIRED", "LAB_V15_RECEIPT"),
        1800,
    ),
    Step(
        "run-all:ac18-world-postgres",
        ("AC18",),
        (
            Command("backend", PYTEST + ("tests/test_world_revision.py", "tests/test_lab_world_e2e.py", "-q")),
            Command("backend", PYTEST + ("-m", "lab_postgres", "tests/integration/test_lab_world_atomic_postgres.py", "-q")),
        ),
        ("LAB_POSTGRES_REQUIRED", "LAB_TEST_DATABASE_URL"),
        1200,
    ),
    Step(
        "run-all:ac19-visual-receipts",
        ("AC19",),
        receipt_kind="visual",
        required_env=("LAB_VISUAL_RECEIPT",),
    ),
    Step(
        "run-all:ac20-asset-release",
        ("AC20",),
        (
            Command("frontend", ("npm", "run", "map:verify-art")),
            Command("frontend", ("npm", "run", "assets:verify")),
            Command("frontend", ("npm", "run", "assets:verify:release")),
        ),
        ("LAB_RELEASE_GATE",),
        600,
    ),
    Step(
        "run-all:backend-full",
        (),
        (Command("backend", PYTEST + ("tests/", "-q")),),
        ("LAB_RELEASE_GATE",),
        1800,
    ),
    Step(
        "run-all:frontend-full",
        (),
        (
            Command("frontend", ("npm", "run", "lint")),
            Command("frontend", ("npx", "tsc", "-b")),
            Command("frontend", ("npm", "run", "test", "--", "--run")),
            Command("frontend", ("npm", "run", "build")),
        ),
        (),
        1200,
    ),
    Step(
        "run-all:capacity",
        (),
        (Command("backend", PYTEST + ("-m", "lab_capacity", "tests/integration/test_lab_capacity_release.py", "-q")),),
        ("LAB_CAPACITY_REQUIRED", "LAB_STAGING_REQUIRED"),
        1800,
    ),
)

PREPUSH_STEP = Step(
    "prepush:ac21-release",
    ("AC21",),
    receipt_kind="prepush",
    required_env=("LAB_D0_ATTESTATION", "LAB_D0_TRUST_ROOT", "LAB_D0_APPROVER_POLICY"),
)

REQUIRED_MARKERS = {"lab_postgres", "lab_redis", "lab_staging", "lab_capacity", "lab_oci"}
AC01_TO_AC20 = {f"AC{number:02d}" for number in range(1, 21)}
SENSITIVE_ENV_FRAGMENTS = ("SECRET", "TOKEN", "PASSWORD", "KEY", "ATTESTATION", "TRUST_ROOT")
COMMON_REQUIRED_ENV = {
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
APPROVED_DIRTY_MANIFEST_SHA256 = (
    "342ef37e2125c39cf96e0752047b37d73b3302f0d074a7cbf0bce877594b7b82"
)


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def run_git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args], text=True, capture_output=True, check=check
    )


def git_output(repo_root: Path, *args: str) -> str:
    return run_git(repo_root, *args).stdout.strip()


def worktree_roots(repo_root: Path) -> list[Path]:
    output = git_output(repo_root, "worktree", "list", "--porcelain")
    return [Path(line[9:]).resolve() for line in output.splitlines() if line.startswith("worktree ")]


def path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def require_external_path(path: Path, repo_root: Path, label: str) -> Path:
    resolved = path.resolve()
    if any(path_is_within(resolved, root) for root in worktree_roots(repo_root)):
        raise GateError(f"{label} must be outside every Git worktree: {resolved}")
    return resolved


def validate_manifest() -> dict:
    ids = [step.step_id for step in RUN_ALL_STEPS]
    if len(ids) != len(set(ids)):
        raise GateError("run-all manifest contains duplicate step IDs")
    if PREPUSH_STEP.step_id in set(ids):
        raise GateError("AC21 prepush step leaked into run-all manifest")

    coverage: dict[str, list[str]] = {}
    for step in RUN_ALL_STEPS:
        for ac in step.acs:
            coverage.setdefault(ac, []).append(step.step_id)
        if not step.commands and step.receipt_kind is None:
            raise GateError(f"step has no executable command or receipt validator: {step.step_id}")
    if set(coverage) != AC01_TO_AC20:
        raise GateError(f"AC01-AC20 coverage mismatch: {sorted(set(coverage) ^ AC01_TO_AC20)}")
    duplicates = {ac: owners for ac, owners in coverage.items() if len(owners) != 1}
    if duplicates:
        raise GateError(f"AC covered by multiple steps: {duplicates}")
    if PREPUSH_STEP.acs != ("AC21",):
        raise GateError("prepush manifest must cover AC21 exactly")
    return {"step_ids": ids, "ac_coverage": coverage, "prepush_step": PREPUSH_STEP.step_id}


def validate_repo_sha(repo_root: Path, expected_sha: str, *, require_clean: bool) -> dict:
    actual = git_output(repo_root, "rev-parse", "HEAD")
    if actual != expected_sha:
        raise GateError(f"HEAD {actual} does not match --sha {expected_sha}")
    status = run_git(repo_root, "status", "--porcelain=v2", "-z", "--untracked-files=all").stdout
    if require_clean and status:
        raise GateError("release worktree is not clean")
    return {"head": actual, "clean": not bool(status), "status_sha256": sha256_bytes(status.encode())}


def validate_required_env(steps: Sequence[Step], env: dict[str, str]) -> list[str]:
    required = sorted({name for step in steps for name in step.required_env} | COMMON_REQUIRED_ENV)
    missing = [name for name in required if not env.get(name)]
    if missing:
        raise GateError(f"missing required release environment: {', '.join(missing)}")
    false_required = [
        name for name in required
        if name.endswith("_REQUIRED") or name == "LAB_RELEASE_GATE"
        if env.get(name, "").lower() not in {"1", "true", "yes", "on"}
    ]
    if false_required:
        raise GateError(f"required release switches are not true: {', '.join(false_required)}")
    receipt_algorithms = {
        env["LAB_ARTIFACT_RECEIPT_ALGORITHM"],
        env["LAB_ARTIFACT_INGEST_RECEIPT_ALGORITHM"],
        env["LAB_ARTIFACT_SCANNER_RECEIPT_ALGORITHM"],
        env["LAB_ARTIFACT_CLEANUP_RECEIPT_ALGORITHM"],
    }
    if receipt_algorithms != {"EdDSA"}:
        raise GateError("production release requires EdDSA Artifact receipts")
    return required


def validate_markers(repo_root: Path) -> list[str]:
    with (repo_root / "backend/pyproject.toml").open("rb") as source:
        config = tomllib.load(source)
    marker_rows = config.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    registered = {row.split(":", 1)[0].strip() for row in marker_rows}
    missing = REQUIRED_MARKERS - registered
    if missing:
        raise GateError(f"required pytest markers are not registered: {sorted(missing)}")
    return sorted(registered)


def validate_test_paths(repo_root: Path, steps: Sequence[Step]) -> list[str]:
    checked: list[str] = []
    for step in steps:
        for command in step.commands:
            if "pytest" not in command.argv:
                continue
            cwd = repo_root / command.cwd
            paths = [item for item in command.argv if item.endswith(".py") or item.endswith("tests/")]
            if not paths:
                raise GateError(f"pytest step has no explicit collection target: {step.step_id}")
            for relative in paths:
                target = cwd / relative
                if not target.exists():
                    raise GateError(f"required collection target does not exist: {target}")
                checked.append(str(target))
    return checked


async def _postgres_preflight(url: str, run_id: str) -> dict:
    try:
        import asyncpg
    except ImportError as exc:  # pragma: no cover - release environment contract
        raise GateError("asyncpg is required for release preflight") from exc
    connect_url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(connect_url)
    try:
        database = await connection.fetchval("SELECT current_database()")
        disposable = await connection.fetchval("SELECT current_setting('simverse.release_disposable', true)")
        version = await connection.fetchval("SHOW server_version")
    finally:
        await connection.close()
    expected = f"simverse_lab_release_{run_id}"
    if database != expected or disposable != "on":
        raise GateError(
            f"Postgres is not the disposable release database: database={database!r} setting={disposable!r}"
        )
    return {"database": database, "server_version": version, "disposable": True}


async def _redis_preflight(url: str, run_id: str, expected_token: str) -> dict:
    try:
        from redis.asyncio import from_url
    except ImportError as exc:  # pragma: no cover - release environment contract
        raise GateError("redis client is required for release preflight") from exc
    client = from_url(url, decode_responses=True)
    try:
        key = f"lab-release:{run_id}:disposable"
        actual = await client.get(key)
        info = await client.info("server")
    finally:
        await client.aclose()
    if not expected_token or actual != expected_token:
        raise GateError("Redis disposable namespace token mismatch")
    return {"key": key, "server_version": info.get("redis_version"), "disposable": True}


def validate_service_health(env: dict[str, str]) -> dict[str, dict]:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - release environment contract
        raise GateError("httpx is required for service health preflight") from exc

    service_specs = (
        ("lab-runtime", "LAB_RUNTIME_BASE_URL", "LAB_RUNTIME_SERVICE_IMAGE_DIGEST"),
        ("lab-executor", "LAB_EXECUTOR_BASE_URL", "LAB_EXECUTOR_SERVICE_IMAGE_DIGEST"),
        (
            "artifact-ingest",
            "LAB_ARTIFACT_INGEST_BASE_URL",
            "LAB_ARTIFACT_INGEST_IMAGE_DIGEST",
        ),
        (
            "artifact-scanner",
            "LAB_ARTIFACT_SCANNER_BASE_URL",
            "LAB_ARTIFACT_SCANNER_IMAGE_DIGEST",
        ),
        (
            "artifact-cleanup",
            "LAB_ARTIFACT_CLEANUP_BASE_URL",
            "LAB_ARTIFACT_CLEANUP_IMAGE_DIGEST",
        ),
    )
    services: dict[str, dict] = {}
    for service_name, base_url_name, image_digest_name in service_specs:
        base_url = env.get(base_url_name)
        expected_digest = env.get(image_digest_name)
        if not base_url or not expected_digest:
            raise GateError(f"missing {base_url_name} or {image_digest_name}")
        parsed = urlparse(base_url)
        if parsed.scheme != "https":
            raise GateError(
                f"{service_name} endpoint must use HTTPS for release evidence"
            )
        response = httpx.get(base_url.rstrip("/") + "/livez", timeout=10.0)
        if response.status_code != 200:
            raise GateError(f"{service_name} /livez returned {response.status_code}")
        body = response.json()
        if body.get("alive") is not True or body.get("service") != service_name:
            raise GateError(f"{service_name} /livez identity is invalid")
        if (
            service_name.startswith("artifact-")
            and body.get("receipt_algorithm") != "EdDSA"
        ):
            raise GateError(
                f"{service_name} live receipt algorithm is not EdDSA"
            )
        if body.get("image_digest") != expected_digest:
            raise GateError(f"{service_name} image digest does not match live service")
        if body.get("sha") != env.get("LAB_SHA"):
            raise GateError(f"{service_name} service SHA does not match tested SHA")
        ready_response = httpx.get(
            base_url.rstrip("/") + "/readyz", timeout=10.0
        )
        if ready_response.status_code != 200:
            raise GateError(
                f"{service_name} /readyz returned {ready_response.status_code}"
            )
        ready_body = ready_response.json()
        if (
            ready_body.get("ready") is not True
            or ready_body.get("service") != service_name
        ):
            raise GateError(f"{service_name} /readyz identity is invalid")
        services[service_name] = {
            "base_url": base_url,
            "image_digest": expected_digest,
            "service_sha": body.get("sha"),
            "ready": True,
        }
    return services


def _external_json(path_value: str, repo_root: Path, label: str) -> tuple[Path, dict]:
    path = require_external_path(Path(path_value), repo_root, label)
    if not path.is_file():
        raise GateError(f"{label} is missing: {path}")
    return path, json.loads(path.read_text(encoding="utf-8"))


def validate_d0(repo_root: Path, request_path: Path, env: dict[str, str]) -> dict:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request_hash = sha256_bytes(canonical_json(request.get("request")))
    if request_hash != request.get("request_hash"):
        raise GateError("D0 request hash mismatch")
    request_body = request.get("request", {})
    if not request_body.get("approval_eligible") or request_body.get("unresolved_fields"):
        raise GateError("D0 request is not approval-eligible or still has unresolved fields")

    attestation_path, attestation = _external_json(env["LAB_D0_ATTESTATION"], repo_root, "D0 attestation")
    policy_path, policy = _external_json(env["LAB_D0_APPROVER_POLICY"], repo_root, "D0 approver policy")
    topology_path, topology_evidence = _external_json(
        env["LAB_NETWORK_POLICY_EVIDENCE"], repo_root, "network/topology evidence"
    )
    trust_root = require_external_path(Path(env["LAB_D0_TRUST_ROOT"]), repo_root, "D0 trust root")
    if not trust_root.is_file():
        raise GateError("D0 trust root is missing")

    payload = attestation.get("payload", {})
    if payload.get("request_hash") != request_hash:
        raise GateError("D0 attestation request hash mismatch")
    now = datetime.now(UTC)
    issued = datetime.fromisoformat(payload["issued_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
    if issued > now or expires <= now:
        raise GateError("D0 attestation is not currently valid")

    approvers = {entry["id"]: entry for entry in policy.get("approvers", [])}
    approver = approvers.get(payload.get("approver_identity"))
    approved_scope = set(payload.get("approved_scope", []))
    requested_scope = set(request_body.get("approval_scope", []))
    if approver is None or not requested_scope <= approved_scope <= set(approver.get("scopes", [])):
        raise GateError("D0 approver or approved scope is not allowed by protected policy")

    topology_hash = sha256_bytes(canonical_json(topology_evidence.get("topology")))
    network_hash = sha256_bytes(canonical_json(topology_evidence.get("network_policy")))
    if topology_hash != request_body.get("topology_hash") or network_hash != request_body.get("network_policy_hash"):
        raise GateError("D0 topology/network evidence hash mismatch")
    if payload.get("topology_hash") != topology_hash or payload.get("network_policy_hash") != network_hash:
        raise GateError("D0 attestation topology/network hash mismatch")

    requested_digests = {item["name"]: item["image_digest"] for item in request_body.get("services", [])}
    attested_digests = {item["name"]: item["image_digest"] for item in payload.get("services", [])}
    if requested_digests != attested_digests:
        raise GateError("D0 service/image digest scope mismatch")

    signature = base64.b64decode(attestation.get("signature_base64", ""), validate=True)
    if attestation.get("signature_algorithm") != "rsa-sha256":
        raise GateError("unsupported D0 signature algorithm")
    with tempfile.TemporaryDirectory(prefix="lab-d0-") as directory:
        payload_file = Path(directory) / "payload.json"
        signature_file = Path(directory) / "signature.bin"
        payload_file.write_bytes(canonical_json(payload))
        signature_file.write_bytes(signature)
        verified = subprocess.run(
            [
                "openssl", "dgst", "-sha256", "-verify", str(trust_root),
                "-signature", str(signature_file), str(payload_file),
            ],
            text=True,
            capture_output=True,
        )
    if verified.returncode != 0:
        raise GateError("D0 signature verification failed")

    return {
        "request_hash": request_hash,
        "attestation_sha256": sha256_file(attestation_path),
        "trust_root_sha256": sha256_file(trust_root),
        "approver_policy_sha256": sha256_file(policy_path),
        "topology_evidence_sha256": sha256_file(topology_path),
        "approver_identity": payload["approver_identity"],
        "expires_at": payload["expires_at"],
        "services": requested_digests,
    }


def validate_visual_receipt(path_value: str, repo_root: Path, sha: str) -> dict:
    path, receipt = _external_json(path_value, repo_root, "AC19 visual receipt")
    if receipt.get("sha") != sha:
        raise GateError("visual receipt SHA mismatch")
    states = receipt.get("states", [])
    if len(states) != 15:
        raise GateError(f"visual receipt must contain exactly 15 states, got {len(states)}")
    for state in states:
        if (
            state.get("verdict") != "pass"
            or state.get("score", 0) < 90
            or state.get("category_match") is not True
            or state.get("overlap_count") != 0
            or state.get("overflow_count") != 0
            or state.get("min_touch_target_px", 0) < 44
        ):
            raise GateError(f"visual state failed: {state.get('id')}")
    if receipt.get("console_errors") or receipt.get("network_errors"):
        raise GateError("visual receipt contains console or network errors")
    return {"receipt_sha256": sha256_file(path), "state_count": len(states), "minimum_score": min(s["score"] for s in states)}


def environment_fingerprint(env: dict[str, str], names: Iterable[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name in sorted(set(names)):
        value = env.get(name, "")
        if any(fragment in name for fragment in SENSITIVE_ENV_FRAGMENTS):
            result[name] = {"present": bool(value), "sha256": sha256_bytes(value.encode()) if value else None}
        else:
            result[name] = value
    return result


def command_receipt(command: Command, completed: subprocess.CompletedProcess[str], elapsed_s: float, log_path: Path) -> dict:
    return {
        "cwd": command.cwd,
        "argv": list(command.argv),
        "exit_code": completed.returncode,
        "elapsed_s": round(elapsed_s, 3),
        "log": str(log_path),
        "log_sha256": sha256_file(log_path),
    }


def execute_step(step: Step, repo_root: Path, run_dir: Path, env: dict[str, str], sha: str, d0_request: Path) -> dict:
    started = time.monotonic()
    if step.receipt_kind == "visual":
        detail = validate_visual_receipt(env["LAB_VISUAL_RECEIPT"], repo_root, sha)
        return {"step_id": step.step_id, "acs": step.acs, "status": "passed", "detail": detail}
    if step.receipt_kind == "d0":
        detail = validate_d0(repo_root, d0_request, env)
        return {"step_id": step.step_id, "acs": step.acs, "status": "passed", "detail": detail}

    command_results: list[dict] = []
    safe_id = step.step_id.replace(":", "-")
    for index, command in enumerate(step.commands, start=1):
        cwd = (repo_root / command.cwd).resolve()
        if not path_is_within(cwd, repo_root) or not cwd.is_dir():
            raise GateError(f"invalid command cwd for {step.step_id}: {cwd}")
        log_path = run_dir / "logs" / f"{safe_id}-{index}.log"
        command_started = time.monotonic()
        try:
            completed = subprocess.run(
                list(command.argv),
                cwd=cwd,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=step.timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            log_path.write_text((exc.stdout or "") + "\nTIMEOUT\n", encoding="utf-8")
            raise GateError(f"step timed out: {step.step_id}") from exc
        log_path.write_text(completed.stdout, encoding="utf-8")
        receipt = command_receipt(command, completed, time.monotonic() - command_started, log_path)
        command_results.append(receipt)
        if completed.returncode != 0:
            raise GateError(f"step failed: {step.step_id} command {index} exit={completed.returncode}")
        if "pytest" in command.argv and ("collected 0 items" in completed.stdout or "no tests ran" in completed.stdout):
            raise GateError(f"required pytest collection was empty: {step.step_id}")
    return {
        "step_id": step.step_id,
        "acs": step.acs,
        "status": "passed",
        "elapsed_s": round(time.monotonic() - started, 3),
        "commands": command_results,
    }


def write_json(path: Path, value: object, *, exclusive: bool = True) -> None:
    mode = "x" if exclusive else "w"
    with path.open(mode, encoding="utf-8") as target:
        json.dump(value, target, indent=2, sort_keys=True)
        target.write("\n")


def make_run_dir(evidence_root: Path, sha: str, command: str, run_id: str) -> Path:
    if command == "verify":
        run_dir = evidence_root / "provisional" / sha / run_id
    else:
        run_dir = evidence_root / sha / f"test-sub-bundle.pending-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "logs").mkdir()
    (run_dir / "receipts").mkdir()
    return run_dir


def chmod_tree_read_only(path: Path) -> None:
    for child in sorted(path.rglob("*"), reverse=True):
        child.chmod(0o555 if child.is_dir() else 0o444)
    path.chmod(0o555)


def preflight(repo_root: Path, evidence_root: Path, sha: str, env: dict[str, str], d0_request: Path) -> dict:
    manifest = validate_manifest()
    git_state = validate_repo_sha(repo_root, sha, require_clean=True)
    required_env = validate_required_env(RUN_ALL_STEPS, env)
    markers = validate_markers(repo_root)
    test_paths = validate_test_paths(repo_root, RUN_ALL_STEPS)
    run_id = env["LAB_RELEASE_RUN_ID"]
    postgres = asyncio.run(_postgres_preflight(env["LAB_TEST_DATABASE_URL"], run_id))
    redis = asyncio.run(_redis_preflight(env["LAB_TEST_REDIS_URL"], run_id, env.get("LAB_REDIS_DISPOSABLE_TOKEN", "")))
    services = validate_service_health(env)
    d0 = validate_d0(repo_root, d0_request, env)
    live_digests = {
        name: service["image_digest"] for name, service in services.items()
    }
    if live_digests != d0["services"]:
        raise GateError("live service image digests do not match the D0 request")
    return {
        "at": utc_now(),
        "manifest": manifest,
        "git": git_state,
        "evidence_root": str(evidence_root),
        "required_env": environment_fingerprint(env, required_env),
        "markers": markers,
        "collection_targets": test_paths,
        "postgres": postgres,
        "redis": redis,
        "services": services,
        "d0": d0,
        "resource_fingerprint": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "machine": platform.machine(),
            "postgres_url_sha256": sha256_bytes(env["LAB_TEST_DATABASE_URL"].encode()),
            "redis_url_sha256": sha256_bytes(env["LAB_TEST_REDIS_URL"].encode()),
            "service_image_digests": live_digests,
        },
    }


def run_verification(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    evidence_root = require_external_path(args.evidence_root, repo_root, "release evidence root")
    env = dict(os.environ)
    env["LAB_SHA"] = args.sha
    if args.command == "verify" and not args.no_seal:
        raise GateError("verify requires --no-seal")
    if args.command == "run-all" and not args.seal_tests:
        raise GateError("run-all requires --seal-tests")
    run_id = env.get("LAB_RELEASE_RUN_ID", "")
    if not run_id:
        raise GateError("LAB_RELEASE_RUN_ID is required")
    run_dir = make_run_dir(evidence_root, args.sha, args.command, run_id)
    try:
        preflight_receipt = preflight(repo_root, evidence_root, args.sha, env, args.d0_request)
        write_json(run_dir / "preflight.json", preflight_receipt)
        receipts: list[dict] = []
        for step in RUN_ALL_STEPS:
            receipt = execute_step(step, repo_root, run_dir, env, args.sha, args.d0_request)
            write_json(run_dir / "receipts" / f"{step.step_id.replace(':', '-')}.json", receipt)
            receipts.append(receipt)
        index = {
            "schema_version": 1,
            "kind": "provisional-verification" if args.command == "verify" else "sealed-test-sub-bundle",
            "sha": args.sha,
            "created_at": utc_now(),
            "run_id": run_id,
            "step_ids": [receipt["step_id"] for receipt in receipts],
            "ac_coverage": validate_manifest()["ac_coverage"],
            "preflight_sha256": sha256_file(run_dir / "preflight.json"),
            "receipt_sha256": {
                path.name: sha256_file(path) for path in sorted((run_dir / "receipts").glob("*.json"))
            },
        }
        write_json(run_dir / "index.json", index)
        if args.command == "run-all":
            final_dir = evidence_root / args.sha / "test-sub-bundle"
            if final_dir.exists():
                raise GateError(f"sealed test sub-bundle already exists: {final_dir}")
            write_json(run_dir / "SEALED.json", {"sha": args.sha, "index_sha256": sha256_file(run_dir / "index.json")})
            run_dir.rename(final_dir)
            chmod_tree_read_only(final_dir)
            print(json.dumps({"ok": True, "bundle": str(final_dir), "sha": args.sha}, sort_keys=True))
        else:
            print(json.dumps({"ok": True, "provisional": str(run_dir), "sha": args.sha}, sort_keys=True))
        return 0
    except Exception as exc:
        try:
            write_json(run_dir / "FAILED.json", {"at": utc_now(), "error": str(exc)}, exclusive=False)
        except Exception:
            pass
        raise


def validate_sealed_test_bundle(evidence_root: Path, sha: str) -> dict:
    bundle = evidence_root / sha / "test-sub-bundle"
    seal_path = bundle / "SEALED.json"
    index_path = bundle / "index.json"
    if not seal_path.is_file() or not index_path.is_file():
        raise GateError("sealed AC01-AC20 test sub-bundle is missing")
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if seal.get("sha") != sha or index.get("sha") != sha:
        raise GateError("sealed test sub-bundle SHA mismatch")
    if seal.get("index_sha256") != sha256_file(index_path):
        raise GateError("sealed test sub-bundle index digest mismatch")
    if bundle.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        raise GateError("sealed test sub-bundle is writable")
    return {"path": str(bundle), "index_sha256": sha256_file(index_path), "seal_sha256": sha256_file(seal_path)}


def validate_remote(repo_root: Path, remote: str, branch: str, sha: str) -> dict:
    if branch != "master":
        raise GateError("authorized release branch is master")
    run_git(repo_root, "fetch", remote, "--prune")
    remote_head = git_output(repo_root, "symbolic-ref", f"refs/remotes/{remote}/HEAD")
    if remote_head != f"refs/remotes/{remote}/master":
        raise GateError(f"remote default branch changed: {remote_head}")
    main = run_git(repo_root, "ls-remote", "--heads", remote, "refs/heads/main").stdout.strip()
    if main:
        raise GateError("a real remote main branch now exists; governance decision required")
    latest = git_output(repo_root, "rev-parse", f"{remote}/{branch}")
    ancestor = run_git(repo_root, "merge-base", "--is-ancestor", latest, sha, check=False).returncode == 0
    if not ancestor:
        raise GateError(f"latest {remote}/{branch} is not an ancestor of tested SHA")
    return {"remote_head": remote_head, "latest": latest, "latest_is_ancestor": True, "main_absent": True}


def is_secret_env_path(path: str) -> bool:
    """Examples are release inputs; concrete dotenv files are credentials."""
    name = Path(path).name
    return name != ".env.example" and (name == ".env" or name.startswith(".env."))


def validate_scoped_diff(repo_root: Path, remote: str, branch: str, dirty_manifest: Path) -> dict:
    paths = [line for line in git_output(repo_root, "diff", "--name-only", f"{remote}/{branch}...HEAD").splitlines() if line]
    baseline = json.loads(dirty_manifest.read_text(encoding="utf-8"))
    protected = {entry["path"] for entry in baseline.get("paths", [])}
    forbidden = [
        path for path in paths
        if path in protected
        or path.endswith((".db", ".sqlite3"))
        or is_secret_env_path(path)
        or path.startswith("output/")
        or path.startswith("target-")
    ]
    if forbidden:
        raise GateError(f"release diff contains protected/user/generated paths: {forbidden}")
    return {"path_count": len(paths), "paths": paths, "forbidden": []}


def verify_dirty_manifest(
    repo_root: Path,
    dirty_manifest: Path,
    *,
    expected_sha256: str = APPROVED_DIRTY_MANIFEST_SHA256,
) -> dict:
    dirty_manifest = require_external_path(dirty_manifest, repo_root, "original dirty manifest")
    if sha256_file(dirty_manifest) != expected_sha256:
        raise GateError("original dirty manifest digest does not match the approved baseline")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from snapshot_dirty_worktree import verify

    manifest = json.loads(dirty_manifest.read_text(encoding="utf-8"))
    raw_status = manifest.get("raw_status_file")
    if not raw_status:
        raise GateError("original dirty manifest has no raw status evidence")
    require_external_path(Path(raw_status), repo_root, "original raw dirty status")
    result = verify(Path(manifest["repo_root"]), dirty_manifest)
    if not result["ok"]:
        raise GateError(f"original dirty worktree changed: {result['errors']}")
    return result


def run_prepush(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    evidence_root = require_external_path(args.evidence_root, repo_root, "release evidence root")
    env = dict(os.environ)
    validate_repo_sha(repo_root, args.sha, require_clean=True)
    bundle = validate_sealed_test_bundle(evidence_root, args.sha)
    remote = validate_remote(repo_root, args.remote, args.branch, args.sha)
    dirty = verify_dirty_manifest(repo_root, args.dirty_manifest)
    diff = validate_scoped_diff(repo_root, args.remote, args.branch, args.dirty_manifest)
    d0 = validate_d0(repo_root, args.d0_request, {
        **env,
        "LAB_D0_ATTESTATION": str(args.d0_attestation),
        "LAB_D0_TRUST_ROOT": str(args.d0_trust_root),
        "LAB_D0_APPROVER_POLICY": str(args.d0_approver_policy),
        "LAB_NETWORK_POLICY_EVIDENCE": str(args.topology_evidence),
    })
    dry_run = run_git(repo_root, "push", "--dry-run", args.remote, f"HEAD:{args.branch}", check=False)
    if dry_run.returncode != 0:
        raise GateError(f"non-force push dry-run failed: {dry_run.stderr.strip()}")
    receipt = {
        "schema_version": 1,
        "step_id": PREPUSH_STEP.step_id,
        "ac": "AC21",
        "sha": args.sha,
        "created_at": utc_now(),
        "sealed_test_bundle": bundle,
        "remote": remote,
        "dirty_manifest": dirty,
        "diff": diff,
        "d0": d0,
        "push_dry_run": {"command": ["git", "push", "--dry-run", args.remote, f"HEAD:{args.branch}"], "ok": True},
    }
    receipt_path = evidence_root / args.sha / "ac21-prepush.json"
    write_json(receipt_path, receipt)
    receipt_path.chmod(0o444)
    print(json.dumps({"ok": True, "receipt": str(receipt_path), "sha": args.sha}, sort_keys=True))
    return 0


def validate_immutable_parent(evidence_root: Path, sha: str) -> dict:
    parent_path = evidence_root / sha / "release-parent.json"
    if not parent_path.is_file():
        raise GateError("protected immutable release parent is missing")
    if parent_path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        raise GateError("release parent is writable")
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    if parent.get("sha") != sha:
        raise GateError("release parent SHA mismatch")
    required_reviews = {"architect", "security-reviewer", "code-reviewer", "verifier"}
    reviews = {item.get("role"): item for item in parent.get("reviews", [])}
    if set(reviews) != required_reviews or any(item.get("verdict") != "APPROVE" for item in reviews.values()):
        raise GateError("release parent does not contain four independent APPROVE verdicts")
    test_bundle = validate_sealed_test_bundle(evidence_root, sha)
    prepush = evidence_root / sha / "ac21-prepush.json"
    if not prepush.is_file():
        raise GateError("AC21 prepush receipt is missing")
    expected = parent.get("digests", {})
    if expected.get("test_index_sha256") != test_bundle["index_sha256"] or expected.get("prepush_sha256") != sha256_file(prepush):
        raise GateError("release parent child digests do not match")
    return {"path": str(parent_path), "sha256": sha256_file(parent_path), "reviews": sorted(reviews)}


def validate_release_check_receipt(evidence_root: Path, sha: str) -> dict:
    path = evidence_root / sha / "release-check.json"
    if not path.is_file():
        raise GateError("release-check receipt is missing")
    if path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        raise GateError("release-check receipt is writable")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("ok") is not True or receipt.get("sha") != sha:
        raise GateError("release-check receipt does not approve this SHA")
    return {"path": str(path), "sha256": sha256_file(path), "checked_at": receipt.get("checked_at")}


def run_release_check(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    evidence_root = require_external_path(args.evidence_root, repo_root, "release evidence root")
    validate_repo_sha(repo_root, args.sha, require_clean=True)
    remote = validate_remote(repo_root, args.remote, args.branch, args.sha)
    d0 = validate_d0(repo_root, args.d0_request, {
        **os.environ,
        "LAB_D0_ATTESTATION": str(args.d0_attestation),
        "LAB_D0_TRUST_ROOT": str(args.d0_trust_root),
        "LAB_D0_APPROVER_POLICY": str(args.d0_approver_policy),
        "LAB_NETWORK_POLICY_EVIDENCE": str(args.topology_evidence),
    })
    parent = validate_immutable_parent(evidence_root, args.sha)
    receipt = {"ok": True, "sha": args.sha, "checked_at": utc_now(), "remote": remote, "d0": d0, "parent": parent}
    path = evidence_root / args.sha / "release-check.json"
    write_json(path, receipt)
    path.chmod(0o444)
    print(json.dumps({"ok": True, "receipt": str(path), "sha": args.sha}, sort_keys=True))
    return 0


def run_record_postcondition(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    evidence_root = require_external_path(args.evidence_root, repo_root, "release evidence root")
    head = git_output(repo_root, "rev-parse", "HEAD")
    remote_sha = git_output(repo_root, "rev-parse", args.remote_ref)
    parent = validate_immutable_parent(evidence_root, args.sha)
    release_check = validate_release_check_receipt(evidence_root, args.sha)
    if head != args.sha or remote_sha != args.sha:
        raise GateError(f"release postcondition mismatch: HEAD={head} {args.remote_ref}={remote_sha}")
    receipt = {
        "ok": True,
        "sha": args.sha,
        "recorded_at": utc_now(),
        "head": head,
        "remote_ref": args.remote_ref,
        "remote_sha": remote_sha,
        "immutable_parent": parent,
        "release_check": release_check,
    }
    path = evidence_root / args.sha / "release-postcondition.json"
    write_json(path, receipt)
    path.chmod(0o444)
    print(json.dumps({"ok": True, "receipt": str(path), "sha": args.sha}, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    subparsers = result.add_subparsers(dest="command", required=True)

    for name in ("verify", "run-all"):
        command = subparsers.add_parser(name)
        command.add_argument("--repo-root", type=Path, required=True)
        command.add_argument("--sha", required=True)
        command.add_argument("--evidence-root", type=Path, required=True)
        command.add_argument(
            "--d0-request", type=Path,
            default=Path(__file__).resolve().parents[2] / ".omx/approvals/lab-agent-services-d0.json",
        )
        command.add_argument("--no-seal", action="store_true")
        command.add_argument("--seal-tests", action="store_true")

    prepush = subparsers.add_parser("prepush")
    prepush.add_argument("--repo-root", type=Path, required=True)
    prepush.add_argument("--sha", required=True)
    prepush.add_argument("--remote", required=True)
    prepush.add_argument("--branch", required=True)
    prepush.add_argument("--dirty-manifest", type=Path, required=True)
    prepush.add_argument("--evidence-root", type=Path, required=True)
    prepush.add_argument("--d0-request", type=Path, required=True)
    prepush.add_argument("--d0-attestation", type=Path, required=True)
    prepush.add_argument("--d0-trust-root", type=Path, required=True)
    prepush.add_argument("--d0-approver-policy", type=Path, required=True)
    prepush.add_argument("--topology-evidence", type=Path, required=True)

    release = subparsers.add_parser("release-check")
    release.add_argument("--repo-root", type=Path, required=True)
    release.add_argument("--sha", required=True)
    release.add_argument("--remote", required=True)
    release.add_argument("--branch", required=True)
    release.add_argument("--evidence-root", type=Path, required=True)
    release.add_argument("--require-immutable-parent", action="store_true", required=True)
    release.add_argument("--d0-request", type=Path, required=True)
    release.add_argument("--d0-attestation", type=Path, required=True)
    release.add_argument("--d0-trust-root", type=Path, required=True)
    release.add_argument("--d0-approver-policy", type=Path, required=True)
    release.add_argument("--topology-evidence", type=Path, required=True)

    post = subparsers.add_parser("record-postcondition")
    post.add_argument("--repo-root", type=Path, required=True)
    post.add_argument("--sha", required=True)
    post.add_argument("--remote-ref", required=True)
    post.add_argument("--evidence-root", type=Path, required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command in {"verify", "run-all"}:
            return run_verification(args)
        if args.command == "prepush":
            return run_prepush(args)
        if args.command == "release-check":
            return run_release_check(args)
        if args.command == "record-postcondition":
            return run_record_postcondition(args)
        raise GateError(f"unsupported command: {args.command}")
    except (GateError, KeyError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "command": args.command, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
