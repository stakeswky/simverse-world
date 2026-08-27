#!/usr/bin/env python3
"""Inventory Lab terminal writers and the D1a A'/B feasibility inputs.

This is deliberately a source audit, not an authorization mechanism. Database
roles and release probes remain the enforcement oracle. The allowlist makes a
new terminal call/write site fail closed until it is reviewed and classified.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


TERMINAL_STATUSES = {
    "completed",
    "failed",
    "expired",
    "cancelled",
    "settled",
    "refunded",
    "succeeded",
}
TERMINAL_CALLS = {
    "reward",
    "treasury_credit",
    "settle",
    "refund",
    "settle_pending",
    "refund_pending",
    "submit_command",
    "submit_for_caller",
    "finalize",
    "finalize_legacy",
    "fail_task",
    "_settle_and_complete",
    "cancel_task",
    "expire_lab_tasks",
    "cas_task_status",
}

AUDITED_PATHS = (
    "backend/app/lab",
    "backend/app/services/lab_task_service.py",
    "backend/app/services/lab_terminalization_service.py",
    "backend/app/services/coin_service.py",
    "backend/app/routers/lab.py",
    "backend/app/routers/admin/lab.py",
    "backend/app/tasks/nightly_cron.py",
)


@dataclass(frozen=True, order=True)
class Finding:
    kind: str
    path: str
    symbol: str
    operation: str
    value: str = ""


EXPECTED_FINDINGS = {
    Finding(
        "write", "backend/app/lab/broker.py", "request_action._build",
        "LabToolAction.status", "<dynamic>",
    ),
    Finding("write", "backend/app/lab/broker.py", "execute_action", "action.status", "failed"),
    Finding("write", "backend/app/lab/broker.py", "execute_action", "action.status", "succeeded"),
    Finding("write", "backend/app/lab/orchestrator.py", "_fail", "self.run.status", "failed"),
    Finding("call", "backend/app/lab/orchestrator.py", "_fail", "fail_task"),
    Finding("write", "backend/app/lab/orchestrator.py", "_succeed", "self.run.status", "succeeded"),
    Finding(
        "write", "backend/app/lab/orchestrator.py", "_handle_delegation",
        "finish_worker.status", "<dynamic>",
    ),
    Finding("write", "backend/app/lab/orchestrator.py", "run_one_v1", "run.status", "failed"),
    Finding("write", "backend/app/lab/runner.py", "run_one", "run.status", "failed"),
    Finding("call", "backend/app/lab/runner.py", "run_one", "fail_task"),
    Finding(
        "write", "backend/app/lab/terminalizer.py", "_record_failure",
        "command.status", "failed",
    ),
    Finding(
        "call", "backend/app/lab/terminalizer.py", "process_pending_commands",
        "finalize",
    ),
    Finding(
        "call", "backend/app/lab/terminalizer.py", "process_pending_commands",
        "finalize_legacy",
    ),
    Finding("call", "backend/app/lab/supervision.py", "kill_switch_all", "fail_task"),
    Finding("write", "backend/app/lab/supervision.py", "_fence_run_once", "run.status", "cancelled"),
    Finding(
        "write", "backend/app/lab/transitions.py", "cas_proposal_status",
        "values.status", "<dynamic>",
    ),
    Finding(
        "write", "backend/app/lab/workers.py", "execute_worker_on_mock",
        "WorkerResult.status", "<dynamic>",
    ),
    Finding(
        "write", "backend/app/lab/workers.py", "execute_worker_on_mock",
        "WorkerResult.status", "failed",
    ),
    Finding(
        "write", "backend/app/lab/workers.py", "finish_worker",
        "attempt.status", "<dynamic>",
    ),
    Finding("call", "backend/app/routers/admin/lab.py", "cancel_run", "fail_task"),
    Finding("write", "backend/app/routers/admin/lab.py", "cancel_run", "run.status", "cancelled"),
    Finding("call", "backend/app/routers/lab.py", "cancel_task", "cancel_task"),
    Finding("call", "backend/app/services/coin_service.py", "refund", "refund_pending"),
    Finding("call", "backend/app/services/coin_service.py", "settle", "settle_pending"),
    Finding(
        "write", "backend/app/services/coin_service.py", "refund_pending",
        "values.status", "refunded",
    ),
    Finding(
        "write", "backend/app/services/coin_service.py", "settle_pending",
        "values.status", "settled",
    ),
    Finding(
        "call", "backend/app/services/lab_task_service.py", "_settle_and_complete",
        "submit_for_caller",
    ),
    Finding(
        "call", "backend/app/services/lab_task_service.py", "accept_result",
        "submit_for_caller",
    ),
    Finding(
        "call", "backend/app/services/lab_task_service.py", "cancel_task",
        "submit_for_caller",
    ),
    Finding(
        "call", "backend/app/services/lab_task_service.py", "arbitrate_result",
        "submit_for_caller",
    ),
    Finding("call", "backend/app/services/lab_task_service.py", "expire_lab_tasks", "_settle_and_complete"),
    Finding(
        "call", "backend/app/services/lab_task_service.py", "expire_lab_tasks",
        "submit_for_caller",
    ),
    Finding(
        "call", "backend/app/services/lab_task_service.py", "fail_task",
        "submit_for_caller",
    ),
    Finding("call", "backend/app/services/lab_task_service.py", "mark_review", "cas_task_status"),
    Finding(
        "call", "backend/app/services/lab_terminalization_service.py",
        "_finalize_orm_attempt", "refund_pending",
    ),
    Finding(
        "call", "backend/app/services/lab_terminalization_service.py",
        "_finalize_orm_attempt", "settle_pending",
    ),
    Finding(
        "call", "backend/app/services/lab_terminalization_service.py",
        "submit_for_caller", "finalize_legacy",
    ),
    Finding(
        "call", "backend/app/services/lab_terminalization_service.py",
        "submit_for_caller", "submit_command",
    ),
    Finding(
        "write", "backend/app/services/lab_terminalization_service.py",
        "_finalize_orm_attempt", "command.status", "completed",
    ),
    Finding(
        "write", "backend/app/services/lab_terminalization_service.py",
        "_finalize_orm_attempt", "values.status", "<dynamic>",
    ),
    Finding(
        "write", "backend/app/services/lab_terminalization_service.py",
        "_prepare_task_runs", "run.status", "cancelled",
    ),
    Finding("call", "backend/app/tasks/nightly_cron.py", "run_nightly_jobs", "expire_lab_tasks"),
    Finding("call", "backend/app/tasks/nightly_cron.py", "sweep_orphan_lab_runs", "fail_task"),
    Finding("write", "backend/app/tasks/nightly_cron.py", "sweep_orphan_lab_runs", "run.status", "failed"),
    Finding(
        "call", "backend/app/lab/artifact_pipeline.py", "reconcile_once", "fail_task"
    ),
    Finding("call", "backend/app/lab/runner.py", "run_one", "cas_task_status"),
    Finding(
        "call", "backend/app/services/coin_service.py", "reward_creator_passive",
        "reward",
    ),
    Finding(
        "write", "backend/app/lab/artifact_pipeline.py", "reconcile_once",
        "run.status", "failed",
    ),
    Finding(
        "write", "backend/app/lab/artifact_services/cleanup/service.py", "delete",
        "_receipt.status", "completed",
    ),
    Finding(
        "write", "backend/app/lab/artifact_services/cleanup/service.py", "delete",
        "_receipt.status", "failed",
    ),
    Finding(
        "write", "backend/app/lab/artifact_services/scanner/service.py", "_finish",
        "_receipt.status", "<dynamic>",
    ),
    Finding(
        "write", "backend/app/lab/artifact_services/scanner/service.py",
        "_retry_or_fail", "_finish.status", "failed",
    ),
    Finding(
        "write", "backend/app/lab/artifact_services/scanner/service.py", "process",
        "_finish.status", "failed",
    ),
    Finding(
        "write", "backend/app/lab/broker.py", "settle_reconciled_action",
        "action.status", "<dynamic>",
    ),
    Finding(
        "write", "backend/app/lab/control_plane.py", "_complete_request",
        "request.status", "completed",
    ),
    Finding(
        "write", "backend/app/lab/control_plane.py", "_complete_request",
        "run.status", "cancelled",
    ),
    Finding(
        "write", "backend/app/lab/control_plane.py", "_settle_target",
        "session.status", "cancelled",
    ),
    Finding(
        "write", "backend/app/lab/control_plane.py", "process_global_kill",
        "kill.status", "completed",
    ),
    Finding(
        "write", "backend/app/lab/control_plane.py", "reconcile_v2_processing",
        "claim.status", "completed",
    ),
    Finding(
        "write", "backend/app/lab/control_plane.py", "reconcile_v2_processing",
        "claim.status", "expired",
    ),
    Finding(
        "write", "backend/app/lab/control_plane.py", "settle_queue_claim",
        "values.status", "<dynamic>",
    ),
    Finding(
        "write", "backend/app/lab/executor_service/server.py", "_complete_result",
        "sign.status", "<dynamic>",
    ),
    Finding(
        "write", "backend/app/lab/orchestrator.py", "_commit_v2_success",
        "run.status", "succeeded",
    ),
    Finding(
        "write", "backend/app/lab/orchestrator.py", "run_one_v2",
        "run.status", "failed",
    ),
    Finding(
        "write", "backend/app/lab/remote_executor.py", "get_result",
        "verify.status", "<dynamic>",
    ),
    Finding(
        "write", "backend/app/lab/supervision.py", "_commit_runtime_event",
        "session.status", "cancelled",
    ),
    Finding(
        "write", "backend/app/lab/supervision.py", "_commit_runtime_event",
        "session.status", "completed",
    ),
    Finding(
        "write", "backend/app/lab/supervision.py", "_commit_runtime_event",
        "session.status", "failed",
    ),
    Finding(
        "write", "backend/app/lab/supervision.py", "_commit_runtime_event",
        "turn.status", "completed",
    ),
}

CURRENT_RUNTIME_CALLERS = (
    {
        "process": "api",
        "mount": "app.main when RUN_BACKGROUND_TASKS=true plus player/admin routes",
        "operations": ["accept", "cancel", "admin_cancel", "auto_release", "expire", "orphan_fail"],
    },
    {
        "process": "agent-worker",
        "mount": "app.agent.main nightly_cron_loop",
        "operations": ["auto_release", "expire", "orphan_fail"],
    },
    {
        "process": "lab-runner",
        "mount": "app.lab.main RunnerService",
        "operations": [
            "run_success",
            "run_failure",
            "kill_switch",
            "terminal_command_consumer",
            "terminal_event_publisher",
        ],
    },
)

PLANNED_DB_ROLES = (
    {
        "role": "lab_financial_kernel_owner",
        "login": False,
        "mount": "none",
        "capability": "own controlled entrypoint and required kernel objects",
    },
    {
        "role": "lab_command_submitter_v2",
        "login": False,
        "mount": "API role membership after D0/D1b only",
        "capability": "EXECUTE submit_lab_terminalization_command(operation, task, actor, epoch)",
    },
    {
        "role": "lab_terminalizer_v2",
        "login": True,
        "mount": "Lab Runner terminalization component only",
        "capability": "EXECUTE finalize_lab_terminalization(command_id, expected_epoch)",
    },
    {
        "role": "lab_terminalizer_breakglass",
        "login": False,
        "mount": "none by default",
        "capability": "externally approved audited compensation entrypoint only",
    },
)

A_PRIME = {
    "files": [
        "backend/app/config.py",
        "backend/app/lab/apply.py",
        "backend/app/lab/broker.py",
        "backend/app/lab/main.py",
        "backend/app/lab/orchestrator.py",
        "backend/app/lab/outbox_dispatcher.py",
        "backend/app/lab/protocol.py",
        "backend/app/lab/queue.py",
        "backend/app/lab/runtime_ref/agent.py",
        "backend/app/lab/runtime_ref/server.py",
        "backend/app/lab/sandbox/base.py",
        "backend/app/lab/service_auth.py",
        "backend/app/lab/supervision.py",
        "backend/app/models/coin_hold.py",
        "backend/app/models/coin_hold_entry.py",
        "backend/app/models/lab_control.py",
        "backend/app/models/lab_run.py",
        "backend/app/models/lab_runtime.py",
        "backend/app/models/lab_terminalization.py",
        "backend/app/services/coin_service.py",
        "backend/app/services/lab_task_service.py",
        "backend/app/services/lab_terminalization_service.py",
        "backend/app/services/proposal_service.py",
        "backend/app/services/world_revision_service.py",
        "backend/app/tasks/nightly_cron.py",
        "backend/alembic/versions/038_add_lab_agent_v2.py",
        "backend/scripts/audit_lab_terminal_writers.py",
        "backend/scripts/run_lab_release_gate.py",
    ],
    "symbols": [
        "LabTerminalizationService.submit",
        "LabTerminalizationService.finalize",
        "finalize_lab_terminalization",
        "validate_distribution",
        "generate_cohort_matrix",
        "reconcile_lab_finances",
        "LabRuntimeSession",
        "LabRuntimeTurn",
        "LabRuntimeIntent",
        "LabRuntimeResult",
        "LabRunControlRequest",
        "LabToolExecution",
        "LabGlobalKill",
        "LabGlobalKillTarget",
        "RuntimeEventV2",
        "ToolResultCommandV2",
        "ControlCommandV2",
        "ServiceTokenIssuer",
        "ServiceTokenVerifier",
        "RuntimeReceiptStore",
        "create_or_reattach_session",
        "ingest_runtime_events",
        "deliver_tool_result",
        "process_control_requests",
        "request_global_kill",
        "reconcile_global_kill",
        "dispatch_owned_topics",
        "apply_world_change",
        "revert_world_change",
    ],
    "tables": [
        "coin_hold_entries",
        "lab_terminalization_commands",
        "lab_breakglass_audits",
        "lab_compensation_entries",
        "lab_runtime_sessions",
        "lab_runtime_turns",
        "lab_runtime_intents",
        "lab_runtime_results",
        "lab_run_control_requests",
        "lab_tool_executions",
        "lab_global_kills",
        "lab_global_kill_targets",
    ],
    "backfills": [
        "historical LabRun rows to immutable protocol_version=v1",
        "eligible nonterminal CoinHold rows to terminalization_version=v2 with watermark",
        "1120-tuple cohort classification and actual-row mapping without synthetic journal history",
    ],
    "services": ["lab-runtime", "lab-executor", "artifact-cleanup"],
    "financial_domains": 1,
}

OPTION_B = {
    **A_PRIME,
    "files": A_PRIME["files"] + [
        "backend/app/models/lab_v2_task.py",
        "backend/app/models/lab_v2_hold.py",
        "backend/app/models/lab_v2_ledger.py",
        "backend/app/models/lab_v2_treasury.py",
        "backend/app/models/lab_v2_artifact.py",
        "backend/app/models/lab_v2_action.py",
        "backend/app/services/lab_v2_task_service.py",
        "backend/app/services/lab_v2_coin_service.py",
        "backend/app/services/lab_v2_broker.py",
        "backend/app/services/lab_v2_reconciliation_bridge.py",
    ],
    "symbols": A_PRIME["symbols"] + [
        "LabV2TaskService",
        "LabV2CoinService",
        "LabV2LedgerService",
        "LabV2TreasuryService",
        "LabV2ArtifactService",
        "LabV2Broker",
        "LabV1V2ReconciliationBridge",
        "migrate_v1_tasks",
        "migrate_v1_holds",
        "migrate_v1_ledger",
    ],
    "tables": A_PRIME["tables"] + [
        "lab_v2_tasks",
        "lab_v2_holds",
        "lab_v2_transactions",
        "lab_v2_treasuries",
        "lab_v2_artifacts",
        "lab_v2_actions",
        "lab_v2_outbox_events",
        "lab_v1_v2_reconciliation",
    ],
    "backfills": [
        "copy tasks",
        "copy holds",
        "copy user and treasury ledger state",
        "copy artifact provenance",
        "copy Broker actions",
        "copy outbox state",
        "establish v1/v2 row lineage",
        "operate an ongoing financial reconciliation bridge",
    ],
    "services": [
        "lab-v2-gateway",
        "lab-runtime",
        "lab-executor",
        "artifact-cleanup",
        "lab-v1-v2-financial-bridge",
    ],
    "financial_domains": 2,
}


def _iter_python_files(repo_root: Path) -> Iterable[Path]:
    for relative in AUDITED_PATHS:
        path = repo_root / relative
        if path.is_dir():
            yield from sorted(path.rglob("*.py"))
        elif path.is_file():
            yield path


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.symbols: list[str] = []
        self.findings: set[Finding] = set()
        self.call_aliases: dict[str, str] = {}

    @property
    def symbol(self) -> str:
        return ".".join(self.symbols) if self.symbols else "<module>"

    def _visit_symbol(self, node: ast.AST) -> None:
        self.symbols.append(node.name)  # type: ignore[attr-defined]
        self.generic_visit(node)
        self.symbols.pop()

    visit_FunctionDef = _visit_symbol
    visit_AsyncFunctionDef = _visit_symbol

    @staticmethod
    def _string_values(node: ast.AST) -> set[str] | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {node.value}
        if isinstance(node, ast.IfExp):
            left = _Visitor._string_values(node.body)
            right = _Visitor._string_values(node.orelse)
            return None if left is None or right is None else left | right
        return None

    def _record_status_write(self, operation: str, value: ast.AST) -> None:
        possible = self._string_values(value)
        if possible is not None and not (possible & TERMINAL_STATUSES):
            return
        values = sorted(possible & TERMINAL_STATUSES) if possible is not None else ["<dynamic>"]
        for terminal in values:
            self.findings.add(Finding("write", self.path, self.symbol, operation, terminal))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name in TERMINAL_CALLS:
                self.call_aliases[alias.asname or alias.name] = alias.name
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        source_operation = None
        if isinstance(node.value, ast.Attribute) and node.value.attr in TERMINAL_CALLS:
            source_operation = node.value.attr
        elif isinstance(node.value, ast.Name):
            source_operation = self.call_aliases.get(node.value.id)
        for target in node.targets:
            if isinstance(target, ast.Name) and source_operation:
                self.call_aliases[target.id] = source_operation
            if isinstance(target, ast.Attribute) and target.attr == "status":
                self._record_status_write(ast.unparse(target), node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if (
            isinstance(node.target, ast.Attribute)
            and node.target.attr == "status"
            and node.value is not None
        ):
            self._record_status_write(ast.unparse(node.target), node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        operation = ""
        if isinstance(node.func, ast.Attribute):
            operation = node.func.attr
        elif isinstance(node.func, ast.Name):
            operation = self.call_aliases.get(node.func.id, node.func.id)
        if operation in TERMINAL_CALLS:
            self.findings.add(Finding("call", self.path, self.symbol, operation))

        if (
            operation == "setattr"
            and len(node.args) >= 3
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "status"
        ):
            self._record_status_write(f"setattr({ast.unparse(node.args[0])}.status)", node.args[2])

        for keyword in node.keywords:
            if keyword.arg == "status":
                self._record_status_write(f"{operation or '<call>'}.status", keyword.value)
            elif keyword.arg is None and isinstance(keyword.value, ast.Dict):
                for key, value in zip(keyword.value.keys, keyword.value.values):
                    if isinstance(key, ast.Constant) and key.value == "status":
                        self._record_status_write(f"{operation or '<call>'}.status", value)
        self.generic_visit(node)


def source_findings(repo_root: Path) -> set[Finding]:
    findings: set[Finding] = set()
    for path in _iter_python_files(repo_root):
        relative = path.relative_to(repo_root).as_posix()
        visitor = _Visitor(relative)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=relative))
        findings.update(visitor.findings)
    return findings


PLANNED_QUEUE_KEYS = {
    "v1_pending": "sv:lab:v1:queue",
    "v1_processing": "sv:lab:v1:processing",
    "v2_pending": "sv:lab:v2:queue",
    "v2_processing": "sv:lab:v2:processing",
}


def queue_constants(repo_root: Path) -> dict[str, str]:
    path = repo_root / "backend/app/lab/queue.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = {
        "V1_QUEUE_KEY": "v1_pending",
        "V1_PROCESSING_KEY": "v1_processing",
        "V2_QUEUE_KEY": "v2_pending",
        "V2_PROCESSING_KEY": "v2_processing",
    }
    values: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                values[names[target.id]] = str(node.value.value)
    return values


def _counts(option: dict) -> dict[str, int]:
    return {
        key: len(option[key]) for key in ("files", "symbols", "tables", "backfills", "services")
    } | {"financial_domains": int(option["financial_domains"])}


def _parse_spike(raw: bytes) -> dict[str, object]:
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")

    def passed(name: str) -> bool:
        return re.search(rf"(?m)^{re.escape(name)}=PASS(?:\s|$)", text) is not None

    failure_match = re.search(r"(?m)^failure_count=(\d+)\s*$", text)
    failure_count = int(failure_match.group(1)) if failure_match else None
    postgres_checks = (
        "legacy_direct_dml",
        "terminalizer_direct_dml",
        "legacy_function_execute",
        "terminalizer_set_role_owner",
        "terminalizer_controlled_entrypoint",
    )
    postgres_passed = (
        failure_count == 0
        and all(passed(name) for name in postgres_checks)
        and "lab_financial_kernel_owner|f|f|f|f" in text
        and "postgres_membership_oracle:\n0\n" in text
        and "postgres_final_state:\nsettled|completed" in text
    )
    queue_passed = (
        failure_count == 0
        and passed("physical_queue_cross_claim")
        and "v1_second=empty" in text
        and "redis_version=" in text
    )
    return {
        "failure_count": failure_count,
        "postgres_role_guard_passed": postgres_passed,
        "physical_queue_split_passed": queue_passed,
    }


def _spike_metadata(raw: bytes) -> dict[str, object]:
    """Accept either the original spike log or a prior rendered inventory JSON."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _parse_spike(raw)

    if isinstance(parsed, dict):
        nested = parsed.get("postgres_and_queue_spike")
        if isinstance(nested, dict):
            return {
                "failure_count": nested.get("failure_count"),
                "postgres_role_guard_passed": bool(
                    nested.get("postgres_role_guard_passed")
                ),
                "physical_queue_split_passed": bool(
                    nested.get("physical_queue_split_passed")
                ),
            }
        hard_oracles = parsed.get("hard_oracles")
        if isinstance(hard_oracles, dict):
            return {
                "failure_count": None,
                "postgres_role_guard_passed": bool(
                    hard_oracles.get("controlled_postgres_entrypoint_spike")
                ),
                "physical_queue_split_passed": bool(
                    hard_oracles.get("physical_queue_split_spike")
                ),
            }
    return _parse_spike(raw)


def audit(repo_root: Path, spike_evidence: Path | None = None) -> dict:
    actual = source_findings(repo_root)
    unknown = sorted(actual - EXPECTED_FINDINGS)
    missing = sorted(EXPECTED_FINDINGS - actual)
    queues = queue_constants(repo_root)

    spike: dict[str, object] = {"provided": False}
    if spike_evidence is not None:
        raw = spike_evidence.read_bytes()
        spike = {
            "provided": True,
            "path": str(spike_evidence.resolve()),
            "sha256": hashlib.sha256(raw).hexdigest(),
            **_spike_metadata(raw),
        }

    a_counts = _counts(A_PRIME)
    b_counts = _counts(OPTION_B)
    comparison_passed = (
        a_counts["financial_domains"] == 1
        and a_counts["services"] <= b_counts["services"]
        and a_counts["backfills"] < b_counts["backfills"]
        and len(set(A_PRIME["tables"]) & {
            "lab_v2_tasks", "lab_v2_holds", "lab_v2_transactions", "lab_v2_treasuries"
        }) == 0
    )
    hard_oracles = {
        "source_inventory_has_no_unknown": not unknown and not missing,
        "controlled_postgres_entrypoint_spike": bool(spike.get("postgres_role_guard_passed")),
        "physical_queue_split_spike": bool(spike.get("physical_queue_split_passed")),
        "current_physical_queue_split": queues == PLANNED_QUEUE_KEYS,
        "a_prime_keeps_one_financial_domain": a_counts["financial_domains"] == 1,
    }
    return {
        "schema_version": 1,
        "source_findings": [asdict(item) for item in sorted(actual)],
        "unknown_findings": [asdict(item) for item in unknown],
        "missing_findings": [asdict(item) for item in missing],
        "runtime_callers": CURRENT_RUNTIME_CALLERS,
        "dynamic_sql_or_configured_jobs": {
            "dynamic_terminal_sql": [],
            "configured_jobs": [
                "API optional nightly_cron_loop",
                "agent-worker nightly_cron_loop",
                "Lab Runner runner_loop",
                "Lab Runner terminalizer command/event loop",
                "player/admin Lab routes",
            ],
        },
        "current_queue_keys": queues,
        "planned_queue_keys": PLANNED_QUEUE_KEYS,
        "planned_db_roles": PLANNED_DB_ROLES,
        "postgres_and_queue_spike": spike,
        "comparative_matrix": {
            "a_prime": {"counts": a_counts, **A_PRIME},
            "b": {"counts": b_counts, **OPTION_B},
            "decision_rule_passed": comparison_passed,
        },
        "hard_oracles": hard_oracles,
        "decision": "A_PRIME" if all(hard_oracles.values()) and comparison_passed else "STOP_AND_REASSESS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--spike-evidence", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    result = audit(args.repo_root.resolve(), args.spike_evidence)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.strict and result["decision"] != "A_PRIME":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
