#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


EVENT_VOCABULARY = {
    "task_started",
    "panel_opened",
    "wrong_target_selected",
    "crisis_identified",
    "preview_requested",
    "preview_ready",
    "approval_viewed",
    "approval_granted",
    "commit_attempted",
    "commit_succeeded",
    "verification_started",
    "verification_ready",
    "task_completed",
}
REQUIRED_EVENTS = [
    "task_started",
    "panel_opened",
    "crisis_identified",
    "preview_requested",
    "preview_ready",
    "approval_viewed",
    "approval_granted",
    "commit_attempted",
    "commit_succeeded",
    "verification_started",
    "verification_ready",
    "task_completed",
]
ROW_FIELDS = {
    "run_id",
    "mode",
    "duration_ms",
    "clicks",
    "panel_switches",
    "route_switches",
    "wrong_selections",
    "success",
    "core_tool_calls",
    "unauthorized_attempts",
    "unauthorized_successes",
    "preview_rebuild_count",
    "events",
    "unauthorized_probe",
    "commit_evidence",
    "verify_evidence",
}
SAFE_EVENT_FIELDS = {
    "duration_ms",
    "clicks",
    "panel",
    "route",
    "wrong_selection",
    "success",
    "core_tool_calls",
    "unauthorized_attempts",
    "unauthorized_successes",
    "preview_rebuild_count",
}
COMMIT_EVIDENCE_FIELDS = {
    "receipt_id",
    "world_before_version",
    "world_after_version",
    "budget_before_sc",
    "budget_delta_sc",
    "budget_after_sc",
}
VERIFY_EVIDENCE_FIELDS = {
    "receipt_id",
    "world_before_version",
    "world_after_version",
    "tick_count",
}


class BenchmarkValidationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BenchmarkValidationError(message)


def is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def require_non_negative(value: Any, label: str) -> None:
    require(is_number(value) and value >= 0, f"{label} must be non-negative.")


def validate_event_sequence(row: dict[str, Any], label: str) -> None:
    events = row["events"]
    require(isinstance(events, list), f"{label}.events must be a list.")
    names: list[str] = []
    previous_elapsed = -1.0
    for index, event in enumerate(events):
        event_label = f"{label}.events[{index}]"
        require(isinstance(event, dict), f"{event_label} must be an object.")
        require(
            set(event) == {"event", "elapsed_ms", "fields"},
            f"{event_label} has unexpected fields.",
        )
        name = event["event"]
        require(name in EVENT_VOCABULARY, f"{event_label} has unknown event {name!r}.")
        elapsed = event["elapsed_ms"]
        require_non_negative(elapsed, f"{event_label}.elapsed_ms")
        require(elapsed >= previous_elapsed, f"{label}.events must be time ordered.")
        previous_elapsed = float(elapsed)
        fields = event["fields"]
        require(isinstance(fields, dict), f"{event_label}.fields must be an object.")
        require(
            set(fields).issubset(SAFE_EVENT_FIELDS),
            f"{event_label}.fields contains unsafe keys.",
        )
        names.append(name)

    without_wrong = [name for name in names if name != "wrong_target_selected"]
    require(
        without_wrong == REQUIRED_EVENTS,
        f"{label} does not contain the required lifecycle event order.",
    )
    wrong_count = names.count("wrong_target_selected")
    require(
        wrong_count == row["wrong_selections"],
        f"{label} wrong selection event/count mismatch.",
    )
    if wrong_count:
        panel_index = names.index("panel_opened")
        crisis_index = names.index("crisis_identified")
        require(
            all(
                panel_index < index < crisis_index
                for index, name in enumerate(names)
                if name == "wrong_target_selected"
            ),
            f"{label} wrong selections must precede crisis identification.",
        )


def validate_row(row: Any, index: int) -> dict[str, Any]:
    label = f"rows[{index}]"
    require(isinstance(row, dict), f"{label} must be an object.")
    require(set(row) == ROW_FIELDS, f"{label} has missing or unexpected fields.")
    mode = row["mode"]
    require(mode in {"ordinary", "webmcp"}, f"{label}.mode is invalid.")
    require(isinstance(row["run_id"], str), f"{label}.run_id must be a string.")
    for field in (
        "duration_ms",
        "clicks",
        "panel_switches",
        "route_switches",
        "wrong_selections",
        "core_tool_calls",
        "unauthorized_attempts",
        "unauthorized_successes",
        "preview_rebuild_count",
    ):
        require_non_negative(row[field], f"{label}.{field}")
    require(row["success"] is True, f"{label} did not complete successfully.")
    require(row["wrong_selections"] == 0, f"{label} contains a synthetic wrong selection.")
    require(row["preview_rebuild_count"] == 0, f"{label} rebuilt its preview.")
    require(row["unauthorized_attempts"] == 1, f"{label} lacks the real denial probe.")
    require(row["unauthorized_successes"] == 0, f"{label} has an unauthorized success.")
    expected_core_calls = 0 if mode == "ordinary" else 4
    require(
        row["core_tool_calls"] == expected_core_calls,
        f"{label} core_tool_calls must be {expected_core_calls} for {mode}.",
    )
    validate_event_sequence(row, label)

    probe = row["unauthorized_probe"]
    require(
        probe == {"status": 403, "code": "APPROVAL_REQUIRED", "success": False},
        f"{label} does not contain the authoritative 403 approval probe.",
    )
    commit = row["commit_evidence"]
    require(isinstance(commit, dict), f"{label}.commit_evidence must be an object.")
    require(set(commit) == COMMIT_EVIDENCE_FIELDS, f"{label}.commit_evidence shape is invalid.")
    require(
        isinstance(commit["receipt_id"], str) and bool(commit["receipt_id"]),
        f"{label}.commit_evidence.receipt_id is missing.",
    )
    require(
        (
            commit["world_before_version"],
            commit["world_after_version"],
            commit["budget_before_sc"],
            commit["budget_delta_sc"],
            commit["budget_after_sc"],
        )
        == (7, 8, 300, -240, 60),
        f"{label}.commit_evidence does not match the locked fixture.",
    )
    verify = row["verify_evidence"]
    require(isinstance(verify, dict), f"{label}.verify_evidence must be an object.")
    require(set(verify) == VERIFY_EVIDENCE_FIELDS, f"{label}.verify_evidence shape is invalid.")
    require(
        verify
        == {
            "receipt_id": commit["receipt_id"],
            "world_before_version": 8,
            "world_after_version": 9,
            "tick_count": 12,
        },
        f"{label}.verify_evidence does not match its commit receipt.",
    )
    return row


def validate_payload(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    require(isinstance(payload, dict), "Benchmark payload must be an object.")
    require(
        set(payload) == {
            "schema_version",
            "recorded_at",
            "source_head",
            "chromium_version",
            "rows",
        },
        "Benchmark payload has missing or unexpected fields.",
    )
    require(payload["schema_version"] == 1, "Unsupported benchmark schema version.")
    require(
        isinstance(payload["recorded_at"], str) and bool(payload["recorded_at"]),
        "recorded_at is required.",
    )
    source_head = payload["source_head"]
    require(
        isinstance(source_head, str)
        and len(source_head) == 40
        and all(character in "0123456789abcdef" for character in source_head),
        "source_head must be a 40-character lowercase Git SHA.",
    )
    require(
        isinstance(payload["chromium_version"], str)
        and bool(payload["chromium_version"]),
        "chromium_version is required.",
    )
    raw_rows = payload["rows"]
    require(isinstance(raw_rows, list), "rows must be a list.")
    require(len(raw_rows) == 10, "rows must contain exactly ten paired runs.")
    rows = [validate_row(row, index) for index, row in enumerate(raw_rows)]
    run_ids = [row["run_id"] for row in rows]
    require(len(set(run_ids)) == len(run_ids), "run_id values must be unique.")
    expected_run_ids = {
        f"{mode}-{run}"
        for mode in ("ordinary", "webmcp")
        for run in range(1, 6)
    }
    require(set(run_ids) == expected_run_ids, "run_id values must form five paired runs.")
    for mode in ("ordinary", "webmcp"):
        require(
            sum(row["mode"] == mode for row in rows) == 5,
            f"{mode} must contain exactly five rows.",
        )
        require(
            all(row["run_id"].startswith(f"{mode}-") for row in rows if row["mode"] == mode),
            f"{mode} row ids do not match their mode.",
        )
    return payload, rows


def format_number(value: int | float) -> str:
    return f"{value:.1f}" if isinstance(value, float) and not value.is_integer() else str(int(value))


def render_markdown(
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
    raw_sha256: str,
) -> str:
    summary = "ordinary_runs=5 webmcp_runs=5 paired_runs=5 unauthorized_success=0"
    slowest = max(rows, key=lambda row: (row["duration_ms"], row["run_id"]))
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lines = [
        "# Challenge paired benchmark",
        "",
        f"`{summary}`",
        "",
        "## Evidence identity",
        "",
        f"- Source HEAD: `{payload['source_head']}`",
        f"- Chromium: `{payload['chromium_version']}`",
        f"- Browser execution recorded at: `{payload['recorded_at']}`",
        f"- Renderer generated at: `{generated_at}`",
        f"- Raw SHA-256: `{raw_sha256}`",
        "",
        "## Medians",
        "",
        "| Mode | Runs | Duration ms | Human clicks | Core tool calls |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for mode in ("ordinary", "webmcp"):
        mode_rows = [row for row in rows if row["mode"] == mode]
        lines.append(
            "| "
            + " | ".join(
                [
                    mode,
                    str(len(mode_rows)),
                    format_number(statistics.median(row["duration_ms"] for row in mode_rows)),
                    format_number(statistics.median(row["clicks"] for row in mode_rows)),
                    format_number(statistics.median(row["core_tool_calls"] for row in mode_rows)),
                ]
            )
            + " |"
        )

    lines.extend([
        "",
        "## All raw rows",
        "",
        "No run was discarded. Rows remain in paired execution order.",
        "",
    ])
    for row in rows:
        lines.extend([
            f"### {row['run_id']}",
            "",
            "```json",
            json.dumps(row, indent=2, sort_keys=True),
            "```",
            "",
        ])
    lines.extend([
        "## Slowest row",
        "",
        f"- Run: `{slowest['run_id']}`",
        f"- Mode: `{slowest['mode']}`",
        f"- Duration: `{format_number(slowest['duration_ms'])} ms`",
        f"- Human clicks: `{format_number(slowest['clicks'])}`",
        f"- Core tool calls: `{format_number(slowest['core_tool_calls'])}`",
        "",
    ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and render Challenge benchmark evidence.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        raw_bytes = args.input.read_bytes()
        payload = json.loads(raw_bytes)
        validated_payload, rows = validate_payload(payload)
        rendered = render_markdown(
            validated_payload,
            rows,
            hashlib.sha256(raw_bytes).hexdigest(),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(f".{args.output.name}.tmp")
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, args.output)
    except (OSError, json.JSONDecodeError, BenchmarkValidationError) as error:
        print(f"benchmark_validation_error: {error}", file=sys.stderr)
        return 1
    print("ordinary_runs=5 webmcp_runs=5 paired_runs=5 unauthorized_success=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
