#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


SPEC = (
    Path(__file__).resolve().parents[1]
    / "frontend/e2e/challenge-benchmark.spec.ts"
)


class ChallengeBenchmarkDomOrderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SPEC.read_text(encoding="utf-8")

    def assert_source_order(self, earlier: str, later: str) -> None:
        earlier_index = self.source.find(earlier)
        later_index = self.source.find(later)
        self.assertNotEqual(earlier_index, -1, f"missing source marker: {earlier}")
        self.assertNotEqual(later_index, -1, f"missing source marker: {later}")
        self.assertLess(
            earlier_index,
            later_index,
            f"expected real DOM action before telemetry: {earlier} -> {later}",
        )

    def test_ordinary_lifecycle_events_follow_real_dom_actions(self) -> None:
        self.assert_source_order(
            "page.getByRole('button', { name: 'Investigate Harbor crisis' }).click()",
            "recordTelemetry(page, 'crisis_identified', { clicks: 1 })",
        )
        self.assert_source_order(
            "page.getByRole('button', { name: 'Preview intervention' }).click()",
            "recordTelemetry(page, 'preview_requested', { clicks: 1 })",
        )
        self.assert_source_order(
            ").check()",
            "recordTelemetry(page, 'approval_granted', { clicks: 2 })",
        )
        self.assert_source_order(
            "page.getByRole('button', { name: 'Create one-time approval' }).click()",
            "recordTelemetry(page, 'approval_granted', { clicks: 2 })",
        )
        self.assert_source_order(
            "page.getByRole('button', { name: 'Commit approved intervention' }).click()",
            "recordTelemetry(page, 'commit_attempted', { clicks: 1 })",
        )
        self.assert_source_order(
            "page.getByRole('button', { name: 'Verify 72-hour outcome' }).click()",
            "recordTelemetry(page, 'verification_started', { clicks: 1 })",
        )


if __name__ == "__main__":
    unittest.main()
