#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


EVIDENCE_FILES = {
    "e2e": Path("docs/webmcp-challenge/E2E_EVIDENCE.md"),
    "benchmark": Path("docs/webmcp-challenge/BENCHMARK.md"),
}
RUNTIME_PREFIXES = (
    "backend/alembic/",
    "backend/app/challenge/",
    "frontend/src/components/challenge/",
    "frontend/src/webmcp/",
)
RUNTIME_FILES = {
    "backend/app/config.py",
    "backend/app/main.py",
    "backend/app/routers/challenge.py",
    "backend/pyproject.toml",
    "docker-compose.yml",
    "frontend/e2e/challenge-benchmark.spec.ts",
    "frontend/e2e/challenge-flow.spec.ts",
    "frontend/package-lock.json",
    "frontend/package.json",
    "frontend/playwright.config.ts",
    "frontend/src/pages/ChallengePage.tsx",
    "frontend/src/services/api/challenge.ts",
    "frontend/src/services/challengeTelemetry.ts",
    "frontend/src/stores/challengeStore.ts",
    "frontend/vite.config.ts",
    "scripts/run-challenge-e2e.sh",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reject Challenge runtime drift after the E2E evidence source commit.",
    )
    parser.add_argument("--root", required=True, type=Path)
    return parser.parse_args()


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def is_runtime_path(path: str) -> bool:
    return path in RUNTIME_FILES or path.startswith(RUNTIME_PREFIXES)


def main() -> int:
    root = parse_args().root.resolve()
    violations: list[str] = []
    source_heads: dict[str, str] = {}
    for label, relative in EVIDENCE_FILES.items():
        evidence_path = root / relative
        if not evidence_path.is_file():
            violations.append(f"{label}: missing {relative}")
            continue
        text = evidence_path.read_text(encoding="utf-8")
        match = re.search(
            r"(?:source\s+HEAD|Runtime source HEAD):?\s+`([0-9a-f]{40})`",
            text,
            flags=re.IGNORECASE,
        )
        if match is None:
            violations.append(f"{label}: missing 40-character Runtime source HEAD")
            continue
        source_head = match.group(1)
        source_heads[label] = source_head

        resolved = git(root, "rev-parse", "--verify", f"{source_head}^{{commit}}")
        if resolved.returncode != 0:
            violations.append(f"{label}: source HEAD does not resolve: {source_head}")
            continue
        ancestor = git(root, "merge-base", "--is-ancestor", source_head, "HEAD")
        if ancestor.returncode != 0:
            violations.append(f"{label}: source HEAD is not an ancestor: {source_head}")
            continue

        changed = git(root, "diff", "--name-only", f"{source_head}..HEAD", "--")
        if changed.returncode != 0:
            violations.append(f"{label}: git diff failed")
            continue
        for path in sorted(
            path for path in changed.stdout.splitlines() if is_runtime_path(path)
        ):
            violations.append(f"{label}: runtime changed after evidence: {path}")

    if violations:
        for violation in sorted(set(violations)):
            print(
                f"challenge_e2e_evidence_violation: {violation}",
                file=sys.stderr,
            )
        return 1

    print(
        "challenge_evidence_heads=PASS "
        f"e2e_source_head={source_heads['e2e']} "
        f"benchmark_source_head={source_heads['benchmark']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
