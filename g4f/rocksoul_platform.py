from __future__ import annotations

"""ROCKSOUL intelligence/platform overlay for g4f.

Non-invasive additions around the existing provider/client architecture:
provider health, capability-aware routing, tool-call normalization, benchmark
arena, security policy, media persistence, node mesh, and a small agent runtime.
All state is persisted as JSON and the module uses only the Python standard
library beyond g4f itself.
"""

import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
import socket
import statistics
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlparse


ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ROCKSOUL" / "g4f"
STATE_DIR = ROOT / "intelligence"
HEALTH_FILE = STATE_DIR / "health.json"
REGISTRY_FILE = STATE_DIR / "registry.json"
MESH_FILE = STATE_DIR / "mesh.json"
MEDIA_DIR = ROOT / "media"


class ProviderCategory:
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    MODEL_NOT_FOUND = "model_not_found"
    UNSUPPORTED = "unsupported"
    CONTENT_BLOCKED = "content_blocked"
    INVALID_RESPONSE = "invalid_response"
    PROVIDER_DOWN = "provider_down"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class CapabilitySet:
    text: bool = True
    streaming: bool | None = None
    vision: bool | None = None
    tools: bool | None = None
    structured_output: bool | None = None
    image: bool | None = None
    audio: bool | None = None
    video: bool | None = None
    web_search: bool | None = None

    def satisfies(self, required: Mapping[str, bool]) -> bool:
        for key, value in required.items():
            if not value:
                continue
            if getattr(self, key, None) is not True:
                return False
        return True


@dataclass(slots=True)
class ProviderRecord:
    name: str
    url: str | None = None
    working: bool | None = None
    active_by_default: bool | None = None
    needs_auth: bool = False
    capabilities: CapabilitySet = field(default_factory=CapabilitySet)
    models: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HealthRecord:
    provider: str
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    last_latency_ms: float | None = None
    last_error: str | None = None
    last_error_class: str | None = None
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    updated_at: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.5

    @property
    def avg_latency_ms(self) -> float | None:
        return self.total_latency_ms / self.successes if self.successes else None

    @property
    def score(self) -> float:
        reliability = self.success_rate * 70.0
        latency = 20.0 if self.avg_latency_ms is None else max(0.0, 20.0 - min(self.avg_latency_ms / 250.0, 20.0))
        penalty = min(self.consecutive_failures * 5.0, 25.0)
        return max(0.0, min(100.0, reliability + latency - penalty))


@dataclass(slots=True)
class ModelBinding:
    model: str
    provider: str
    capabilities: CapabilitySet = field(default_factory=CapabilitySet)
    verified: bool = False
    verified_at: float | None = None


class JsonStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self, default: Any) -> Any:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def save(self, value: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)


class HealthStore:
    def __init__(self, path: Path = HEALTH_FILE) -> None:
        self.store = JsonStore(path)
        self.records: dict[str, HealthRecord] = {}
        raw = self.store.load({})
        for name, value in raw.items():
            try:
                self.records[name] = HealthRecord(**value)
            except (TypeError, ValueError):
                continue

    def get(self, provider: str) -> HealthRecord:
        return self.records.setdefault(provider, HealthRecord(provider=provider))

    def available(self, provider: str) -> bool:
        return self.get(provider).cooldown_until <= time.time()

    def record_success(self, provider: str, latency_ms: float) -> HealthRecord:
        item = self.get(provider)
        item.attempts += 1
        item.successes += 1
        item.total_latency_ms += max(0.0, latency_ms)
        item.last_latency_ms = latency_ms
        item.last_error = None
        item.last_error_class = None
        item.consecutive_failures = 0
        item.cooldown_until = 0.0
        item.updated_at = time.time()
        self.persist()
        return item

    def record_failure(self, provider: str, exc: BaseException, cooldown: float | None = None) -> HealthRecord:
        item = self.get(provider)
        item.attempts += 1
        item.failures += 1
        item.consecutive_failures += 1
        item.last_error = str(exc)
        item.last_error_class = classify_error(exc)
        if cooldown is None and item.consecutive_failures >= 3:
            cooldown = min(60.0 * (2 ** min(item.consecutive_failures - 3, 3)), 900.0)
        if cooldown:
            item.cooldown_until = time.time() + cooldown
        item.updated_at = time.time()
        self.persist()
        return item

    def persist(self) -> None:
        self.store.save({name: asdict(item) for name, item in self.records.items()})


class ProviderCircuit:
    def __init__(self, failures: int = 3, cooldown: float = 60.0) -> None:
        self.failures = failures
        self.cooldown = cooldown
        self._counts: dict[str, int] = {}
        self._until: dict[str, float] = {}

    def allow(self, provider: str) -> bool:
        return self._until.get(provider, 0.0) <= time.time()

    def success(self, provider: str) -> None:
        self._counts.pop(provider, None)
        self._until.pop(provider, None)

    def failure(self, provider: str) -> None:
        count = self._counts.get(provider, 0) + 1
        self._counts[provider] = count
        if count >= self.failures:
            self._until[provider] = time.time() + self.cooldown


def classify_error(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    status = getattr(exc, "status_code", None)
    if status in (401, 403) or any(x in name + " " + text for x in ("auth", "unauthorized", "forbidden", "api key", "login")):
        return ProviderCategory.AUTH
    if status == 429 or any(x in text for x in ("rate limit", "too many requests", "429")):
        return ProviderCategory.RATE_LIMIT
    if isinstance(exc, TimeoutError) or "timeout" in name or "timed out" in text:
        return ProviderCategory.TIMEOUT
    if isinstance(exc, (ConnectionError, OSError)) or any(x in name for x in ("network", "connection")):
        return ProviderCategory.NETWORK
    if status == 404 or any(x in text for x in ("model not found", "unknown model", "not found")):
        return ProviderCategory.MODEL_NOT_FOUND
    if any(x in text for x in ("unsupported", "not support", "does not support")):
        return ProviderCategory.UNSUPPORTED
    if any(x in text for x in ("blocked", "safety", "policy")):
        return ProviderCategory.CONTENT_BLOCKED
    if any(x in text for x in ("json", "schema", "invalid response", "parse")):
        return ProviderCategory.INVALID_RESPONSE
    return ProviderCategory.UNKNOWN


class ProviderRegistry:
    def __init__(self, path: Path = REGISTRY_FILE) -> None:
        self.store = JsonStore(path)
        self.providers: dict[str, ProviderRecord] = {}
        self.models: dict[str, list[ModelBinding]] = {}

    @classmethod
    def discover(cls) -> "ProviderRegistry":
        registry = cls()
        try:
            from .Provider import ProviderLoader
            names: Iterable[str] = ProviderLoader.names
        except Exception:
            names = []
        for name in names:
            registry.providers[name] = registry.inspect(name)
        registry.persist()
        return registry

    def inspect(self, name: str) -> ProviderRecord:
        try:
            from .Provider import ProviderLoader
            provider = ProviderLoader.from_name(name)
            caps = CapabilitySet(
                streaming=getattr(provider, "supports_stream", None),
                vision=getattr(provider, "supports_vision", getattr(provider, "vision", None)),
                tools=getattr(provider, "supports_native_tools", None),
                structured_output=getattr(provider, "supports_structured_output", None),
                image=getattr(provider, "supports_image_generation", None),
                audio=getattr(provider, "supports_audio", None),
                video=getattr(provider, "supports_video", None),
            )
            models = getattr(provider, "models", [])
            if isinstance(models, str):
                models = [models]
            return ProviderRecord(
                name=name,
                url=getattr(provider, "url", None),
                working=getattr(provider, "working", None),
                active_by_default=getattr(provider, "active_by_default", None),
                needs_auth=bool(getattr(provider, "needs_auth", False)),
                capabilities=caps,
                models=[str(x) for x in models if x],
            )
        except Exception:
            return ProviderRecord(name=name)

    def bind_model(self, model: str, provider: str, capabilities: CapabilitySet | None = None, verified: bool = False) -> None:
        item = ModelBinding(model, provider, capabilities or CapabilitySet(), verified, time.time() if verified else None)
        bindings = [x for x in self.models.get(model, []) if x.provider != provider]
        bindings.append(item)
        self.models[model] = bindings
        self.persist()

    def model_candidates(self, model: str) -> list[ModelBinding]:
        return list(self.models.get(model, []))

    def persist(self) -> None:
        self.store.save({
            "providers": {k: asdict(v) for k, v in self.providers.items()},
            "models": {k: [asdict(v) for v in values] for k, values in self.models.items()},
        })


class AdaptiveRouter:
    def __init__(self, registry: ProviderRegistry, health: HealthStore | None = None) -> None:
        self.registry = registry
        self.health = health or HealthStore()
        self.circuit = ProviderCircuit()

    def rank(self, model: str, required: Mapping[str, bool] | None = None, providers: Sequence[str] | None = None) -> list[str]:
        required = required or {}
        names = list(providers) if providers else list(self.registry.providers)
        scored: list[tuple[float, str]] = []
        for name in names:
            spec = self.registry.providers.get(name) or self.registry.inspect(name)
            if required and not spec.capabilities.satisfies(required):
                continue
            health = self.health.get(name)
            if not self.circuit.allow(name) or not self.health.available(name):
                continue
            model_bonus = 12.0 if model in spec.models else 0.0
            active_bonus = 4.0 if spec.active_by_default else 0.0
            auth_penalty = 3.0 if spec.needs_auth else 0.0
            score = health.score + model_bonus + active_bonus - auth_penalty
            scored.append((score, name))
        scored.sort(reverse=True)
        return [name for _, name in scored]

    def select(self, model: str, required: Mapping[str, bool] | None = None, providers: Sequence[str] | None = None) -> str | None:
        ranked = self.rank(model, required, providers)
        return ranked[0] if ranked else None

    def execute(self, model: str, fn: Callable[[str], Any], required: Mapping[str, bool] | None = None, providers: Sequence[str] | None = None) -> Any:
        ranked = self.rank(model, required, providers)
        if not ranked:
            raise RuntimeError(f"No provider satisfies model={model!r} capabilities={dict(required or {})}")
        errors: dict[str, BaseException] = {}
        for provider in ranked:
            started = time.perf_counter()
            try:
                result = fn(provider)
                latency = (time.perf_counter() - started) * 1000
                self.health.record_success(provider, latency)
                self.circuit.success(provider)
                return result
            except Exception as exc:
                latency = (time.perf_counter() - started) * 1000
                errors[provider] = exc
                self.health.record_failure(provider, exc)
                self.circuit.failure(provider)
                category = classify_error(exc)
                if category == ProviderCategory.AUTH:
                    continue
        message = "; ".join(f"{p}: {type(e).__name__}: {e}" for p, e in errors.items())
        raise RuntimeError(f"Adaptive routing exhausted providers: {message}") from next(iter(errors.values()))


@dataclass(slots=True)
class NormalizedToolCall:
    id: str
    name: str
    arguments: str
    index: int = 0
    type: str = "function"


def normalize_tool_calls(value: Any) -> list[NormalizedToolCall]:
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    result: list[NormalizedToolCall] = []
    for index, raw in enumerate(items):
        if raw is None:
            continue
        if isinstance(raw, Mapping):
            data = dict(raw)
            function = data.get("function") if isinstance(data.get("function"), Mapping) else data
            call_id = str(data.get("id") or f"call_{uuid.uuid4().hex[:16]}")
            name = str(function.get("name") or data.get("name") or "")
            arguments = function.get("arguments", data.get("arguments", "{}"))
            idx = int(data.get("index", index) or index)
            kind = str(data.get("type", "function"))
        else:
            function = getattr(raw, "function", raw)
            call_id = str(getattr(raw, "id", None) or f"call_{uuid.uuid4().hex[:16]}")
            name = str(getattr(function, "name", getattr(raw, "name", "")))
            arguments = getattr(function, "arguments", getattr(raw, "arguments", "{}"))
            idx = int(getattr(raw, "index", index) or index)
            kind = str(getattr(raw, "type", "function"))
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"), default=str)
        result.append(NormalizedToolCall(call_id, name, arguments, idx, kind))
    return result


@dataclass(slots=True)
class BenchmarkResult:
    name: str
    ok: bool
    latency_ms: float
    error: str | None = None
    category: str | None = None


class Arena:
    def run(self, cases: Mapping[str, Callable[[], Any]]) -> list[BenchmarkResult]:
        results: list[BenchmarkResult] = []
        for name, case in cases.items():
            started = time.perf_counter()
            try:
                case()
                results.append(BenchmarkResult(name, True, (time.perf_counter() - started) * 1000))
            except Exception as exc:
                results.append(BenchmarkResult(name, False, (time.perf_counter() - started) * 1000, str(exc), classify_error(exc)))
        return results

    @staticmethod
    def summarize(results: Sequence[BenchmarkResult]) -> dict[str, Any]:
        latencies = [r.latency_ms for r in results]
        return {
            "tests": len(results),
            "passed": sum(r.ok for r in results),
            "failed": sum(not r.ok for r in results),
            "success_rate": (sum(r.ok for r in results) / len(results)) if results else 0.0,
            "avg_latency_ms": statistics.mean(latencies) if latencies else 0.0,
            "p95_latency_ms": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else 0.0,
        }


class SecurityPolicy:
    def __init__(self, allow_hosts: Sequence[str] = (), allow_private: bool = False) -> None:
        self.allow_hosts = {x.lower() for x in allow_hosts}
        self.allow_private = allow_private

    def validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Only http/https URLs with a hostname are allowed")
        host = parsed.hostname.lower()
        if self.allow_hosts and host not in self.allow_hosts:
            raise PermissionError(f"Host not allowlisted: {host}")
        try:
            address = ipaddress.ip_address(socket.gethostbyname(host))
            if not self.allow_private and (address.is_private or address.is_loopback or address.is_link_local):
                raise PermissionError(f"Private/local destination blocked: {host}")
        except socket.gaierror:
            pass

    def validate_tool(self, name: str, allowed_tools: Sequence[str]) -> None:
        if allowed_tools and name not in allowed_tools:
            raise PermissionError(f"Tool not allowlisted: {name}")


class MediaStore:
    def __init__(self, root: Path = MEDIA_DIR, policy: SecurityPolicy | None = None) -> None:
        self.root = root
        self.policy = policy or SecurityPolicy()

    def store_bytes(self, data: bytes, suffix: str = ".bin", content_type: str | None = None) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(data).hexdigest()
        safe_suffix = suffix if suffix.startswith(".") else "." + suffix
        path = self.root / f"{digest}{safe_suffix}"
        if not path.exists():
            path.write_bytes(data)
        return path

    def fetch(self, url: str, timeout: float = 30.0) -> Path:
        self.policy.validate_url(url)
        request = urllib.request.Request(url, headers={"User-Agent": "ROCKSOUL-g4f-media/1"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "")
        extension = ".bin"
        for candidate in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp3", ".wav", ".mp4"):
            if candidate in content_type.lower():
                extension = candidate
                break
        return self.store_bytes(data, extension, content_type)


@dataclass(slots=True)
class MeshNode:
    node_id: str
    endpoint: str
    capabilities: CapabilitySet = field(default_factory=CapabilitySet)
    health: float = 50.0
    latency_ms: float | None = None
    last_seen: float = field(default_factory=time.time)

    @property
    def score(self) -> float:
        latency_penalty = 0.0 if self.latency_ms is None else min(30.0, self.latency_ms / 100.0)
        return max(0.0, self.health - latency_penalty)


class MeshRegistry:
    def __init__(self, path: Path = MESH_FILE) -> None:
        self.store = JsonStore(path)
        self.nodes: dict[str, MeshNode] = {}

    def add(self, node: MeshNode) -> None:
        self.nodes[node.node_id] = node
        self.persist()

    def remove(self, node_id: str) -> None:
        self.nodes.pop(node_id, None)
        self.persist()

    def select(self, required: Mapping[str, bool] | None = None) -> MeshNode | None:
        required = required or {}
        candidates = [n for n in self.nodes.values() if n.capabilities.satisfies(required)]
        return max(candidates, key=lambda n: n.score, default=None)

    def persist(self) -> None:
        self.store.save({k: asdict(v) for k, v in self.nodes.items()})


class AgentRuntime:
    def __init__(self, model_fn: Callable[[str, Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]]], Any], policy: SecurityPolicy | None = None) -> None:
        self.model_fn = model_fn
        self.policy = policy or SecurityPolicy()
        self.tools: dict[str, Callable[..., Any]] = {}

    def register_tool(self, name: str, fn: Callable[..., Any]) -> None:
        self.tools[name] = fn

    def run(self, prompt: str, max_steps: int = 8) -> Any:
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        for _ in range(max_steps):
            response = self.model_fn(prompt, messages, [{"name": n} for n in self.tools])
            calls = normalize_tool_calls(response.get("tool_calls") if isinstance(response, Mapping) else None)
            if not calls:
                return response
            messages.append({"role": "assistant", "content": None, "tool_calls": [asdict(c) for c in calls]})
            for call in calls:
                self.policy.validate_tool(call.name, tuple(self.tools))
                fn = self.tools[call.name]
                args = json.loads(call.arguments or "{}")
                result = fn(**args) if isinstance(args, Mapping) else fn(args)
                messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name, "content": json.dumps(result, ensure_ascii=False, default=str)})
        raise RuntimeError("Agent exceeded max_steps")


class RocksoulClient:
    """Adaptive wrapper around g4f.client.Client.

    Pass explicit providers to keep routing deterministic and avoid probing/auth
    attempts against every provider. The existing g4f client remains unchanged.
    """

    def __init__(self, client: Any = None, registry: ProviderRegistry | None = None, health: HealthStore | None = None) -> None:
        if client is None:
            from .client import Client
            client = Client()
        self.client = client
        self.registry = registry or ProviderRegistry.discover()
        self.router = AdaptiveRouter(self.registry, health)

    def complete(self, model: str, messages: Sequence[Mapping[str, Any]], providers: Sequence[str] | None = None, required: Mapping[str, bool] | None = None, **kwargs: Any) -> Any:
        def execute(provider_name: str) -> Any:
            from .providers.service import get_provider
            try:
                provider = get_provider(provider_name)
            except Exception:
                from .client.service import convert_to_provider
                provider = convert_to_provider(provider_name)
            return self.client.chat.completions.create(messages=list(messages), model=model, provider=provider, **kwargs)
        return self.router.execute(model, execute, required, providers)


def _provider_table(registry: ProviderRegistry, health: HealthStore) -> list[dict[str, Any]]:
    rows = []
    for name, spec in sorted(registry.providers.items()):
        h = health.get(name)
        rows.append({
            "provider": name,
            "working": spec.working,
            "active": spec.active_by_default,
            "auth": spec.needs_auth,
            "score": round(h.score, 1),
            "success_rate": round(h.success_rate * 100, 1),
            "avg_latency_ms": round(h.avg_latency_ms, 1) if h.avg_latency_ms is not None else None,
            "cooldown": max(0, round(h.cooldown_until - time.time(), 1)),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="ROCKSOUL intelligence overlay for g4f")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("discover", help="discover provider metadata")
    sub.add_parser("health", help="show persisted provider health")
    route = sub.add_parser("route", help="rank providers for a model")
    route.add_argument("model")
    route.add_argument("--require-tools", action="store_true")
    route.add_argument("--require-vision", action="store_true")
    norm = sub.add_parser("normalize", help="normalize a JSON tool-call list")
    norm.add_argument("json")
    sub.add_parser("mesh", help="show registered mesh nodes")
    args = parser.parse_args()

    registry = ProviderRegistry.discover()
    health = HealthStore()

    if args.command == "discover":
        print(json.dumps({"providers": len(registry.providers), "state": str(REGISTRY_FILE)}, indent=2))
        return 0
    if args.command == "health":
        print(json.dumps(_provider_table(registry, health), indent=2, ensure_ascii=False))
        return 0
    if args.command == "route":
        router = AdaptiveRouter(registry, health)
        required = {"tools": args.require_tools, "vision": args.require_vision}
        print(json.dumps(router.rank(args.model, required), indent=2))
        return 0
    if args.command == "normalize":
        print(json.dumps([asdict(x) for x in normalize_tool_calls(json.loads(args.json))], indent=2, ensure_ascii=False))
        return 0
    if args.command == "mesh":
        mesh = MeshRegistry()
        print(json.dumps({k: asdict(v) for k, v in mesh.nodes.items()}, indent=2))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
