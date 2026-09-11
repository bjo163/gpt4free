from __future__ import annotations

"""CLI adapter for the SQLite-backed ROCKSOUL intelligence engine."""

import argparse
import json
import time
from typing import Any

from .rocksoul_db import RocksoulDB, DB_PATH


def inspect_provider(db: RocksoulDB, name: str) -> dict[str, Any]:
    result: dict[str, Any] = {"provider": name, "models": 0, "capabilities": 0, "error": None}
    try:
        from .Provider import ProviderLoader

        provider = ProviderLoader.from_name(name)
        db.upsert_provider(
            name,
            getattr(provider, "url", None),
            getattr(provider, "working", None),
            getattr(provider, "active_by_default", None),
            bool(getattr(provider, "needs_auth", False)),
        )

        models = getattr(provider, "models", [])
        if isinstance(models, str):
            models = [models]
        for model in models:
            model_name = str(model)
            if not model_name:
                continue
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
    return {
        "providers": len(names),
        "models": sum(int(item["models"]) for item in results),
        "capabilities": sum(int(item["capabilities"]) for item in results),
        "errors": len(errors),
        "failed_providers": errors,
        "db": str(db.path),
    }


def json_health(db: RocksoulDB, provider: str | None) -> Any:
    if provider:
        item = db.health(provider)
        return {
            "provider": item.provider,
            "attempts": item.attempts,
            "successes": item.successes,
            "failures": item.failures,
            "success_rate": round(item.success_rate * 100.0, 2),
            "avg_latency_ms": item.avg_latency_ms,
            "p95_latency_ms": item.p95_latency_ms,
            "score": round(item.score, 2),
            "status": "COOLDOWN" if item.cooldown_until > time.time() else "ACTIVE",
            "last_error_class": item.last_error_class,
        }
    with db.connect() as conn:
        rows = conn.execute("SELECT name FROM providers ORDER BY name").fetchall()
    return [
        {
            "provider": item["name"],
            "score": round((h := db.health(item["name"])).score, 2),
            "attempts": h.attempts,
            "success_rate": round(h.success_rate * 100.0, 2),
            "avg_latency_ms": h.avg_latency_ms,
        }
        for item in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="ROCKSOUL SQLite intelligence engine")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("discover")
    sub.add_parser("migrate")
    health = sub.add_parser("health")
    health.add_argument("provider", nargs="?")
    route = sub.add_parser("route")
    route.add_argument("model")
    route.add_argument("--verified-only", action="store_true")
    provider = sub.add_parser("provider")
    provider.add_argument("name")
    sub.add_parser("status")
    args = parser.parse_args()
    db = RocksoulDB()

    if args.command == "discover":
        print(json.dumps(discover_all(db), indent=2))
    elif args.command == "migrate":
        print(json.dumps({"migrated": db.migrate_legacy_json(), "db": str(db.path)}, indent=2))
    elif args.command == "provider":
        print(json.dumps(inspect_provider(db, args.name), indent=2))
    elif args.command == "health":
        print(json.dumps(json_health(db, args.provider), indent=2))
    elif args.command == "route":
        candidates = db.route_candidates(args.model, verified_only=args.verified_only)
        print(json.dumps([
            {
                "provider": item.provider,
                "score": round(item.score, 2),
                "model_verified": item.model_verified,
                "health_score": round(item.health_score, 2),
                "avg_latency_ms": item.avg_latency_ms,
            }
            for item in candidates
        ], indent=2))
    elif args.command == "status":
        with db.connect() as conn:
            providers = int(conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0])
            models = int(conn.execute("SELECT COUNT(*) FROM models").fetchone()[0])
            bindings = int(conn.execute("SELECT COUNT(*) FROM provider_models").fetchone()[0])
            capabilities = int(conn.execute("SELECT COUNT(*) FROM capabilities").fetchone()[0])
            probes = int(conn.execute("SELECT COUNT(*) FROM probe_runs").fetchone()[0])
            decisions = int(conn.execute("SELECT COUNT(*) FROM route_decisions").fetchone()[0])
        print(json.dumps({
            "db": str(DB_PATH),
            "providers": providers,
            "models": models,
            "provider_models": bindings,
            "capabilities": capabilities,
            "probes": probes,
            "route_decisions": decisions,
        }, indent=2))


if __name__ == "__main__":
    main()
