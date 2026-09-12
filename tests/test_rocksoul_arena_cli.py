from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from g4f.rocksoul_arena_cli import main


class RocksoulArenaCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "rocksoul.db")

    def invoke(self, *args: str) -> tuple[int, object]:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--db", self.db, *args])
        return code, json.loads(output.getvalue())

    def test_status_contract(self):
        code, payload = self.invoke("status")
        self.assertEqual(code, 0)
        self.assertEqual(payload["phase"], "F5")
        self.assertEqual(payload["authority"], "rocksoul_arena")

    def test_fixture_run_and_leaderboard(self):
        code, perfect = self.invoke("fixture", "--target", "perfect")
        self.assertEqual(code, 0)
        self.assertEqual(perfect["score"], 100.0)
        self.assertEqual(perfect["passed"], 3)

        code, mixed = self.invoke("fixture", "--target", "mixed")
        self.assertEqual(code, 0)
        self.assertLess(mixed["score"], perfect["score"])

        code, board = self.invoke("leaderboard")
        self.assertEqual(code, 0)
        self.assertEqual([item["target"] for item in board], ["perfect", "mixed"])

    def test_show_unknown_run_is_explicit(self):
        code, payload = self.invoke("show", "missing")
        self.assertEqual(code, 3)
        self.assertEqual(payload["error"], "run_not_found")

    def test_fixture_manifest_is_stable(self):
        code, first = self.invoke("fixture-manifest")
        self.assertEqual(code, 0)
        code, second = self.invoke("fixture-manifest")
        self.assertEqual(code, 0)
        self.assertEqual(first["digest"], second["digest"])


if __name__ == "__main__":
    unittest.main()
