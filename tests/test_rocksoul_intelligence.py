from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from g4f.rocksoul_db import RocksoulDB
from g4f.rocksoul_intelligence import CapabilityRequirement, CapabilityVerifier, ExplainableRouter, RecoveryManager


class FakeResult:
    content = "ROCKSOUL_CAPABILITY_OK"
    tool_calls = [{"id": "call_1"}]


class FakeCompletions:
    def create(self, **kwargs):
        del kwargs
        return FakeResult()


class FakeImages:
    def generate(self, **kwargs):
        del kwargs
        return {"data": [{"url": "https://example.test/image"}]}


class FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions())
        self.images = FakeImages()


class IntelligenceTests(unittest.TestCase):
    def make_db(self) -> tuple[tempfile.TemporaryDirectory[str], RocksoulDB]:
        tmp = tempfile.TemporaryDirectory()
        return tmp, RocksoulDB(Path(tmp.name) / "rocksoul.db")

    def test_capability_verifier_persists_verified_tools(self) -> None:
        tmp, db = self.make_db()
        try:
            verifier = CapabilityVerifier(db)
            verifier._provider = lambda _name: object()
            verifier._client = lambda _provider: FakeClient()
            result = verifier.verify("Synthetic", "demo", "tools")
            self.assertTrue(result.ok)
            with db.connect() as conn:
                row = conn.execute("SELECT detected, verified FROM capabilities WHERE name='tools'").fetchone()
            self.assertEqual(row[0], 1)
            self.assertEqual(row[1], 1)
        finally:
            tmp.cleanup()

    def test_explain_router_rejects_unverified_capability(self) -> None:
        tmp, db = self.make_db()
        try:
            db.upsert_provider("ProviderA", active_by_default=True)
            db.bind_model("ProviderA", "demo", verified=True)
            db.set_capability("ProviderA", "vision", True, False, False, model="demo")
            output = ExplainableRouter(db).explain("demo", [CapabilityRequirement("vision")])
            self.assertEqual(len(output), 1)
            self.assertFalse(output[0]["accepted"])
            self.assertIn("DECLARED", output[0]["capabilities"]["vision"])
        finally:
            tmp.cleanup()

    def test_explain_router_accepts_verified_capability(self) -> None:
        tmp, db = self.make_db()
        try:
            db.upsert_provider("ProviderA", active_by_default=True)
            db.bind_model("ProviderA", "demo", verified=True)
            db.set_capability("ProviderA", "vision", True, True, True, model="demo")
            selected = ExplainableRouter(db).select("demo", [CapabilityRequirement("vision")])
            self.assertIsNotNone(selected)
            self.assertEqual(selected["provider"], "ProviderA")
        finally:
            tmp.cleanup()

    def test_recovery_targets_three_failure_streak(self) -> None:
        tmp, db = self.make_db()
        try:
            db.upsert_provider("Broken")
            for _ in range(3):
                db.record_probe("Broken", "smoke", False, error_class="timeout", error="timed out")
            self.assertEqual(RecoveryManager(db).quarantined(), ["Broken"])
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
