#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable


SCRIPT = Path(__file__).with_name("verify-webmcp-challenge-docs.py")
FINAL_TOOLS = [
    "simverse_investigate_crisis",
    "simverse_preview_intervention",
    "simverse_commit_approved",
    "simverse_verify_outcome",
    "simverse_reset_town",
]


def valid_documents() -> dict[str, str]:
    tool_sections = "\n".join(f"### `{name}`\nContract.\n" for name in FINAL_TOOLS)
    live_rows = "\n".join(
        [
            *(f"| ChatGPT in-app Browser | 151 | {run} | PASS | PASS | PASS | 0 |" for run in range(1, 4)),
            *(f"| Chrome for Testing | 149 | {run} | PASS | PASS | PASS | 0 |" for run in range(1, 4)),
            "| Ordinary Chrome | 151 | 1 | N/A | N/A | PASS | 0 |",
        ]
    )
    return {
        "README.md": (
            "# Simverse\n"
            "[Civic Copilot Challenge](docs/webmcp-challenge/WEBMCP_TOOLS.md) uses a "
            "deterministic isolated town and is not the production town.\n"
        ),
        "docs/webmcp-challenge/JUDGING_MAP.md": """# Judging Map

| Criterion | Product evidence | Test node id | E2E evidence | Live screenshot |
|---|---|---|---|---|
| WebMCP leverage | five tools | contract node | E2E evidence | Day-0 screenshot |
| Execution | reset | router node | E2E evidence | Day-0 screenshot |
| Potential impact | benchmark | benchmark node | E2E evidence | Final mutation live pending |
| Creativity and ambition | outcome | outcome node | E2E evidence | Final mutation live pending |
""",
        "docs/webmcp-challenge/SECURITY.md": """# Security

Threat statement: Untrusted Site Tool input must never create, widen, or replay human approval.
The server binds diff_hash and world_version. Redis WATCH implements CAS.
Every mutation checks exact Origin and CSRF before entering the service.
""",
        "docs/webmcp-challenge/TEST_PLAN.md": """# Test Plan

## Automated contract
Automated checks run first.
## Local runtime
Local Redis evidence is separate.
## E2E browser
E2E uses real Chromium.
## Live browser
Live evidence is host-specific.
## Deployed identity
Deployed assets require exact SHA evidence.
""",
        "docs/webmcp-challenge/WEBMCP_TOOLS.md": (
            "# Tools\n\n"
            "## Diagnostics-only status probe\n"
            "`simverse_get_challenge_status` is available only at `diagnostics=1`.\n\n"
            + tool_sections
        ),
        "docs/webmcp-challenge/DEMO_SCRIPT.md": """# Demo

Total duration: 2:55
Show Prediction, Actual, and No-action control after the verified outcome.
""",
        "docs/webmcp-challenge/FIXTURE_LOCK.md": """# Fixture lock

scenario_id: harbor-wage-crisis-v1
fixture_version: 1
forecast_seeds: [101, 102, 103, 104, 105]
actual_seed: 211
initial_hash: sha256:d095c7b5c759a58e6d07f5b6a6c4c2687016ce2b64295cfaad2490010ca5cb10
expected_actual: high_food_risk_residents=1 social_tension=54 strike_risk_pct=38 stabilized_residents=5
expected_no_action: high_food_risk_residents=3 social_tension=81 strike_risk_pct=100 stabilized_residents=0 strike_event_triggered=true
""",
        "docs/webmcp-challenge/LIVE_GATE.md": (
            "# Live Gate\n\n"
            + live_rows
            + "\n\n`day0_chatgpt=3/3 chrome149=3/3 ordinary_fallback=1/1 duplicate_tools=0 stale_tools=0`\n"
        ),
    }


class VerifyChallengeDocsTest(unittest.TestCase):
    def make_root(self) -> Path:
        temporary = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temporary, ignore_errors=True)
        for relative, content in valid_documents().items():
            path = temporary / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return temporary

    def run_verify(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root)],
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_invalid(
        self,
        mutate: Callable[[Path], None],
    ) -> None:
        root = self.make_root()
        mutate(root)
        completed = self.run_verify(root)
        self.assertNotEqual(completed.returncode, 0)
        self.assertTrue(completed.stderr.strip())

    def test_valid_contract_passes(self) -> None:
        completed = self.run_verify(self.make_root())

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("challenge_docs_contract=PASS", completed.stdout)

    def test_required_files_old_exact_tokens_and_tool_sections_are_enforced(self) -> None:
        def remove_fixture(root: Path) -> None:
            (root / "docs/webmcp-challenge/FIXTURE_LOCK.md").unlink()

        def add_old_token(root: Path) -> None:
            with (root / "docs/webmcp-challenge/DEMO_SCRIPT.md").open("a", encoding="utf-8") as handle:
                handle.write("Call preview_intervention.\n")

        def remove_tool_heading(root: Path) -> None:
            path = root / "docs/webmcp-challenge/WEBMCP_TOOLS.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "### `simverse_commit_approved`",
                    "Commit is mentioned but not defined",
                ),
                encoding="utf-8",
            )

        def separate_diagnostics(root: Path) -> None:
            path = root / "docs/webmcp-challenge/WEBMCP_TOOLS.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "only at `diagnostics=1`.",
                    "only on an explicit route.\n\n## Other section\n`diagnostics=1`.",
                ),
                encoding="utf-8",
            )

        for mutate in (remove_fixture, add_old_token, remove_tool_heading, separate_diagnostics):
            with self.subTest(mutate=mutate.__name__):
                self.assert_invalid(mutate)

        root = self.make_root()
        with (root / "docs/webmcp-challenge/TEST_PLAN.md").open("a", encoding="utf-8") as handle:
            handle.write("simverse_preview_intervention and simverse_verify_outcome remain final.\n")
        completed = self.run_verify(root)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_security_judging_demo_fixture_and_readme_contracts_are_enforced(self) -> None:
        def remove_threat_statement(root: Path) -> None:
            path = root / "docs/webmcp-challenge/SECURITY.md"
            path.write_text(path.read_text(encoding="utf-8").replace("Threat statement:", "Note:"), encoding="utf-8")

        def blank_judging_cell(root: Path) -> None:
            path = root / "docs/webmcp-challenge/JUDGING_MAP.md"
            path.write_text(path.read_text(encoding="utf-8").replace("| contract node |", "|  |", 1), encoding="utf-8")

        def overlong_demo(root: Path) -> None:
            path = root / "docs/webmcp-challenge/DEMO_SCRIPT.md"
            path.write_text(path.read_text(encoding="utf-8").replace("2:55", "3:01"), encoding="utf-8")

        def drift_fixture(root: Path) -> None:
            path = root / "docs/webmcp-challenge/FIXTURE_LOCK.md"
            path.write_text(path.read_text(encoding="utf-8").replace("actual_seed: 211", "actual_seed: 212"), encoding="utf-8")

        def remove_readme_disclaimer(root: Path) -> None:
            path = root / "README.md"
            path.write_text(path.read_text(encoding="utf-8").replace("deterministic isolated", "ordinary"), encoding="utf-8")

        for mutate in (
            remove_threat_statement,
            blank_judging_cell,
            overlong_demo,
            drift_fixture,
            remove_readme_disclaimer,
        ):
            with self.subTest(mutate=mutate.__name__):
                self.assert_invalid(mutate)

    def test_live_claims_require_complete_pass_rows_and_summary(self) -> None:
        def claim(root: Path) -> None:
            with (root / "README.md").open("a", encoding="utf-8") as handle:
                handle.write("The final experience is deployed and verified.\n")

        def missing_chatgpt_row(root: Path) -> None:
            path = root / "docs/webmcp-challenge/LIVE_GATE.md"
            lines = path.read_text(encoding="utf-8").splitlines()
            removed = False
            retained = []
            for line in lines:
                if not removed and line.startswith("| ChatGPT in-app Browser"):
                    removed = True
                    continue
                retained.append(line)
            path.write_text("\n".join(retained) + "\n", encoding="utf-8")
            claim(root)

        def failed_chrome_row(root: Path) -> None:
            path = root / "docs/webmcp-challenge/LIVE_GATE.md"
            path.write_text(path.read_text(encoding="utf-8").replace("| PASS |", "| FAIL |", 1), encoding="utf-8")
            claim(root)

        def unverified_gate(root: Path) -> None:
            path = root / "docs/webmcp-challenge/LIVE_GATE.md"
            path.write_text(path.read_text(encoding="utf-8") + "UNVERIFIED\n", encoding="utf-8")
            claim(root)

        def short_summary(root: Path) -> None:
            path = root / "docs/webmcp-challenge/LIVE_GATE.md"
            path.write_text(path.read_text(encoding="utf-8").replace("chatgpt=3/3", "chatgpt=2/3"), encoding="utf-8")
            claim(root)

        for mutate in (missing_chatgpt_row, failed_chrome_row, unverified_gate, short_summary):
            with self.subTest(mutate=mutate.__name__):
                self.assert_invalid(mutate)

        root = self.make_root()
        claim(root)
        completed = self.run_verify(root)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
