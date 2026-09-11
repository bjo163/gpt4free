from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RocksoulCliContractTests(unittest.TestCase):
    def run_cli(self, *args: str, root: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["LOCALAPPDATA"] = root
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [sys.executable, "-m", "g4f.rocksoul_db_cli", *args],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=Path(__file__).resolve().parents[1],
        )

    def test_help_contains_product_commands(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = self.run_cli("--help", root=root)
        self.assertEqual(result.returncode, 0)
        for command in ("status", "route", "route-explain", "execute", "trace", "quarantine", "recover"):
            self.assertIn(command, result.stdout)

    def test_quarantine_and_status_are_offline(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            quarantined = self.run_cli("quarantine", "SyntheticProvider", "--reason", "contract-test", root=root)
            self.assertEqual(quarantined.returncode, 0, quarantined.stderr)
            payload = json.loads(quarantined.stdout)
            self.assertEqual(payload["state"], "QUARANTINED")

            status = self.run_cli("status", root=root)
            self.assertEqual(status.returncode, 0, status.stderr)
            payload = json.loads(status.stdout)
            self.assertIn("provider_states", payload)
            state = next(item for item in payload["provider_states"] if item["provider"] == "SyntheticProvider")
            self.assertEqual(state["state"], "QUARANTINED")

    def test_route_explain_is_offline_without_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = self.run_cli("route-explain", "synthetic-model", root=root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])


if __name__ == "__main__":
    unittest.main()
