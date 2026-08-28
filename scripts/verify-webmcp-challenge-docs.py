#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


CHALLENGE_DIR = Path("docs/webmcp-challenge")
REQUIRED_FILES = [
    Path("README.md"),
    CHALLENGE_DIR / "JUDGING_MAP.md",
    CHALLENGE_DIR / "SECURITY.md",
    CHALLENGE_DIR / "TEST_PLAN.md",
    CHALLENGE_DIR / "WEBMCP_TOOLS.md",
    CHALLENGE_DIR / "DEMO_SCRIPT.md",
    CHALLENGE_DIR / "FIXTURE_LOCK.md",
    CHALLENGE_DIR / "LIVE_GATE.md",
]
DELIVERY_DOCS = [
    Path("README.md"),
    CHALLENGE_DIR / "JUDGING_MAP.md",
    CHALLENGE_DIR / "SECURITY.md",
    CHALLENGE_DIR / "TEST_PLAN.md",
    CHALLENGE_DIR / "WEBMCP_TOOLS.md",
    CHALLENGE_DIR / "DEMO_SCRIPT.md",
    CHALLENGE_DIR / "FIXTURE_LOCK.md",
]
OLD_TOOL_TOKENS = [
    "inspect_town_signals",
    "focus_evidence",
    "draft_interventions",
    "preview_intervention",
    "discard_intervention",
    "stage_intervention",
    "commit_intervention",
    "verify_outcome",
    "reset_challenge_town",
]
FINAL_TOOLS = [
    "simverse_investigate_crisis",
    "simverse_preview_intervention",
    "simverse_commit_approved",
    "simverse_verify_outcome",
    "simverse_reset_town",
]
JUDGING_CRITERIA = {
    "WebMCP leverage",
    "Execution",
    "Potential impact",
    "Creativity and ambition",
}
EXPECTED_LIVE_SUMMARY = (
    "day0_chatgpt=3/3 chrome149=3/3 ordinary_fallback=1/1 "
    "duplicate_tools=0 stale_tools=0"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the current WebMCP Challenge documentation contract.")
    parser.add_argument("--root", required=True, type=Path)
    return parser.parse_args()


def read_required_files(root: Path, violations: list[str]) -> dict[Path, str]:
    contents: dict[Path, str] = {}
    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file():
            violations.append(f"missing required file: {relative}")
            continue
        contents[relative] = path.read_text(encoding="utf-8")
    return contents


def check_old_tool_tokens(contents: dict[Path, str], violations: list[str]) -> None:
    for relative in DELIVERY_DOCS:
        text = contents.get(relative)
        if text is None:
            continue
        for token in OLD_TOOL_TOKENS:
            pattern = re.compile(
                rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])"
            )
            if pattern.search(text):
                violations.append(f"{relative}: obsolete tool token {token}")


def markdown_h2_sections(text: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r"(?m)^##\s+", text)]
    if not starts:
        return [text]
    sections: list[str] = []
    if starts[0] > 0:
        sections.append(text[: starts[0]])
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        sections.append(text[start:end])
    return sections


def check_tool_contract(contents: dict[Path, str], violations: list[str]) -> None:
    relative = CHALLENGE_DIR / "WEBMCP_TOOLS.md"
    text = contents.get(relative)
    if text is None:
        return
    for tool in FINAL_TOOLS:
        count = len(re.findall(rf"(?m)^###\s+`{re.escape(tool)}`\s*$", text))
        if count != 1:
            violations.append(
                f"{relative}: {tool} must have exactly one definition heading; found {count}"
            )
    diagnostics_ok = any(
        "simverse_get_challenge_status" in section and "diagnostics=1" in section
        for section in markdown_h2_sections(text)
    )
    if not diagnostics_ok:
        violations.append(
            f"{relative}: simverse_get_challenge_status and diagnostics=1 must share one section"
        )


def check_security(contents: dict[Path, str], violations: list[str]) -> None:
    relative = CHALLENGE_DIR / "SECURITY.md"
    text = contents.get(relative)
    if text is None:
        return
    for token in ("diff_hash", "world_version", "WATCH", "CAS", "Origin", "CSRF"):
        if token not in text:
            violations.append(f"{relative}: missing security token {token}")
    if not re.search(r"(?mi)^Threat statement:\s+\S", text):
        violations.append(f"{relative}: missing explicit Threat statement")


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def check_judging_map(contents: dict[Path, str], violations: list[str]) -> None:
    relative = CHALLENGE_DIR / "JUDGING_MAP.md"
    text = contents.get(relative)
    if text is None:
        return
    expected_header = [
        "Criterion",
        "Product evidence",
        "Test node id",
        "E2E evidence",
        "Live screenshot",
    ]
    lines = text.splitlines()
    header_index = next(
        (index for index, line in enumerate(lines) if split_table_row(line) == expected_header),
        None,
    )
    if header_index is None:
        violations.append(f"{relative}: missing exact five-column judging evidence table")
        return
    rows: dict[str, list[str]] = {}
    for line in lines[header_index + 2 :]:
        if not line.lstrip().startswith("|"):
            break
        cells = split_table_row(line)
        if len(cells) == 5 and cells[0] in JUDGING_CRITERIA:
            rows[cells[0]] = cells
    if set(rows) != JUDGING_CRITERIA:
        violations.append(f"{relative}: judging table must contain all four criteria exactly once")
    for criterion, cells in rows.items():
        if any(not cell for cell in cells):
            violations.append(f"{relative}: {criterion} has an empty evidence cell")


def check_test_plan(contents: dict[Path, str], violations: list[str]) -> None:
    relative = CHALLENGE_DIR / "TEST_PLAN.md"
    text = contents.get(relative)
    if text is None:
        return
    for layer in ("Automated", "Local", "E2E", "Live", "Deployed"):
        if not re.search(rf"(?i)\b{layer}\b", text):
            violations.append(f"{relative}: missing evidence layer {layer}")


def check_demo(contents: dict[Path, str], violations: list[str]) -> None:
    relative = CHALLENGE_DIR / "DEMO_SCRIPT.md"
    text = contents.get(relative)
    if text is None:
        return
    for label in ("Prediction", "Actual", "No-action control"):
        if label not in text:
            violations.append(f"{relative}: missing outcome label {label}")
    durations = re.findall(r"Total duration:\s*(\d+):(\d{2})", text)
    if len(durations) != 1:
        violations.append(f"{relative}: expected exactly one Total duration: M:SS")
        return
    minutes, seconds = (int(value) for value in durations[0])
    if seconds >= 60 or minutes * 60 + seconds > 180:
        violations.append(f"{relative}: demo duration exceeds 180 seconds")


def check_fixture(contents: dict[Path, str], violations: list[str]) -> None:
    relative = CHALLENGE_DIR / "FIXTURE_LOCK.md"
    text = contents.get(relative)
    if text is None:
        return
    required_fragments = [
        "scenario_id: harbor-wage-crisis-v1",
        "fixture_version: 1",
        "forecast_seeds: [101, 102, 103, 104, 105]",
        "actual_seed: 211",
        "initial_hash: sha256:d095c7b5c759a58e6d07f5b6a6c4c2687016ce2b64295cfaad2490010ca5cb10",
        "expected_actual: high_food_risk_residents=1 social_tension=54 strike_risk_pct=38 stabilized_residents=5",
        "expected_no_action: high_food_risk_residents=3 social_tension=81 strike_risk_pct=100 stabilized_residents=0 strike_event_triggered=true",
    ]
    for fragment in required_fragments:
        if fragment not in text:
            violations.append(f"{relative}: missing locked fragment {fragment}")


def check_readme(contents: dict[Path, str], violations: list[str]) -> None:
    text = contents.get(Path("README.md"))
    if text is None:
        return
    if "[Civic Copilot Challenge](docs/webmcp-challenge/WEBMCP_TOOLS.md)" not in text:
        violations.append("README.md: missing Civic Copilot Challenge entry")
    if not re.search(r"(?i)deterministic isolated", text):
        violations.append("README.md: missing deterministic isolated-town disclaimer")


def live_gate_complete(text: str) -> bool:
    upper = text.upper()
    if "FAIL" in upper or "UNVERIFIED" in upper:
        return False
    chatgpt_rows = [
        line for line in text.splitlines() if line.startswith("| ChatGPT in-app Browser")
    ]
    chrome_rows = [
        line for line in text.splitlines() if line.startswith("| Chrome for Testing")
    ]
    ordinary_rows = [
        line for line in text.splitlines() if line.startswith("| Ordinary Chrome")
    ]
    return (
        len(chatgpt_rows) == 3
        and len(chrome_rows) == 3
        and len(ordinary_rows) == 1
        and all("PASS" in line for line in [*chatgpt_rows, *chrome_rows, *ordinary_rows])
        and EXPECTED_LIVE_SUMMARY in text
    )


def check_live_claims(contents: dict[Path, str], violations: list[str]) -> None:
    live_text = contents.get(CHALLENGE_DIR / "LIVE_GATE.md")
    if live_text is None or live_gate_complete(live_text):
        return
    claims = re.compile(r"(?i)\b(?:live verified|deployed and verified)\b")
    for relative in (Path("README.md"), CHALLENGE_DIR / "JUDGING_MAP.md"):
        text = contents.get(relative, "")
        if claims.search(text):
            violations.append(f"{relative}: live verification claim exceeds LIVE_GATE evidence")


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    violations: list[str] = []
    contents = read_required_files(root, violations)
    check_old_tool_tokens(contents, violations)
    check_tool_contract(contents, violations)
    check_security(contents, violations)
    check_judging_map(contents, violations)
    check_test_plan(contents, violations)
    check_demo(contents, violations)
    check_fixture(contents, violations)
    check_readme(contents, violations)
    check_live_claims(contents, violations)
    if violations:
        for violation in sorted(set(violations)):
            print(f"challenge_docs_violation: {violation}", file=sys.stderr)
        return 1
    print("challenge_docs_contract=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
