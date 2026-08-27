#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("verify-challenge-e2e-evidence.py")


class VerifyChallengeE2EEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.run_git("init", "-q")
        self.run_git("config", "user.name", "Challenge Test")
        self.run_git("config", "user.email", "challenge@example.invalid")
        self.write("frontend/src/pages/ChallengePage.tsx", "export const version = 1\n")
        self.write("README.md", "# Simverse\n")
        self.run_git("add", ".")
        self.run_git("commit", "-qm", "runtime")
        self.source_head = self.run_git("rev-parse", "HEAD").stdout.strip()
        self.write_evidence(self.source_head)
        self.run_git("add", ".")
        self.run_git("commit", "-qm", "evidence")

    def run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def write_evidence(self, source_head: str) -> None:
        self.write(
            "docs/webmcp-challenge/E2E_EVIDENCE.md",
            f"# Evidence\n\nRuntime source HEAD `{source_head}` passed.\n",
        )

    def verify(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_document_only_commits_after_evidence_source_are_allowed(self) -> None:
        self.write("README.md", "# Simverse\n\nDocs only.\n")
        self.run_git("add", ".")
        self.run_git("commit", "-qm", "docs")

        completed = self.verify()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("challenge_e2e_evidence_head=PASS", completed.stdout)

    def test_runtime_change_after_evidence_source_is_rejected(self) -> None:
        self.write("frontend/src/pages/ChallengePage.tsx", "export const version = 2\n")
        self.run_git("add", ".")
        self.run_git("commit", "-qm", "runtime drift")

        completed = self.verify()

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("frontend/src/pages/ChallengePage.tsx", completed.stderr)

    def test_missing_or_unresolvable_source_head_is_rejected(self) -> None:
        self.write_evidence("f" * 40)

        completed = self.verify()

        self.assertNotEqual(completed.returncode, 0)
        self.assertTrue(completed.stderr.strip())


if __name__ == "__main__":
    unittest.main()
