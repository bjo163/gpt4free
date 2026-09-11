from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_normalize_tool_calls_accepts_object_arguments() -> None:
    calls = normalize_tool_calls([
        {"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": {"q": "rocksoul"}}},
        {"function": {"name": "next"}},
    ])
    assert calls[0].arguments == '{"q":"rocksoul"}'
    assert calls[0].index == 0
    assert calls[1].index == 1
    assert calls[1].id.startswith("call_")


def test_security_policy_blocks_loopback() -> None:
    policy = SecurityPolicy()
    with pytest.raises(PermissionError):
        policy.validate_url("http://127.0.0.1:8080/")


def test_health_persistence_and_score(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    store = HealthStore(path)
    store.record_success("A", 100)
    store.record_success("A", 200)
    assert store.get("A").success_rate == 1.0
    restored = HealthStore(path)
    assert restored.get("A").attempts == 2
    assert restored.get("A").score > 80


def test_router_filters_capabilities(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "registry.json")
    registry.providers = {
        "vision": ProviderRecord("vision", capabilities=CapabilitySet(vision=True, tools=True), active_by_default=True),
        "text": ProviderRecord("text", capabilities=CapabilitySet(vision=False, tools=False), active_by_default=True),
    }
    router = AdaptiveRouter(registry, HealthStore(tmp_path / "health.json"))
    assert router.rank("model", {"vision": True}) == ["vision"]


def test_mesh_selects_best_capability_match(tmp_path: Path) -> None:
    mesh = MeshRegistry(tmp_path / "mesh.json")
    mesh.add(MeshNode("a", "http://a", CapabilitySet(tools=True), health=80, latency_ms=100))
    mesh.add(MeshNode("b", "http://b", CapabilitySet(tools=True), health=70, latency_ms=10))
    assert mesh.select({"tools": True}).node_id == "a"


def test_arena_summary() -> None:
    results = Arena().run({"ok": lambda: None, "bad": lambda: (_ for _ in ()).throw(ValueError("x"))})
    summary = Arena.summarize(results)
    assert summary["tests"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
