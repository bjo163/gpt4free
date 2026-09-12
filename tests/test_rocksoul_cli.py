from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from g4f.rocksoul_db import RocksoulDB


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

    def test_route_verified_only_is_preserved_with_capability_filter(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "ROCKSOUL" / "g4f" / "rocksoul.db"
            db = RocksoulDB(db_path)

            db.upsert_provider("UnverifiedFast", "https://example.test", True, True, False)
            db.bind_model("UnverifiedFast", "demo", verified=False)
            db.set_capability("UnverifiedFast", "streaming", True, True, True, model="demo")
            db.record_probe("UnverifiedFast", "smoke", True, 1.0, model="demo")

            db.upsert_provider("VerifiedSlower", "https://example.test", True, True, False)
            db.bind_model("VerifiedSlower", "demo", verified=True)
            db.set_capability("VerifiedSlower", "streaming", True, True, True, model="demo")
            db.record_probe("VerifiedSlower", "smoke", True, 50.0, model="demo")
            db.record_probe("VerifiedSlower", "execution", False, 50.0, model="demo", error_class="network", error="synthetic-1")
            db.record_probe("VerifiedSlower", "execution", False, 50.0, model="demo", error_class="network", error="synthetic-2")

            unrestricted = self.run_cli("route", "demo", "--streaming", root=root)
            self.assertEqual(unrestricted.returncode, 0, unrestricted.stderr)
            self.assertEqual(json.loads(unrestricted.stdout)["provider"], "UnverifiedFast")

            verified_only = self.run_cli("route", "demo", "--streaming", "--verified-only", root=root)
            self.assertEqual(verified_only.returncode, 0, verified_only.stderr)
            payload = json.loads(verified_only.stdout)
            self.assertEqual(payload["provider"], "VerifiedSlower")
            self.assertTrue(payload["model_verified"])


if __name__ == "__main__":
    unittest.main()
