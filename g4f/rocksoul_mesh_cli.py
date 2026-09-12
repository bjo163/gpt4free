from __future__ import annotations

"""Operator CLI for the ROCKSOUL Mesh control plane."""

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .rocksoul_db import DB_PATH, RocksoulDB
from .rocksoul_mesh import MESH_STATES, MeshError, MeshPolicy, MeshStore, make_mesh_auth


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _secrets() -> str | Mapping[str, str] | None:
    raw = os.environ.get("ROCKSOUL_MESH_KEYS_JSON")
    if raw:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("ROCKSOUL_MESH_KEYS_JSON must be a JSON object")
        return {str(key): str(secret) for key, secret in value.items()}
    return os.environ.get("ROCKSOUL_MESH_SECRET")


def _secret_for_node(node_id: str) -> str:
    value = _secrets()
    if isinstance(value, Mapping):
        secret = value.get(node_id)
    else:
        secret = value
    if not secret:
        raise ValueError(f"no mesh secret configured for node {node_id!r}")
    return str(secret)


def _store(args: argparse.Namespace) -> MeshStore:
    allow_local = bool(args.allow_insecure_local) or _truthy(os.environ.get("ROCKSOUL_MESH_ALLOW_INSECURE_LOCAL"))
    policy = MeshPolicy(allow_insecure_local=allow_local)
    return MeshStore(RocksoulDB(Path(args.db)), secret=_secrets(), policy=policy)


def _emit(value: Any) -> None:
    print(json.dumps(value, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ROCKSOUL Mesh operator control plane")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--allow-insecure-local", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    sub.add_parser("list")

    register = sub.add_parser("register")
    register.add_argument("node_id")
    register.add_argument("endpoint")
    register.add_argument("--capability", action="append", default=[])
    register.add_argument("--weight", type=float, default=1.0)

    heartbeat = sub.add_parser("heartbeat")
    heartbeat.add_argument("node_id")
    heartbeat.add_argument("--health", type=float, default=100.0)
    heartbeat.add_argument("--latency-ms", type=float, default=None)

    state = sub.add_parser("state")
    state.add_argument("node_id")
    state.add_argument("state", choices=MESH_STATES)
    state.add_argument("--reason", default="operator_state_change")

    select = sub.add_parser("select")
    select.add_argument("--capability", action="append", default=[])

    lease = sub.add_parser("lease")
    lease.add_argument("request_id")
    lease.add_argument("--capability", action="append", default=[])
    lease.add_argument("--ttl", type=float, default=None)

    release = sub.add_parser("release")
    release.add_argument("lease_id")
    outcome = release.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--success", action="store_true")
    outcome.add_argument("--failure", action="store_true")
    release.add_argument("--latency-ms", type=float, default=None)
    release.add_argument("--error", default=None)

    events = sub.add_parser("events")
    events.add_argument("--node", default=None)
    events.add_argument("--limit", type=int, default=100)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        store = _store(args)
        if args.command == "status":
            _emit(store.status())
        elif args.command == "list":
            _emit([asdict(node) | {"score": node.score} for node in store.list_nodes()])
        elif args.command == "register":
            node = store.register_operator_node(
                args.node_id, args.endpoint, args.capability, weight=args.weight
            )
            _emit(asdict(node) | {"score": node.score})
        elif args.command == "heartbeat":
            secret = _secret_for_node(args.node_id)
            payload = {"health": float(args.health), "latency_ms": args.latency_ms}
            auth = make_mesh_auth(secret, "heartbeat", args.node_id, payload)
            node = store.heartbeat(
                args.node_id,
                health=args.health,
                latency_ms=args.latency_ms,
                auth=auth,
            )
            _emit(asdict(node) | {"score": node.score})
        elif args.command == "state":
            node = store.set_state(args.node_id, args.state, args.reason)
            _emit(asdict(node) | {"score": node.score})
        elif args.command == "select":
            node = store.select(tuple(args.capability))
            _emit({"selected": None} if node is None else {"selected": asdict(node) | {"score": node.score}})
        elif args.command == "lease":
            lease = store.acquire_lease(args.request_id, tuple(args.capability), ttl=args.ttl)
            _emit({"lease": None} if lease is None else {"lease": asdict(lease)})
        elif args.command == "release":
            lease = store.release_lease(
                args.lease_id,
                success=bool(args.success),
                latency_ms=args.latency_ms,
                error=args.error,
            )
            _emit({"lease": asdict(lease)})
        elif args.command == "events":
            _emit(store.events(args.node, limit=args.limit))
        return 0
    except (MeshError, ValueError, json.JSONDecodeError) as exc:
        _emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
