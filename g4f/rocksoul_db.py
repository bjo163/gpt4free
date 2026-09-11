from __future__ import annotations

"""SQLite-backed ROCKSOUL intelligence store and router.

This module is the canonical persistence layer for provider intelligence.
It deliberately uses only the Python standard library so it remains available
before optional provider integrations are loaded.
"""

import argparse
import json
import os
import sqlite3
import statistics
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ROCKSOUL" / "g4f"
DB_PATH = ROOT / "rocksoul.db"
SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    provider: str
    attempts: int
    successes: int
    failures: int
    avg_latency_ms: float | None
    p95_latency_ms: float | None
    last_error: str | None
    last_error_class: str | None
    consecutive_failures: int
    cooldown_until: float
    updated_at: float

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.5

    @property
    def score(self) -> float:
        reliability = self.success_rate * 70.0
        latency = 20.0 if self.avg_latency_ms is None else max(0.0, 20.0 - min(self.avg_latency_ms / 250.0, 20.0))
        penalty = min(self.consecutive_failures * 5.0, 25.0)
        return max(0.0, min(100.0, reliability + latency - penalty))


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    provider: str
    score: float
    model_verified: bool
    health_score: float
    avg_latency_ms: float | None


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS providers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    url TEXT,
    working INTEGER,
    active_by_default INTEGER,
    needs_auth INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'UNKNOWN',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_models (
    provider_id INTEGER NOT NULL,
    model_id INTEGER NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    verified_at REAL,
    PRIMARY KEY (provider_id, model_id),
    FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS capabilities (
    provider_id INTEGER NOT NULL,
    model_id INTEGER,
    name TEXT NOT NULL,
    declared INTEGER,
    detected INTEGER,
    verified INTEGER NOT NULL DEFAULT 0,
    verified_at REAL,
    PRIMARY KEY (provider_id, model_id, name),
    FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS probe_runs (
    id TEXT PRIMARY KEY,
    provider_id INTEGER NOT NULL,
    model_id INTEGER,
    probe_type TEXT NOT NULL,
    ok INTEGER NOT NULL,
    latency_ms REAL,
    status_code INTEGER,
    error_class TEXT,
    error TEXT,
    response_valid INTEGER,
    started_at REAL NOT NULL,
    finished_at REAL NOT NULL,
    FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS route_decisions (
    id TEXT PRIMARY KEY,
    model_id INTEGER,
    selected_provider_id INTEGER,
    candidates_json TEXT NOT NULL,
    reason_json TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE SET NULL,
    FOREIGN KEY (selected_provider_id) REFERENCES providers(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS health_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id INTEGER NOT NULL,
    attempts INTEGER NOT NULL,
    successes INTEGER NOT NULL,
    failures INTEGER NOT NULL,
    avg_latency_ms REAL,
    p95_latency_ms REAL,
    score REAL NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_probe_provider_time ON probe_runs(provider_id, finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_probe_model_time ON probe_runs(model_id, finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_provider_time ON health_snapshots(provider_id, created_at DESC);
"""


class RocksoulDB:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    def provider_id(self, name: str) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM providers WHERE name = ?", (name,)).fetchone()
            if row is not None:
                return int(row["id"])
            now = time.time()
            cur = conn.execute(
                "INSERT INTO providers(name, created_at, updated_at) VALUES(?, ?, ?)",
                (name, now, now),
            )
            return int(cur.lastrowid)

    def upsert_provider(
        self,
        name: str,
        url: str | None = None,
        working: bool | None = None,
        active_by_default: bool | None = None,
        needs_auth: bool = False,
        status: str = "UNKNOWN",
    ) -> int:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO providers(name, url, working, active_by_default, needs_auth, status, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    url=excluded.url,
                    working=excluded.working,
                    active_by_default=excluded.active_by_default,
                    needs_auth=excluded.needs_auth,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (name, url, working, active_by_default, int(needs_auth), status, now, now),
            )
            return int(conn.execute("SELECT id FROM providers WHERE name = ?", (name,)).fetchone()["id"])

    def upsert_model(self, name: str) -> int:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO models(name, created_at, updated_at) VALUES(?, ?, ?) ON CONFLICT(name) DO UPDATE SET updated_at=excluded.updated_at",
                (name, now, now),
            )
            return int(conn.execute("SELECT id FROM models WHERE name = ?", (name,)).fetchone()["id"])

    def bind_model(self, provider: str, model: str, verified: bool = False) -> None:
        pid = self.provider_id(provider)
        mid = self.upsert_model(model)
        verified_at = time.time() if verified else None
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO provider_models(provider_id, model_id, verified, verified_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(provider_id, model_id) DO UPDATE SET
                    verified=excluded.verified,
                    verified_at=excluded.verified_at
                """,
                (pid, mid, int(verified), verified_at),
            )

    def set_capability(
        self,
        provider: str,
        capability: str,
        declared: bool | None,
        detected: bool | None,
        verified: bool,
        model: str | None = None,
    ) -> None:
        pid = self.provider_id(provider)
        mid = self.upsert_model(model) if model else None
        verified_at = time.time() if verified else None
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO capabilities(provider_id, model_id, name, declared, detected, verified, verified_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, model_id, name) DO UPDATE SET
                    declared=excluded.declared,
                    detected=excluded.detected,
                    verified=excluded.verified,
                    verified_at=excluded.verified_at
                """,
                (pid, mid, capability, declared, detected, int(verified), verified_at),
            )

    def record_probe(
        self,
        provider: str,
        probe_type: str,
        ok: bool,
        latency_ms: float | None = None,
        model: str | None = None,
        status_code: int | None = None,
        error_class: str | None = None,
        error: str | None = None,
        response_valid: bool | None = None,
        started_at: float | None = None,
        finished_at: float | None = None,
    ) -> str:
        started = started_at if started_at is not None else time.time()
        finished = finished_at if finished_at is not None else time.time()
        pid = self.provider_id(provider)
        mid = self.upsert_model(model) if model else None
        probe_id = uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO probe_runs(id, provider_id, model_id, probe_type, ok, latency_ms, status_code,
                                       error_class, error, response_valid, started_at, finished_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    probe_id,
                    pid,
                    mid,
                    probe_type,
                    int(ok),
                    latency_ms,
                    status_code,
                    error_class,
                    error,
                    None if response_valid is None else int(response_valid),
                    started,
                    finished,
                ),
            )
        self.snapshot_health(provider)
        return probe_id

    def _latencies(self, provider_id: int) -> list[float]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT latency_ms FROM probe_runs WHERE provider_id=? AND ok=1 AND latency_ms IS NOT NULL ORDER BY finished_at DESC LIMIT 100",
                (provider_id,),
            ).fetchall()
        return [float(row[0]) for row in rows]

    def health(self, provider: str) -> ProviderHealth:
        pid = self.provider_id(provider)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS attempts,
                       SUM(CASE WHEN ok=1 THEN 1 ELSE 0 END) AS successes,
                       SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) AS failures,
                       MAX(finished_at) AS updated_at
                FROM probe_runs WHERE provider_id=?
                """,
                (pid,),
            ).fetchone()
            last = conn.execute(
                "SELECT error, error_class FROM probe_runs WHERE provider_id=? AND ok=0 ORDER BY finished_at DESC LIMIT 1",
                (pid,),
            ).fetchone()
            consecutive = conn.execute(
                "SELECT ok FROM probe_runs WHERE provider_id=? ORDER BY finished_at DESC LIMIT 10",
                (pid,),
            ).fetchall()
        attempts = int(row["attempts"] or 0)
        successes = int(row["successes"] or 0)
        failures = int(row["failures"] or 0)
        latencies = self._latencies(pid)
        avg = statistics.mean(latencies) if latencies else None
        p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else None
        fail_streak = 0
        for item in consecutive:
            if int(item["ok"]) == 0:
                fail_streak += 1
            else:
                break
        cooldown = 0.0
        if fail_streak >= 3:
            cooldown = time.time() + min(60.0 * (2 ** min(fail_streak - 3, 3)), 900.0)
        return ProviderHealth(
            provider=provider,
            attempts=attempts,
            successes=successes,
            failures=failures,
            avg_latency_ms=avg,
            p95_latency_ms=p95,
            last_error=None if last is None else last["error"],
            last_error_class=None if last is None else last["error_class"],
            consecutive_failures=fail_streak,
            cooldown_until=cooldown,
            updated_at=float(row["updated_at"] or 0.0),
        )

    def snapshot_health(self, provider: str) -> None:
        pid = self.provider_id(provider)
        current = self.health(provider)
        status = "ACTIVE"
        if current.cooldown_until > time.time():
            status = "COOLDOWN"
        elif current.attempts and current.success_rate < 0.7:
            status = "DEGRADED"
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO health_snapshots(provider_id, attempts, successes, failures, avg_latency_ms, p95_latency_ms, score, status, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (pid, current.attempts, current.successes, current.failures, current.avg_latency_ms, current.p95_latency_ms, current.score, status, time.time()),
            )
            conn.execute("UPDATE providers SET status=?, updated_at=? WHERE id=?", (status, time.time(), pid))

    def route_candidates(self, model: str, providers: Sequence[str] | None = None, verified_only: bool = False) -> list[RouteCandidate]:
        model_id = self.upsert_model(model)
        params: list[Any] = [model_id]
        sql = """
            SELECT p.name, pm.verified, p.active_by_default, p.needs_auth
            FROM providers p
            JOIN provider_models pm ON pm.provider_id=p.id
            WHERE pm.model_id=?
        """
        if providers:
            marks = ",".join("?" for _ in providers)
            sql += f" AND p.name IN ({marks})"
            params.extend(providers)
        if verified_only:
            sql += " AND pm.verified=1"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        result: list[RouteCandidate] = []
        for row in rows:
            health = self.health(row["name"])
            if health.cooldown_until > time.time():
                continue
            score = health.score + (12.0 if row["verified"] else 0.0) + (4.0 if row["active_by_default"] else 0.0) - (3.0 if row["needs_auth"] else 0.0)
            result.append(RouteCandidate(row["name"], score, bool(row["verified"]), health.score, health.avg_latency_ms))
        result.sort(key=lambda item: (-item.score, item.provider))
        return result

    def record_route(self, model: str, candidates: Sequence[RouteCandidate], selected: str | None, reasons: Sequence[str] = ()) -> None:
        mid = self.upsert_model(model)
        sid = self.provider_id(selected) if selected else None
        payload = [
            {
                "provider": candidate.provider,
                "score": candidate.score,
                "model_verified": candidate.model_verified,
                "health_score": candidate.health_score,
                "avg_latency_ms": candidate.avg_latency_ms,
            }
            for candidate in candidates
        ]
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO route_decisions(id, model_id, selected_provider_id, candidates_json, reason_json, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, mid, sid, json.dumps(payload), json.dumps(list(reasons)), time.time()),
            )

    def migrate_legacy_json(self, registry_json: Path | None = None, health_json: Path | None = None) -> dict[str, int]:
        imported = {"providers": 0, "models": 0, "health": 0}
        registry_path = registry_json or (ROOT / "intelligence" / "registry.json")
        health_path = health_json or (ROOT / "intelligence" / "health.json")
        if registry_path.exists():
            try:
                data = json.loads(registry_path.read_text(encoding="utf-8"))
                for value in data.get("providers", {}).values():
                    name = str(value.get("name", ""))
                    if not name:
                        continue
                    self.upsert_provider(name, value.get("url"), value.get("working"), value.get("active_by_default"), bool(value.get("needs_auth", False)))
                    imported["providers"] += 1
                    for model in value.get("models", []):
                        self.bind_model(name, str(model), False)
                        imported["models"] += 1
                for model, bindings in data.get("models", {}).items():
                    for binding in bindings:
                        provider = str(binding.get("provider", ""))
                        if provider:
                            self.bind_model(model, provider, bool(binding.get("verified", False)))
            except (OSError, ValueError, TypeError):
                pass
        if health_path.exists():
            try:
                data = json.loads(health_path.read_text(encoding="utf-8"))
                for provider, value in data.items():
                    successes = int(value.get("successes", 0))
                    failures = int(value.get("failures", 0))
                    latency = value.get("last_latency_ms")
                    for _ in range(successes):
                        self.record_probe(provider, "legacy", True, latency)
                    for _ in range(failures):
                        self.record_probe(provider, "legacy", False, error_class=value.get("last_error_class"), error=value.get("last_error"))
                    imported["health"] += 1
            except (OSError, ValueError, TypeError):
                pass
        return imported


class DBRouter:
    def __init__(self, db: RocksoulDB | None = None) -> None:
        self.db = db or RocksoulDB()

    def select(self, model: str, providers: Sequence[str] | None = None) -> RouteCandidate | None:
        candidates = self.db.route_candidates(model, providers)
        selected = candidates[0] if candidates else None
        self.db.record_route(model, candidates, selected.provider if selected else None, ["model_verified" if selected and selected.model_verified else "model_unverified", "health_score", "latency_score"])
        return selected


def discover() -> int:
    from .Provider import ProviderLoader

    db = RocksoulDB()
    count = 0
    for name in ProviderLoader.names:
        db.upsert_provider(name)
        count += 1
    return count


def migrate() -> dict[str, int]:
    return RocksoulDB().migrate_legacy_json()


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
    sub.add_parser("status")
    args = parser.parse_args()
    db = RocksoulDB()

    if args.command == "discover":
        print(json.dumps({"providers": discover(), "db": str(db.path)}, indent=2))
    elif args.command == "migrate":
        print(json.dumps({"migrated": migrate(), "db": str(db.path)}, indent=2))
    elif args.command == "health":
        if args.provider:
            health_value = db.health(args.provider)
            print(json.dumps({
                "provider": health_value.provider,
                "attempts": health_value.attempts,
                "successes": health_value.successes,
                "failures": health_value.failures,
                "success_rate": round(health_value.success_rate * 100.0, 2),
                "avg_latency_ms": health_value.avg_latency_ms,
                "p95_latency_ms": health_value.p95_latency_ms,
                "score": round(health_value.score, 2),
                "status": "COOLDOWN" if health_value.cooldown_until > time.time() else "ACTIVE",
                "last_error_class": health_value.last_error_class,
            }, indent=2))
        else:
            with db.connect() as conn:
                rows = conn.execute("SELECT name FROM providers ORDER BY name").fetchall()
            output = []
            for row in rows:
                item = db.health(row["name"])
                output.append({"provider": item.provider, "score": round(item.score, 2), "attempts": item.attempts, "success_rate": round(item.success_rate * 100.0, 2), "avg_latency_ms": item.avg_latency_ms})
            print(json.dumps(output, indent=2))
    elif args.command == "route":
        candidates = db.route_candidates(args.model, verified_only=args.verified_only)
        print(json.dumps([{
            "provider": item.provider,
            "score": round(item.score, 2),
            "model_verified": item.model_verified,
            "health_score": round(item.health_score, 2),
            "avg_latency_ms": item.avg_latency_ms,
        } for item in candidates], indent=2))
    elif args.command == "status":
        with db.connect() as conn:
            providers = int(conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0])
            models = int(conn.execute("SELECT COUNT(*) FROM models").fetchone()[0])
            probes = int(conn.execute("SELECT COUNT(*) FROM probe_runs").fetchone()[0])
            decisions = int(conn.execute("SELECT COUNT(*) FROM route_decisions").fetchone()[0])
        print(json.dumps({"db": str(db.path), "providers": providers, "models": models, "probes": probes, "route_decisions": decisions, "schema_version": SCHEMA_VERSION}, indent=2))


if __name__ == "__main__":
    main()
