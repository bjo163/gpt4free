from __future__ import annotations

"""Operator CLI for the ROCKSOUL F5 Arena foundation."""

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .rocksoul_arena import ArenaCase, ArenaError, ArenaStore, ArenaSuite, run_to_dict
from .rocksoul_db import DB_PATH, RocksoulDB


def _emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def fixture_suite() -> ArenaSuite:
    return ArenaSuite(
        name="rocksoul-offline-smoke",
        version="1",
        evaluator="json_exact",
        provenance={
            "source": "repository-fixture",
            "network": False,
            "purpose": "deterministic F5 contract verification",
        },
        cases=(
            ArenaCase("arithmetic", {"op": "add", "a": 2, "b": 3}, 5, tags=("reasoning",)),
            ArenaCase("normalize", {"text": "ROCK SOUL"}, "rock soul", tags=("text",)),
            ArenaCase("shape", {"items": [3, 1, 2]}, {"items": [1, 2, 3]}, weight=2.0, tags=("structured",)),
        ),
    )


def fixture_executor(target: str):
    def execute(case: ArenaCase) -> Any:
        if target == "failing" and case.case_id == "normalize":
            raise RuntimeError("synthetic fixture failure")
        if case.case_id == "arithmetic":
            value: Any = case.input["a"] + case.input["b"]
        elif case.case_id == "normalize":
            value = str(case.input["text"]).lower()
        elif case.case_id == "shape":
            value = {"items": sorted(case.input["items"])}
        else:
            raise KeyError(case.case_id)
        if target == "mixed" and case.case_id == "arithmetic":
            return -1
        return value

    return execute


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ROCKSOUL F5 Arena benchmark control plane")
    parser.add_argument("--db", default=str(DB_PATH))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    fixture = sub.add_parser("fixture")
    fixture.add_argument("--target", choices=("perfect", "mixed", "failing"), default="perfect")

    manifest = sub.add_parser("fixture-manifest")
    manifest.add_argument("--register", action="store_true")

    runs = sub.add_parser("runs")
    runs.add_argument("--suite-digest", default=None)
    runs.add_argument("--limit", type=int, default=100)

    show = sub.add_parser("show")
    show.add_argument("run_id")

    leaderboard = sub.add_parser("leaderboard")
    leaderboard.add_argument("--suite-digest", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        store = ArenaStore(RocksoulDB(Path(args.db)))
        if args.command == "status":
            _emit(store.status())
        elif args.command == "fixture":
            suite = fixture_suite()
            run = store.run(
                suite,
                args.target,
                fixture_executor(args.target),
                metadata={"fixture": True, "network": False},
            )
            _emit(run_to_dict(run))
        elif args.command == "fixture-manifest":
            suite = fixture_suite()
            if args.register:
                store.register_suite(suite)
            _emit({"digest": suite.digest, "manifest": suite.manifest(), "registered": bool(args.register)})
        elif args.command == "runs":
            _emit(store.list_runs(args.suite_digest, limit=args.limit))
        elif args.command == "show":
            run = store.get_run(args.run_id)
            if run is None:
                _emit({"ok": False, "error": "run_not_found", "run_id": args.run_id})
                return 3
            _emit(run)
        elif args.command == "leaderboard":
            _emit(store.leaderboard(args.suite_digest))
        return 0
    except (ArenaError, ValueError, OSError) as exc:
        _emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
