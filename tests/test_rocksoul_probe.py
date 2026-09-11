from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from g4f.rocksoul_db import RocksoulDB
from g4f.rocksoul_probe import LiveProbe, ResponseValidator, result_summary


class FakeCompletion:
    content = "ROCKSOUL_PROBE_OK"
    tool_calls = None


class FakeCompletions:
    def __init__(self, stream: list[object] | None = None) -> None:
        self.stream = stream or []

    def create(self, **kwargs):
        if kwargs.get("stream"):
            return iter(self.stream or [FakeCompletion()])
        return FakeCompletion()


class FakeClient:
    def __init__(self, stream: list[object] | None = None) -> None:
        self.chat = type("Chat", (), {"completions": FakeCompletions(stream)})()


class RocksoulProbeTests(unittest.TestCase):
    def test_response_validator(self) -> None:
        self.assertTrue(ResponseValidator.chat(FakeCompletion()))
        self.assertTrue(ResponseValidator.chat(object(), stream=True))
        self.assertFalse(ResponseValidator.chat(None))

    def test_probe_persists_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = RocksoulDB(Path(tmp) / "rocksoul.db")
            probe = LiveProbe(db)
            result = probe.probe(
                "Synthetic",
                "synthetic-model",
                client_factory=lambda _provider: FakeClient(),
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.error, None)
            health = db.health("Synthetic")
            self.assertEqual(health.attempts, 1)
            self.assertEqual(health.successes, 1)
            self.assertEqual(health.failures, 0)

    def test_probe_persists_failure(self) -> None:
        class BrokenClient:
            class Chat:
                class Completions:
                    def create(self, **kwargs):
                        del kwargs
                        raise TimeoutError("probe timeout")

                completions = Completions()

            chat = Chat()

        with tempfile.TemporaryDirectory() as tmp:
            db = RocksoulDB(Path(tmp) / "rocksoul.db")
            result = LiveProbe(db).probe(
                "Broken",
                "synthetic-model",
                client_factory=lambda _provider: BrokenClient(),
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.error_class, "timeout")
            health = db.health("Broken")
            self.assertEqual(health.failures, 1)
            self.assertEqual(health.last_error_class, "timeout")

    def test_stream_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = RocksoulDB(Path(tmp) / "rocksoul.db")
            result = LiveProbe(db).probe(
                "Synthetic",
                "synthetic-model",
                probe_type="stream",
                client_factory=lambda _provider: FakeClient([FakeCompletion(), FakeCompletion()]),
            )
            self.assertTrue(result.ok)
            self.assertTrue(result.response_valid)

    def test_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = RocksoulDB(Path(tmp) / "rocksoul.db")
            live = LiveProbe(db)
            result = live.probe(
                "Synthetic",
                "synthetic-model",
                client_factory=lambda _provider: FakeClient(),
            )
            summary = result_summary([result])
            self.assertEqual(summary["tests"], 1)
            self.assertEqual(summary["passed"], 1)
            self.assertEqual(summary["success_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
