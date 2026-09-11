from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from g4f.rocksoul_db import RocksoulDB


class RocksoulDBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = RocksoulDB(Path(self.tmp.name) / "rocksoul.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_schema_and_provider_model_binding(self) -> None:
        self.db.upsert_provider("Synthetic", "https://example.test", True, True, False)
        self.db.bind_model("Synthetic", "synthetic-model", verified=True)
        with self.db.connect() as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            binding = conn.execute(
                "SELECT pm.verified FROM provider_models pm JOIN providers p ON p.id=pm.provider_id JOIN models m ON m.id=pm.model_id WHERE p.name=? AND m.name=?",
                ("Synthetic", "synthetic-model"),
            ).fetchone()
        self.assertIn("providers", tables)
        self.assertIn("probe_runs", tables)
        self.assertEqual(binding[0], 1)

    def test_probe_updates_health_and_latency(self) -> None:
        self.db.upsert_provider("Synthetic", "https://example.test", True, True, False)
        self.db.record_probe("Synthetic", "smoke", True, 120.0, "synthetic-model", response_valid=True)
        self.db.record_probe("Synthetic", "smoke", True, 80.0, "synthetic-model", response_valid=True)
        health = self.db.health("Synthetic")
        self.assertEqual(health.attempts, 2)
        self.assertEqual(health.successes, 2)
        self.assertEqual(health.failures, 0)
        self.assertEqual(health.avg_latency_ms, 100.0)
        self.assertGreater(health.score, 70.0)

    def test_failure_streak_enters_cooldown(self) -> None:
        self.db.upsert_provider("Synthetic", "https://example.test", True, True, False)
        for _ in range(3):
            self.db.record_probe("Synthetic", "smoke", False, error_class="timeout", error="timed out")
        health = self.db.health("Synthetic")
        self.assertEqual(health.consecutive_failures, 3)
        self.assertGreater(health.cooldown_until, 0.0)

    def test_route_candidates_use_verified_model(self) -> None:
        self.db.upsert_provider("Slow", "https://slow.test", True, True, False)
        self.db.upsert_provider("Fast", "https://fast.test", True, True, False)
        self.db.bind_model("Slow", "demo-model", verified=False)
        self.db.bind_model("Fast", "demo-model", verified=True)
        self.db.record_probe("Slow", "smoke", True, 900.0)
        self.db.record_probe("Fast", "smoke", True, 100.0)
        candidates = self.db.route_candidates("demo-model")
        self.assertEqual(candidates[0].provider, "Fast")
        self.assertTrue(candidates[0].model_verified)
        self.assertTrue(self.db.route_candidates("demo-model", verified_only=True)[0].model_verified)

    def test_route_decision_is_persisted(self) -> None:
        self.db.upsert_provider("Synthetic", "https://example.test", True, True, False)
        self.db.bind_model("Synthetic", "demo-model", verified=True)
        candidates = self.db.route_candidates("demo-model")
        self.db.record_route("demo-model", candidates, "Synthetic", ["model_verified", "health_score"])
        with self.db.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM route_decisions").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
