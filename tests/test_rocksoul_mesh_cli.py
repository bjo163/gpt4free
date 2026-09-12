from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from g4f.rocksoul_mesh_cli import main


class RocksoulMeshCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "rocksoul.db")

    def run_cli(self, *args: str, env: dict[str, str] | None = None) -> tuple[int, object]:
        output = io.StringIO()
        patch_env = {
            "ROCKSOUL_MESH_SECRET": "",
            "ROCKSOUL_MESH_KEYS_JSON": "",
            "ROCKSOUL_MESH_ALLOW_INSECURE_LOCAL": "",
        }
        patch_env.update(env or {})
        with patch.dict(os.environ, patch_env, clear=False), redirect_stdout(output):
            code = main(["--db", self.db, "--allow-insecure-local", *args])
        return code, json.loads(output.getvalue())

    def test_operator_flow_register_heartbeat_select_lease_release(self):
        code, registered = self.run_cli(
            "register", "node-a", "http://127.0.0.1:9001",
            "--capability", "streaming",
        )
        self.assertEqual(code, 0)
        self.assertEqual(registered["state"], "REGISTERED")

        code, heartbeat = self.run_cli(
            "heartbeat", "node-a", "--latency-ms", "10",
            env={"ROCKSOUL_MESH_SECRET": "mesh-secret"},
        )
        self.assertEqual(code, 0)
        self.assertEqual(heartbeat["state"], "ACTIVE")

        code, selected = self.run_cli("select", "--capability", "streaming")
        self.assertEqual(code, 0)
        self.assertEqual(selected["selected"]["node_id"], "node-a")

        code, leased = self.run_cli("lease", "req-1", "--capability", "streaming")
        self.assertEqual(code, 0)
        lease_id = leased["lease"]["lease_id"]

        code, released = self.run_cli("release", lease_id, "--success", "--latency-ms", "12")
        self.assertEqual(code, 0)
        self.assertEqual(released["lease"]["status"], "SUCCEEDED")

    def test_missing_secret_fails_authenticated_heartbeat_without_leaking_secret(self):
        self.run_cli("register", "node-a", "http://127.0.0.1:9001")
        code, value = self.run_cli("heartbeat", "node-a")
        self.assertEqual(code, 2)
        self.assertFalse(value["ok"])
        self.assertIn("no mesh secret configured", value["error"])

    def test_state_events_and_status_are_json_contracts(self):
        self.run_cli("register", "node-a", "http://127.0.0.1:9001")
        code, state = self.run_cli("state", "node-a", "DRAINING", "--reason", "maintenance")
        self.assertEqual(code, 0)
        self.assertEqual(state["state"], "DRAINING")
        code, events = self.run_cli("events", "--node", "node-a")
        self.assertEqual(code, 0)
        self.assertTrue(any(item["event"] == "state_changed" for item in events))
        code, status = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertEqual(status["states"]["DRAINING"], 1)


if __name__ == "__main__":
    unittest.main()
