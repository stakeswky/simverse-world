#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable


SCRIPT = Path(__file__).with_name("render-challenge-benchmark.py")
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


def make_row(mode: str, run: int) -> dict[str, Any]:
    return {
        "run_id": f"{mode}-{run}",
        "mode": mode,
        "duration_ms": 1_000 + run,
        "clicks": 6 if mode == "ordinary" else 2,
        "panel_switches": 2,
        "route_switches": 1,
        "wrong_selections": 0,
        "success": True,
        "core_tool_calls": 0 if mode == "ordinary" else 4,
        "unauthorized_attempts": 1,
        "unauthorized_successes": 0,
        "preview_rebuild_count": 0,
        "events": [
            {"event": event, "elapsed_ms": index, "fields": {}}
            for index, event in enumerate(REQUIRED_EVENTS)
        ],
        "unauthorized_probe": {
            "status": 403,
            "code": "APPROVAL_REQUIRED",
            "success": False,
        },
        "commit_evidence": {
            "receipt_id": f"SV-TEST-{mode}-{run}",
            "world_before_version": 7,
            "world_after_version": 8,
            "budget_before_sc": 300,
            "budget_delta_sc": -240,
            "budget_after_sc": 60,
        },
        "verify_evidence": {
            "receipt_id": f"SV-TEST-{mode}-{run}",
            "world_before_version": 8,
            "world_after_version": 9,
            "tick_count": 12,
        },
    }


def valid_payload() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for run in range(1, 6):
        rows.append(make_row("ordinary", run))
        rows.append(make_row("webmcp", run))
    return {
        "schema_version": 1,
        "recorded_at": "2026-08-27T08:00:00Z",
        "source_head": "a" * 40,
        "chromium_version": "151.0.7922.34",
        "rows": rows,
    }


class RenderChallengeBenchmarkTest(unittest.TestCase):
    def run_renderer(
        self,
        payload: dict[str, Any],
    ) -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "raw.json"
            output_path = root / "BENCHMARK.md"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            rendered = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
            return completed, rendered

    def test_valid_paired_rows_render_all_evidence_and_slowest_run(self) -> None:
        completed, rendered = self.run_renderer(valid_payload())

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(
            "ordinary_runs=5 webmcp_runs=5 paired_runs=5 unauthorized_success=0",
            rendered,
        )
        self.assertIn("## Slowest row", rendered)
        for mode in ("ordinary", "webmcp"):
            for run in range(1, 6):
                self.assertIn(f"{mode}-{run}", rendered)

    def test_rejects_every_invalid_contract_shape(self) -> None:
        def missing_row(payload: dict[str, Any]) -> None:
            payload["rows"].pop()

        def duplicate_run_id(payload: dict[str, Any]) -> None:
            payload["rows"][1]["run_id"] = payload["rows"][0]["run_id"]

        def unbalanced_modes(payload: dict[str, Any]) -> None:
            payload["rows"][0]["mode"] = "webmcp"

        def incomplete_events(payload: dict[str, Any]) -> None:
            payload["rows"][0]["events"].pop()

        def unknown_event(payload: dict[str, Any]) -> None:
            payload["rows"][0]["events"][1]["event"] = "private_payload_seen"

        def ordinary_core_call(payload: dict[str, Any]) -> None:
            payload["rows"][0]["core_tool_calls"] = 1

        def wrong_webmcp_call_count(payload: dict[str, Any]) -> None:
            payload["rows"][1]["core_tool_calls"] = 3

        def unauthorized_success(payload: dict[str, Any]) -> None:
            payload["rows"][0]["unauthorized_successes"] = 1

        def successful_probe(payload: dict[str, Any]) -> None:
            payload["rows"][0]["unauthorized_probe"] = {
                "status": 200,
                "code": "COMMITTED",
                "success": True,
            }

        def no_slowest_row(payload: dict[str, Any]) -> None:
            payload["rows"] = []

        mutations: dict[str, Callable[[dict[str, Any]], None]] = {
            "missing_row": missing_row,
            "duplicate_run_id": duplicate_run_id,
            "unbalanced_modes": unbalanced_modes,
            "incomplete_events": incomplete_events,
            "unknown_event": unknown_event,
            "ordinary_core_call": ordinary_core_call,
            "wrong_webmcp_call_count": wrong_webmcp_call_count,
            "unauthorized_success": unauthorized_success,
            "successful_probe": successful_probe,
            "no_slowest_row": no_slowest_row,
        }

        for name, mutate in mutations.items():
            with self.subTest(name=name):
                payload = copy.deepcopy(valid_payload())
                mutate(payload)
                completed, rendered = self.run_renderer(payload)
                self.assertNotEqual(completed.returncode, 0)
                self.assertTrue(completed.stderr.strip())
                self.assertEqual(rendered, "")


if __name__ == "__main__":
    unittest.main()
