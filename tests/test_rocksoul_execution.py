from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from g4f.rocksoul_db import RocksoulDB
from g4f.rocksoul_execution import ExecutionEngine, ExecutionRequest
from g4f.rocksoul_policy import ErrorClass, ExecutionPolicy, RetryAction


class FakeCompletions:
    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self.failures = failures or {}
        self.calls: list[str] = []

    def create(self, *, provider: str, **kwargs):
        self.calls.append(provider)
        error = self.failures.get(provider)
        if error is not None:
            raise error
        return {"provider": provider, "content": "ok"}


class FakeChat:
    def __init__(self, completions: FakeCompletions) -> None:
        self.completions = completions


class FakeClient:
    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self.chat = FakeChat(FakeCompletions(failures))


class RocksoulExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = RocksoulDB(Path(self.tmp.name) / "rocksoul.db")
        for name, verified in (("A", True), ("B", True), ("C", False)):
            self.db.upsert_provider(name, "https://example.test", True, True, False)
            self.db.bind_model(name, "demo", verified=verified)
            self.db.record_probe(name, "smoke", True, 10.0 if name == "A" else 20.0)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fallback_executes_next_provider_and_persists_attempts(self) -> None:
        client = FakeClient({"A": TimeoutError("timed out")})
        engine = ExecutionEngine(self.db, client)
        result = engine.execute(ExecutionRequest(model="demo", messages=[{"role": "user", "content": "hi"}], max_attempts=2))
        self.assertTrue(result.ok)
        self.assertEqual(result.provider, "B")
        self.assertEqual([item.provider for item in result.attempts], ["A", "B"])
        trace = engine.trace.trace(result.request_id)
        self.assertEqual(trace["attempt_count"], 2)
        self.assertEqual([row["status"] for row in trace["attempts"]], ["failed", "success"])

    def test_execution_persists_route_decision(self) -> None:
        engine = ExecutionEngine(self.db, FakeClient())
        result = engine.execute(ExecutionRequest(model="demo", messages="hello"))
        self.assertTrue(result.ok)
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT selected_provider_id, candidates_json, reason_json FROM route_decisions ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["selected_provider_id"], self.db.provider_id("A"))
        self.assertIn("A", row["candidates_json"])
        self.assertIn("health_score", row["reason_json"])

    def test_success_stops_after_first_provider(self) -> None:
        client = FakeClient()
        engine = ExecutionEngine(self.db, client)
        result = engine.execute(ExecutionRequest(model="demo", messages="hello"))
        self.assertTrue(result.ok)
        self.assertEqual(client.chat.completions.calls, ["A"])

    def test_policy_taxonomy(self) -> None:
        decision = ExecutionPolicy.decide(RuntimeError("429 rate limit exceeded"))
        self.assertEqual(decision.error_class, ErrorClass.RATE_LIMIT)
        self.assertEqual(decision.action, RetryAction.COOLDOWN_NEXT_PROVIDER)
        decision = ExecutionPolicy.decide(RuntimeError("content blocked by safety policy"))
        self.assertEqual(decision.action, RetryAction.TERMINAL)

    def test_backoff_is_bounded_and_timeout_is_immediate(self) -> None:
        rate_limit = ExecutionPolicy.decide(RuntimeError("429 rate limit exceeded"))
        self.assertEqual(ExecutionPolicy.backoff_seconds(rate_limit, 0, maximum=8.0), 8.0)
        network = ExecutionPolicy.decide(ConnectionError("network down"))
        self.assertEqual(ExecutionPolicy.backoff_seconds(network, 2, base=0.5, maximum=8.0), 2.0)
        timeout = ExecutionPolicy.decide(TimeoutError("timed out"))
        self.assertEqual(ExecutionPolicy.backoff_seconds(timeout, 2), 0.0)

    def test_provider_enters_cooldown_after_failure_streak(self) -> None:
        for _ in range(3):
            self.db.record_probe("A", "execution", False, 5.0, error_class="network", error="down")
        health = self.db.health("A")
        self.assertGreater(health.cooldown_until, 0.0)
        self.assertEqual(self.db.route_candidates("demo")[0].provider, "B")

    def test_total_time_budget_stops_fallback(self) -> None:
        client = FakeClient({"A": ConnectionError("network down")})
        engine = ExecutionEngine(self.db, client)
        result = engine.execute(
            ExecutionRequest(
                model="demo",
                messages=[],
                max_attempts=3,
                max_total_time=0.000001,
            )
        )
        self.assertFalse(result.ok)
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(client.chat.completions.calls, ["A"])

    def test_request_identity_is_unique(self) -> None:
        a = ExecutionRequest(model="demo", messages=[])
        b = ExecutionRequest(model="demo", messages=[])
        self.assertNotEqual(a.request_id, b.request_id)


if __name__ == "__main__":
    unittest.main()
