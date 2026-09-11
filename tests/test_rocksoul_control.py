from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from g4f.rocksoul_control import ProviderControlStore
from g4f.rocksoul_db import RocksoulDB
from g4f.rocksoul_intelligence import ExplainableRouter, RecoveryManager


class RocksoulControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = RocksoulDB(Path(self.tmp.name) / "rocksoul.db")
        for name in ("A", "B"):
            self.db.upsert_provider(name, "https://example.test", True, True, False)
            self.db.bind_model(name, "demo", verified=True)
            self.db.record_probe(name, "smoke", True, 10.0)
        self.control = ProviderControlStore(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_rate_limit_cooldown_blocks_until_expiry(self) -> None:
        self.control.cooldown("A", 30, "rate_limit")
        state = self.control.get("A")
        self.assertEqual(state.state, "DEGRADED")
        self.assertTrue(state.blocked)
        candidates = ExplainableRouter(self.db).explain("demo")
        self.assertEqual([item["provider"] for item in candidates], ["B"])

    def test_quarantine_and_recovery_state_machine(self) -> None:
        self.control.quarantine("A", "manual")
        self.assertEqual(self.control.get("A").state, "QUARANTINED")
        self.assertEqual(RecoveryManager(self.db).quarantined(), ["A"])
        self.control.begin_recovery("A")
        self.assertEqual(self.control.get("A").state, "PROBING")
        self.control.re_admit("A")
        self.assertEqual(self.control.get("A").state, "RE_ADMITTED")
        self.assertIn("QUARANTINED", {event["to_state"] for event in self.control.history("A")})

    def test_expired_cooldown_re_admits_active(self) -> None:
        with patch("g4f.rocksoul_control.time.time", side_effect=[100.0, 100.0, 101.0, 102.0, 102.0]):
            self.control.cooldown("A", 1.0)
            with patch("g4f.rocksoul_control.time.time", return_value=102.0):
                self.assertEqual(self.control.get("A").state, "ACTIVE")


if __name__ == "__main__":
    unittest.main()
