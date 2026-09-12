from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from g4f.rocksoul_arena import (
    ArenaCase,
    ArenaStore,
    ArenaSuite,
    ArenaValidationError,
)
from g4f.rocksoul_db import RocksoulDB


class RocksoulArenaTests(unittest.TestCase):
    def make_store(self) -> ArenaStore:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return ArenaStore(RocksoulDB(Path(temp.name) / "rocksoul.db"))

    def suite(self, *, cases=None, version="1") -> ArenaSuite:
        return ArenaSuite(
            name="unit-suite",
            version=version,
            evaluator="json_exact",
            provenance={"source": "unit-test", "network": False},
            cases=tuple(cases or (
                ArenaCase("a", {"v": 1}, {"answer": 1}),
                ArenaCase("b", {"v": 2}, {"answer": 2}, weight=2.0),
            )),
        )

    def test_manifest_digest_is_stable_across_case_input_order(self):
        first = self.suite(cases=(
            ArenaCase("b", {"v": 2}, {"answer": 2}),
            ArenaCase("a", {"v": 1}, {"answer": 1}),
        ))
        second = self.suite(cases=(
            ArenaCase("a", {"v": 1}, {"answer": 1}),
            ArenaCase("b", {"v": 2}, {"answer": 2}),
        ))
        self.assertEqual(first.digest, second.digest)

    def test_suite_version_is_immutable_for_different_content(self):
        store = self.make_store()
        store.register_suite(self.suite())
        changed = self.suite(cases=(ArenaCase("a", {"v": 1}, {"answer": 99}),))
        with self.assertRaises(ArenaValidationError):
            store.register_suite(changed)

    def test_weighted_correctness_is_deterministic_and_latency_is_evidence_only(self):
        store = self.make_store()
        suite = self.suite()

        def execute(case: ArenaCase):
            return {"answer": 1 if case.case_id == "a" else -1}

        run = store.run(suite, "target-a", execute)
        self.assertEqual(run.passed, 1)
        self.assertEqual(run.failed, 1)
        self.assertAlmostEqual(run.score, 100.0 / 3.0)
        self.assertTrue(all(item.latency_ms >= 0.0 for item in run.results))

    def test_execution_failure_is_captured_without_aborting_run(self):
        store = self.make_store()
        suite = self.suite()

        def execute(case: ArenaCase):
            if case.case_id == "a":
                raise RuntimeError("boom")
            return {"answer": 2}

        run = store.run(suite, "target-failure", execute)
        self.assertEqual(run.total, 2)
        self.assertEqual(run.passed, 1)
        self.assertIn("RuntimeError: boom", run.results[0].error or "")
        stored = store.get_run(run.run_id)
        self.assertIsNotNone(stored)
        self.assertEqual(len(stored["results"]), 2)

    def test_leaderboard_uses_latest_run_per_target_and_stable_tie_break(self):
        store = self.make_store()
        suite = self.suite()

        store.run(suite, "zeta", lambda case: case.expected)
        store.run(suite, "alpha", lambda case: case.expected)
        board = store.leaderboard(suite.digest)
        self.assertEqual([item["target"] for item in board], ["alpha", "zeta"])
        self.assertEqual([item["rank"] for item in board], [1, 2])

    def test_status_declares_canonical_foundation_boundary(self):
        status = self.make_store().status()
        self.assertEqual(status["phase"], "F5")
        self.assertEqual(status["authority"], "rocksoul_arena")
        self.assertEqual(status["legacy_arena"], "compatibility-only")
        self.assertEqual(status["latency_role"], "evidence-only")


if __name__ == "__main__":
    unittest.main()
