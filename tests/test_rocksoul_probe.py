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
        self.last_kwargs: dict[str, object] = {}

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if kwargs.get("stream"):
            return iter(self.stream or [FakeCompletion()])
        return FakeCompletion()


class FakeClient:
    def __init__(self, stream: list[object] | None = None) -> None:
        self.completions = FakeCompletions(stream)
        self.chat = type("Chat", (), {"completions": self.completions})()


class RocksoulProbeTests(unittest.TestCase):
    def test_response_validator(self) -> None:
        self.assertTrue(ResponseValidator.chat(FakeCompletion()))
        self.assertTrue(ResponseValidator.chat([FakeCompletion()], stream=True))
        self.assertFalse(ResponseValidator.chat([], stream=True))
        self.assertFalse(ResponseValidator.chat(None))

    def test_probe_persists_success_and_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = RocksoulDB(Path(tmp) / "rocksoul.db")
            client = FakeClient()
            probe = LiveProbe(db)
            result = probe.probe(
                "Synthetic",
                "synthetic-model",
                timeout=7,
                client_factory=lambda _provider: client,
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.error, None)
            self.assertEqual(client.completions.last_kwargs["timeout"], 7.0)
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
            client = FakeClient([FakeCompletion(), FakeCompletion()])
            result = LiveProbe(db).probe(
                "Synthetic",
                "synthetic-model",
                probe_type="stream",
                timeout=3,
                client_factory=lambda _provider: client,
            )
            self.assertTrue(result.ok)
            self.assertTrue(result.response_valid)
            self.assertEqual(client.completions.last_kwargs["stream"], True)
            self.assertEqual(client.completions.last_kwargs["timeout"], 3.0)

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
