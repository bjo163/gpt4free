from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from g4f.rocksoul_platform import (
    AdaptiveRouter,
    Arena,
    CapabilitySet,
    HealthStore,
    MeshNode,
    MeshRegistry,
    ProviderRecord,
    ProviderRegistry,
    SecurityPolicy,
    normalize_tool_calls,
)


class RocksoulPlatformTests(unittest.TestCase):
    def test_normalize_tool_calls_accepts_object_arguments(self) -> None:
        calls = normalize_tool_calls([
            {"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": {"q": "rocksoul"}}},
            {"function": {"name": "next"}},
        ])
        self.assertEqual(calls[0].arguments, '{"q":"rocksoul"}')
        self.assertEqual(calls[0].index, 0)
        self.assertEqual(calls[1].index, 1)
        self.assertTrue(calls[1].id.startswith("call_"))

    def test_security_policy_blocks_loopback(self) -> None:
        policy = SecurityPolicy()
        with self.assertRaises(PermissionError):
            policy.validate_url("http://127.0.0.1:8080/")

    def test_health_persistence_and_score(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "health.json"
            store = HealthStore(path)
            store.record_success("A", 100)
            store.record_success("A", 200)
            self.assertEqual(store.get("A").success_rate, 1.0)
            restored = HealthStore(path)
            self.assertEqual(restored.get("A").attempts, 2)
            self.assertGreater(restored.get("A").score, 80)

    def test_router_filters_capabilities(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            registry = ProviderRegistry(root / "registry.json")
            registry.providers = {
                "vision": ProviderRecord("vision", working=True, url="https://vision", capabilities=CapabilitySet(vision=True, tools=True), active_by_default=True),
                "text": ProviderRecord("text", working=True, url="https://text", capabilities=CapabilitySet(vision=False, tools=False), active_by_default=True),
            }
            router = AdaptiveRouter(registry, HealthStore(root / "health.json"))
            self.assertEqual(router.rank("model", {"vision": True}), ["vision"])

    def test_mesh_selects_best_node(self) -> None:
        with TemporaryDirectory() as directory:
            mesh = MeshRegistry(Path(directory) / "mesh.json")
            mesh.add(MeshNode("a", "http://a", CapabilitySet(tools=True), health=80, latency_ms=100))
            mesh.add(MeshNode("b", "http://b", CapabilitySet(tools=True), health=70, latency_ms=10))
            self.assertEqual(mesh.select({"tools": True}).node_id, "a")

    def test_arena_summary(self) -> None:
        def bad() -> None:
            raise ValueError("x")
        results = Arena().run({"ok": lambda: None, "bad": bad})
        summary = Arena.summarize(results)
        self.assertEqual(summary["tests"], 2)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["failed"], 1)


if __name__ == "__main__":
    unittest.main()
