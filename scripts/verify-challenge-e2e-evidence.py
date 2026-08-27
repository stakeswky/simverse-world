#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


EVIDENCE = Path("docs/webmcp-challenge/E2E_EVIDENCE.md")
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
    evidence_path = root / EVIDENCE
    if not evidence_path.is_file():
        print(f"challenge_e2e_evidence_violation: missing {EVIDENCE}", file=sys.stderr)
        return 1

    text = evidence_path.read_text(encoding="utf-8")
    match = re.search(
        r"(?:source\s+HEAD|Runtime source HEAD)\s+`([0-9a-f]{40})`",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        print(
            "challenge_e2e_evidence_violation: missing 40-character Runtime source HEAD",
            file=sys.stderr,
        )
        return 1
    source_head = match.group(1)

    resolved = git(root, "rev-parse", "--verify", f"{source_head}^{{commit}}")
    if resolved.returncode != 0:
        print(
            f"challenge_e2e_evidence_violation: source HEAD does not resolve: {source_head}",
            file=sys.stderr,
        )
        return 1
    ancestor = git(root, "merge-base", "--is-ancestor", source_head, "HEAD")
    if ancestor.returncode != 0:
        print(
            f"challenge_e2e_evidence_violation: source HEAD is not an ancestor: {source_head}",
            file=sys.stderr,
        )
        return 1

    changed = git(root, "diff", "--name-only", f"{source_head}..HEAD", "--")
    if changed.returncode != 0:
        print("challenge_e2e_evidence_violation: git diff failed", file=sys.stderr)
        return 1
    runtime_drift = sorted(
        path for path in changed.stdout.splitlines() if is_runtime_path(path)
    )
    if runtime_drift:
        for path in runtime_drift:
            print(
                f"challenge_e2e_evidence_violation: runtime changed after evidence: {path}",
                file=sys.stderr,
            )
        return 1

    print(f"challenge_e2e_evidence_head=PASS source_head={source_head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
