from __future__ import annotations

"""CLI adapter for the SQLite-backed ROCKSOUL intelligence engine."""

import argparse
import json
import time
from dataclasses import asdict
from typing import Any

from .rocksoul_db import RocksoulDB, DB_PATH
from .rocksoul_probe import LiveProbe, default_probe_model, result_summary
from .rocksoul_intelligence import CAPABILITIES, CapabilityRequirement, CapabilityVerifier, ExplainableRouter, RecoveryManager
from .rocksoul_execution import ExecutionEngine, ExecutionRequest
from .rocksoul_execution_store import ExecutionTraceStore


def inspect_provider(db: RocksoulDB, name: str) -> dict[str, Any]:
    result: dict[str, Any] = {"provider": name, "models": 0, "capabilities": 0, "error": None}
    try:
        from .Provider import ProviderLoader
        provider = ProviderLoader.from_name(name)
        db.upsert_provider(name, getattr(provider, "url", None), getattr(provider, "working", None), getattr(provider, "active_by_default", None), bool(getattr(provider, "needs_auth", False)))
        models = getattr(provider, "models", [])
        if isinstance(models, str):
            models = [models]
        for model in models:
            model_name = str(model)
            if model_name:
                db.bind_model(name, model_name, False)
                result["models"] += 1
        capability_map = {
            "streaming": getattr(provider, "supports_stream", None),
            "vision": getattr(provider, "supports_vision", getattr(provider, "vision", None)),
            "tools": getattr(provider, "supports_native_tools", None),
            "structured_output": getattr(provider, "supports_structured_output", None),
            "image": getattr(provider, "supports_image_generation", None),
            "audio": getattr(provider, "supports_audio", None),
            "video": getattr(provider, "supports_video", None),
        }
        for capability, declared in capability_map.items():
            if declared is not None:
                db.set_capability(name, capability, bool(declared), None, False)
                result["capabilities"] += 1
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def discover_all(db: RocksoulDB) -> dict[str, Any]:
    from .Provider import ProviderLoader
    names = list(ProviderLoader.names)
    results = [inspect_provider(db, name) for name in names]
    errors = [item for item in results if item["error"]]
    return {"providers": len(names), "models": sum(int(item["models"]) for item in results), "capabilities": sum(int(item["capabilities"]) for item in results), "errors": len(errors), "failed_providers": errors, "db": str(db.path)}


def json_health(db: RocksoulDB, provider: str | None) -> Any:
    if provider:
        item = db.health(provider)
        return {"provider": item.provider, "attempts": item.attempts, "successes": item.successes, "failures": item.failures, "success_rate": round(item.success_rate * 100.0, 2), "avg_latency_ms": item.avg_latency_ms, "p95_latency_ms": item.p95_latency_ms, "score": round(item.score, 2), "status": "COOLDOWN" if item.cooldown_until > time.time() else ("DEGRADED" if item.attempts and item.success_rate < 0.7 else "ACTIVE"), "last_error_class": item.last_error_class}
    with db.connect() as conn:
        rows = conn.execute("SELECT name FROM providers ORDER BY name").fetchall()
    return [{"provider": row["name"], "score": round((h := db.health(row["name"])).score, 2), "attempts": h.attempts, "success_rate": round(h.success_rate * 100.0, 2), "avg_latency_ms": h.avg_latency_ms, "status": "COOLDOWN" if h.cooldown_until > time.time() else ("DEGRADED" if h.attempts and h.success_rate < 0.7 else "ACTIVE")} for row in rows]


def _model_for_provider(db: RocksoulDB, provider: str, requested: str | None) -> str:
    if requested:
        return requested
    with db.connect() as conn:
        row = conn.execute("SELECT m.name FROM models m JOIN provider_models pm ON pm.model_id=m.id JOIN providers p ON p.id=pm.provider_id WHERE p.name=? ORDER BY pm.verified DESC, m.name LIMIT 1", (provider,)).fetchone()
    return str(row["name"]) if row else default_probe_model()


def _requirements(args: argparse.Namespace) -> list[CapabilityRequirement]:
    return [CapabilityRequirement(name) for name in CAPABILITIES if bool(getattr(args, name, False))]


def main() -> None:
    parser = argparse.ArgumentParser(description="ROCKSOUL SQLite intelligence engine")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("discover")
    sub.add_parser("migrate")
    health = sub.add_parser("health"); health.add_argument("provider", nargs="?")
    route = sub.add_parser("route"); route.add_argument("model"); route.add_argument("--verified-only", action="store_true")
    for name in CAPABILITIES: route.add_argument(f"--{name}", action="store_true")
    explain = sub.add_parser("route-explain"); explain.add_argument("model")
    for name in CAPABILITIES: explain.add_argument(f"--{name}", action="store_true")
    provider = sub.add_parser("provider"); provider.add_argument("name")
    probe = sub.add_parser("probe"); probe.add_argument("provider"); probe.add_argument("--model", default=None); probe.add_argument("--type", choices=["smoke", "stream"], default="smoke"); probe.add_argument("--timeout", type=float, default=30.0)
    verify = sub.add_parser("verify"); verify.add_argument("provider"); verify.add_argument("--model", default=None); verify.add_argument("--capability", choices=list(CAPABILITIES), action="append"); verify.add_argument("--timeout", type=float, default=30.0)
    probe_all = sub.add_parser("probe-all"); probe_all.add_argument("--model", default=None); probe_all.add_argument("--type", choices=["smoke", "stream"], default="smoke"); probe_all.add_argument("--concurrency", type=int, default=4); probe_all.add_argument("--timeout", type=float, default=30.0)
    recover = sub.add_parser("recover"); recover.add_argument("--provider", action="append"); recover.add_argument("--model", default=default_probe_model()); recover.add_argument("--timeout", type=float, default=30.0)
    execute = sub.add_parser("execute"); execute.add_argument("model"); execute.add_argument("message"); execute.add_argument("--provider", action="append"); execute.add_argument("--capability", action="append"); execute.add_argument("--max-attempts", type=int, default=3); execute.add_argument("--timeout", type=float, default=30.0); execute.add_argument("--total-time", type=float, default=90.0)
    trace = sub.add_parser("trace"); trace.add_argument("request_id")
    sub.add_parser("status")
    args = parser.parse_args(); db = RocksoulDB()
    execution_store = ExecutionTraceStore(db)

    if args.command == "discover":
        print(json.dumps(discover_all(db), indent=2))
    elif args.command == "migrate":
        print(json.dumps({"migrated": db.migrate_legacy_json(), "db": str(db.path)}, indent=2))
    elif args.command == "provider":
        print(json.dumps(inspect_provider(db, args.name), indent=2))
    elif args.command == "health":
        print(json.dumps(json_health(db, args.provider), indent=2))
    elif args.command == "route":
        requirements = _requirements(args)
        if requirements:
            selected = ExplainableRouter(db).select(args.model, requirements)
            print(json.dumps(selected or {"selected": None, "reason": "no candidate satisfied capability requirements"}, indent=2))
        else:
            candidates = db.route_candidates(args.model, verified_only=args.verified_only)
            db.record_route(args.model, candidates, candidates[0].provider if candidates else None, ["model_verified", "health_score", "latency_score"])
            print(json.dumps([{"provider": item.provider, "score": round(item.score, 2), "model_verified": item.model_verified, "health_score": round(item.health_score, 2), "avg_latency_ms": item.avg_latency_ms} for item in candidates], indent=2))
    elif args.command == "route-explain":
        print(json.dumps(ExplainableRouter(db).explain(args.model, _requirements(args)), indent=2))
    elif args.command == "probe":
        model = _model_for_provider(db, args.provider, args.model)
        print(json.dumps(LiveProbe(db).probe(args.provider, model, args.type, args.timeout).to_dict(), indent=2))
    elif args.command == "verify":
        model = _model_for_provider(db, args.provider, args.model)
        results = CapabilityVerifier(db).verify_many(args.provider, model, args.capability or ["streaming"], args.timeout)
        print(json.dumps([item.to_dict() for item in results], indent=2))
    elif args.command == "probe-all":
        with db.connect() as conn:
            providers = [row["name"] for row in conn.execute("SELECT name FROM providers ORDER BY name").fetchall()]
        if not providers:
            discover_all(db)
            with db.connect() as conn:
                providers = [row["name"] for row in conn.execute("SELECT name FROM providers ORDER BY name").fetchall()]
        model = args.model or default_probe_model()
        results = LiveProbe(db).probe_many(providers, model, args.concurrency, args.type, args.timeout)
        print(json.dumps(result_summary(results), indent=2))
    elif args.command == "recover":
        print(json.dumps(RecoveryManager(db).recover(args.provider, args.model, args.timeout), indent=2))
    elif args.command == "execute":
        request = ExecutionRequest(
            model=args.model,
            messages=({"role": "user", "content": args.message},),
            requirements=tuple(args.capability or ()),
            providers=tuple(args.provider or ()),
            max_attempts=max(1, args.max_attempts),
            timeout=max(0.1, args.timeout),
            max_total_time=max(0.1, args.total_time),
        )
        result = ExecutionEngine(db=db).execute(request)
        print(json.dumps({"request_id": result.request_id, "ok": result.ok, "model": result.model, "provider": result.provider, "outcome": result.outcome, "error_class": result.error_class, "error": result.error, "attempts": [asdict(item) for item in result.attempts]}, indent=2, default=str))
    elif args.command == "trace":
        print(json.dumps(execution_store.trace(args.request_id) or {"request_id": args.request_id, "found": False}, indent=2))
    elif args.command == "status":
        with db.connect() as conn:
            counts = {key: int(conn.execute(query).fetchone()[0]) for key, query in {
                "providers": "SELECT COUNT(*) FROM providers", "models": "SELECT COUNT(*) FROM models", "provider_models": "SELECT COUNT(*) FROM provider_models", "capabilities": "SELECT COUNT(*) FROM capabilities", "probes": "SELECT COUNT(*) FROM probe_runs", "route_decisions": "SELECT COUNT(*) FROM route_decisions", "execution_runs": "SELECT COUNT(*) FROM execution_runs", "execution_attempts": "SELECT COUNT(*) FROM execution_attempts"}.items()}
        print(json.dumps({"db": str(DB_PATH), **counts}, indent=2))


if __name__ == "__main__":
    main()
