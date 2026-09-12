from __future__ import annotations

"""SQLite-backed ROCKSOUL intelligence store and router."""

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
SCHEMA_VERSION = 2


class _ClosingConnection(sqlite3.Connection):
    """Connection whose context manager also closes the handle.

    sqlite3.Connection.__exit__ commits/rolls back but intentionally does not
    close the connection. ROCKSOUL uses ``with db.connect()`` extensively, so
    closing here prevents SQLite handles from leaking across Windows tests and
    production short-lived commands.
    """

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


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
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS providers (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, url TEXT, working INTEGER,
 active_by_default INTEGER, needs_auth INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'UNKNOWN', created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS models (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS provider_models (
 provider_id INTEGER NOT NULL, model_id INTEGER NOT NULL, verified INTEGER NOT NULL DEFAULT 0, verified_at REAL,
 PRIMARY KEY(provider_id, model_id), FOREIGN KEY(provider_id) REFERENCES providers(id) ON DELETE CASCADE,
 FOREIGN KEY(model_id) REFERENCES models(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS capabilities (
 provider_id INTEGER NOT NULL, model_id INTEGER, name TEXT NOT NULL, declared INTEGER,
 detected INTEGER, verified INTEGER NOT NULL DEFAULT 0, verified_at REAL,
 PRIMARY KEY(provider_id, model_id, name), FOREIGN KEY(provider_id) REFERENCES providers(id) ON DELETE CASCADE,
 FOREIGN KEY(model_id) REFERENCES models(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS probe_runs (
 id TEXT PRIMARY KEY, provider_id INTEGER NOT NULL, model_id INTEGER, probe_type TEXT NOT NULL, ok INTEGER NOT NULL,
 latency_ms REAL, status_code INTEGER, error_class TEXT, error TEXT, response_valid INTEGER,
 started_at REAL NOT NULL, finished_at REAL NOT NULL, FOREIGN KEY(provider_id) REFERENCES providers(id) ON DELETE CASCADE,
 FOREIGN KEY(model_id) REFERENCES models(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS route_decisions (
 id TEXT PRIMARY KEY, model_id INTEGER, selected_provider_id INTEGER, candidates_json TEXT NOT NULL,
 reason_json TEXT, created_at REAL NOT NULL, FOREIGN KEY(model_id) REFERENCES models(id) ON DELETE SET NULL,
 FOREIGN KEY(selected_provider_id) REFERENCES providers(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS health_snapshots (
 id INTEGER PRIMARY KEY AUTOINCREMENT, provider_id INTEGER NOT NULL, attempts INTEGER NOT NULL,
 successes INTEGER NOT NULL, failures INTEGER NOT NULL, avg_latency_ms REAL, p95_latency_ms REAL,
 score REAL NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL,
 FOREIGN KEY(provider_id) REFERENCES providers(id) ON DELETE CASCADE
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
        conn = sqlite3.connect(self.path, timeout=10.0, factory=_ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.execute("INSERT INTO meta(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(SCHEMA_VERSION),))

    def provider_id(self, name: str) -> int:
        now = time.time()
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM providers WHERE name=?", (name,)).fetchone()
            if row:
                return int(row[0])
            cur = conn.execute("INSERT INTO providers(name,created_at,updated_at) VALUES(?,?,?)", (name, now, now))
            return int(cur.lastrowid)

    def upsert_provider(self, name: str, url: str | None = None, working: bool | None = None, active_by_default: bool | None = None, needs_auth: bool = False, status: str = "UNKNOWN") -> int:
        now = time.time()
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO providers(name,url,working,active_by_default,needs_auth,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(name) DO UPDATE SET url=excluded.url,working=excluded.working,
                active_by_default=excluded.active_by_default,needs_auth=excluded.needs_auth,
                status=excluded.status,updated_at=excluded.updated_at
            """, (name, url, working, active_by_default, int(needs_auth), status, now, now))
            return int(conn.execute("SELECT id FROM providers WHERE name=?", (name,)).fetchone()[0])

    def upsert_model(self, name: str) -> int:
        now = time.time()
        with self.connect() as conn:
            conn.execute("INSERT INTO models(name,created_at,updated_at) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET updated_at=excluded.updated_at", (name, now, now))
            return int(conn.execute("SELECT id FROM models WHERE name=?", (name,)).fetchone()[0])

    def bind_model(self, provider: str, model: str, verified: bool = False) -> None:
        pid = self.provider_id(provider)
        mid = self.upsert_model(model)
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO provider_models(provider_id,model_id,verified,verified_at) VALUES(?,?,?,?)
                ON CONFLICT(provider_id,model_id) DO UPDATE SET verified=excluded.verified,verified_at=excluded.verified_at
            """, (pid, mid, int(verified), time.time() if verified else None))

    def set_capability(self, provider: str, capability: str, declared: bool | None, detected: bool | None, verified: bool, model: str | None = None) -> None:
        pid = self.provider_id(provider)
        mid = self.upsert_model(model) if model else None
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO capabilities(provider_id,model_id,name,declared,detected,verified,verified_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(provider_id,model_id,name) DO UPDATE SET declared=excluded.declared,
                detected=excluded.detected,verified=excluded.verified,verified_at=excluded.verified_at
            """, (pid, mid, capability, declared, detected, int(verified), time.time() if verified else None))

    def record_probe(self, provider: str, probe_type: str, ok: bool, latency_ms: float | None = None, model: str | None = None, status_code: int | None = None, error_class: str | None = None, error: str | None = None, response_valid: bool | None = None, started_at: float | None = None, finished_at: float | None = None) -> str:
        started = started_at if started_at is not None else time.time()
        finished = finished_at if finished_at is not None else time.time()
        pid = self.provider_id(provider)
        mid = self.upsert_model(model) if model else None
        probe_id = uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO probe_runs(id,provider_id,model_id,probe_type,ok,latency_ms,status_code,error_class,error,response_valid,started_at,finished_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """, (probe_id, pid, mid, probe_type, int(ok), latency_ms, status_code, error_class, error, None if response_valid is None else int(response_valid), started, finished))
        self.snapshot_health(provider)
        return probe_id

    def _latencies(self, provider_id: int) -> list[float]:
        with self.connect() as conn:
            rows = conn.execute("SELECT latency_ms FROM probe_runs WHERE provider_id=? AND ok=1 AND latency_ms IS NOT NULL ORDER BY finished_at DESC LIMIT 100", (provider_id,)).fetchall()
        return [float(row[0]) for row in rows]

    def health(self, provider: str) -> ProviderHealth:
        pid = self.provider_id(provider)
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) attempts,SUM(CASE WHEN ok=1 THEN 1 ELSE 0 END) successes,SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) failures,MAX(finished_at) updated_at FROM probe_runs WHERE provider_id=?", (pid,)).fetchone()
            last = conn.execute("SELECT error,error_class FROM probe_runs WHERE provider_id=? AND ok=0 ORDER BY finished_at DESC LIMIT 1", (pid,)).fetchone()
            recent = conn.execute("SELECT ok FROM probe_runs WHERE provider_id=? ORDER BY finished_at DESC LIMIT 10", (pid,)).fetchall()
        attempts, successes, failures = int(row["attempts"] or 0), int(row["successes"] or 0), int(row["failures"] or 0)
        latencies = self._latencies(pid)
        avg = statistics.mean(latencies) if latencies else None
        p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else None
        streak = 0
        for item in recent:
            if int(item[0]) == 0: streak += 1
            else: break
        cooldown = 0.0
        if streak >= 3:
            cooldown = time.time() + min(60.0 * (2 ** min(streak - 3, 3)), 900.0)
        return ProviderHealth(provider, attempts, successes, failures, avg, p95, None if last is None else last[0], None if last is None else last[1], streak, cooldown, float(row["updated_at"] or 0.0))

    def snapshot_health(self, provider: str) -> None:
        pid = self.provider_id(provider)
        current = self.health(provider)
        status = "COOLDOWN" if current.cooldown_until > time.time() else ("DEGRADED" if current.attempts and current.success_rate < 0.7 else "ACTIVE")
        with self.connect() as conn:
            conn.execute("INSERT INTO health_snapshots(provider_id,attempts,successes,failures,avg_latency_ms,p95_latency_ms,score,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (pid,current.attempts,current.successes,current.failures,current.avg_latency_ms,current.p95_latency_ms,current.score,status,time.time()))
            conn.execute("UPDATE providers SET status=?,updated_at=? WHERE id=?", (status,time.time(),pid))
        if current.consecutive_failures >= 3:
            from .rocksoul_control import ProviderControlStore
            control = ProviderControlStore(self)
            state = control.get(provider)
            if state.state not in {"QUARANTINED", "PROBING"}:
                control.quarantine(provider, f"failure_streak:{current.consecutive_failures}")

    def route_candidates(self, model: str, providers: Sequence[str] | None = None, verified_only: bool = False, capabilities: Sequence[str] | None = None) -> list[RouteCandidate]:
        model_id = self.upsert_model(model)
        params: list[Any] = [model_id]
        sql = "SELECT p.name,pm.verified,p.active_by_default,p.needs_auth FROM providers p JOIN provider_models pm ON pm.provider_id=p.id WHERE pm.model_id=?"
        if providers:
            marks = ",".join("?" for _ in providers); sql += f" AND p.name IN ({marks})"; params.extend(providers)
        if verified_only: sql += " AND pm.verified=1"
        with self.connect() as conn: rows = conn.execute(sql, params).fetchall()
        result=[]
        from .rocksoul_control import ProviderControlStore
        control = ProviderControlStore(self)
        now = time.time()
        for row in rows:
            name=row["name"]
            lifecycle = control.get(name)
            if lifecycle.blocked:
                continue
            health=self.health(name)
            if health.cooldown_until > now: continue
            if capabilities:
                with self.connect() as conn:
                    for cap in capabilities:
                        ok = conn.execute("SELECT 1 FROM capabilities WHERE provider_id=(SELECT id FROM providers WHERE name=?) AND (model_id=? OR model_id IS NULL) AND name=? AND verified=1 ORDER BY model_id DESC LIMIT 1", (name,model_id,cap)).fetchone()
                        if not ok: break
                    else: ok = True
                if ok is not True: continue
            score=health.score + (12 if row["verified"] else 0) + (4 if row["active_by_default"] else 0) - (3 if row["needs_auth"] else 0)
            result.append(RouteCandidate(name,score,bool(row["verified"]),health.score,health.avg_latency_ms))
        result.sort(key=lambda item:(-item.score,item.provider)); return result

    def record_route(self, model: str, candidates: Sequence[RouteCandidate], selected: str | None, reasons: Sequence[str] = ()) -> None:
        mid=self.upsert_model(model); sid=self.provider_id(selected) if selected else None
        payload=[{"provider":c.provider,"score":c.score,"model_verified":c.model_verified,"health_score":c.health_score,"avg_latency_ms":c.avg_latency_ms} for c in candidates]
        with self.connect() as conn: conn.execute("INSERT INTO route_decisions(id,model_id,selected_provider_id,candidates_json,reason_json,created_at) VALUES(?,?,?,?,?,?)", (uuid.uuid4().hex,mid,sid,json.dumps(payload),json.dumps(list(reasons)),time.time()))

    def migrate_legacy_json(self, registry_json: Path | None = None, health_json: Path | None = None) -> dict[str,int]:
        imported={"providers":0,"models":0,"health":0}; registry_path=registry_json or (ROOT/"intelligence"/"registry.json"); health_path=health_json or (ROOT/"intelligence"/"health.json")
        if registry_path.exists():
            try:
                data=json.loads(registry_path.read_text(encoding="utf-8"))
                for value in data.get("providers",{}).values():
                    name=str(value.get("name",""));
                    if not name: continue
                    self.upsert_provider(name,value.get("url"),value.get("working"),value.get("active_by_default"),bool(value.get("needs_auth",False))); imported["providers"]+=1
                    for model in value.get("models",[]): self.bind_model(name,str(model),False); imported["models"]+=1
                for model, bindings in data.get("models",{}).items():
                    for binding in bindings:
                        provider=str(binding.get("provider",""))
                        if provider: self.bind_model(provider, model, bool(binding.get("verified",False)))
            except (OSError,ValueError,TypeError): pass
        if health_path.exists():
            try:
                data=json.loads(health_path.read_text(encoding="utf-8"))
                for provider,value in data.items():
                    for _ in range(int(value.get("successes",0))): self.record_probe(provider,"legacy",True,value.get("last_latency_ms"))
                    for _ in range(int(value.get("failures",0))): self.record_probe(provider,"legacy",False,error_class=value.get("last_error_class"),error=value.get("last_error"))
                    imported["health"]+=1
            except (OSError,ValueError,TypeError): pass
        return imported


class DBRouter:
    def __init__(self, db: RocksoulDB | None = None) -> None:
        self.db=db or RocksoulDB()

    def select(self, model: str, providers: Sequence[str] | None = None, capabilities: Sequence[str] | None = None) -> RouteCandidate | None:
        candidates=self.db.route_candidates(model,providers,capabilities=capabilities)
        selected=candidates[0] if candidates else None
        reasons=["model_verified","health_score","latency_score"]+[f"capability:{x}" for x in (capabilities or ())]
        self.db.record_route(model,candidates,selected.provider if selected else None,reasons)
        return selected


def discover() -> int:
    from .Provider import ProviderLoader
    db=RocksoulDB(); count=0
    for name in ProviderLoader.names:
        db.upsert_provider(name)
        count+=1
    return count


def migrate() -> dict[str,int]:
    return RocksoulDB().migrate_legacy_json()


def main() -> None:
    parser=argparse.ArgumentParser(description="ROCKSOUL SQLite intelligence engine")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("discover"); sub.add_parser("migrate")
    health=sub.add_parser("health"); health.add_argument("provider",nargs="?")
    route=sub.add_parser("route"); route.add_argument("model"); route.add_argument("--verified-only",action="store_true"); route.add_argument("--capability",action="append")
    sub.add_parser("status")
    args=parser.parse_args(); db=RocksoulDB()
    if args.command=="discover": print(json.dumps({"providers":discover(),"db":str(db.path)},indent=2))
    elif args.command=="migrate": print(json.dumps({"migrated":migrate(),"db":str(db.path)},indent=2))
    elif args.command=="health":
        if args.provider:
            names=[args.provider]
        else:
            with db.connect() as conn:
                names=[r["name"] for r in conn.execute("SELECT name FROM providers ORDER BY name").fetchall()]
        print(json.dumps([{ "provider":n, "score":round((h:=db.health(n)).score,2), "attempts":h.attempts, "success_rate":round(h.success_rate*100,2), "avg_latency_ms":h.avg_latency_ms, "status":"COOLDOWN" if h.cooldown_until>time.time() else ("DEGRADED" if h.attempts and h.success_rate<.7 else "ACTIVE") } for n in names],indent=2))
    elif args.command=="route": print(json.dumps([{"provider":c.provider,"score":round(c.score,2),"model_verified":c.model_verified,"health_score":round(c.health_score,2),"avg_latency_ms":c.avg_latency_ms} for c in db.route_candidates(args.model,verified_only=args.verified_only,capabilities=args.capability)],indent=2))
    elif args.command=="status":
        with db.connect() as conn:
            counts={key:int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for key,table in {"providers":"providers","models":"models","provider_models":"provider_models","capabilities":"capabilities","probes":"probe_runs","route_decisions":"route_decisions"}.items()}
        print(json.dumps({"db":str(db.path),"schema_version":SCHEMA_VERSION,**counts},indent=2))


if __name__=="__main__":
    main()