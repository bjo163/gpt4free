from __future__ import annotations

"""Production ROCKSOUL Mesh coordination primitives.

Transport-neutral node coordination with explicit lifecycle, replay-resistant
HMAC authentication, bounded leases, failure isolation, and auditable events.
"""

import hashlib
import hmac
import ipaddress
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

from .rocksoul_db import RocksoulDB

MESH_STATES = ("REGISTERED", "ACTIVE", "DEGRADED", "DRAINING", "QUARANTINED", "OFFLINE")

MESH_SCHEMA = """
CREATE TABLE IF NOT EXISTS mesh_nodes (
 node_id TEXT PRIMARY KEY, endpoint TEXT NOT NULL, capabilities_json TEXT NOT NULL,
 state TEXT NOT NULL, weight REAL NOT NULL DEFAULT 1.0, health REAL NOT NULL DEFAULT 100.0,
 latency_ms REAL, last_heartbeat REAL, consecutive_failures INTEGER NOT NULL DEFAULT 0,
 inflight INTEGER NOT NULL DEFAULT 0, reason TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mesh_leases (
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, node_id TEXT NOT NULL,
 status TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
 finished_at REAL, error TEXT,
 FOREIGN KEY(node_id) REFERENCES mesh_nodes(node_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS mesh_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT, event TEXT NOT NULL,
 detail_json TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mesh_auth_nonces (
 node_id TEXT NOT NULL, nonce TEXT NOT NULL, seen_at REAL NOT NULL,
 PRIMARY KEY(node_id, nonce)
);
CREATE INDEX IF NOT EXISTS idx_mesh_nodes_state ON mesh_nodes(state);
CREATE INDEX IF NOT EXISTS idx_mesh_leases_node_status ON mesh_leases(node_id,status);
CREATE INDEX IF NOT EXISTS idx_mesh_events_node_time ON mesh_events(node_id,created_at DESC);
"""

class MeshError(RuntimeError): pass
class MeshAuthError(MeshError): pass
class MeshSecurityError(MeshError): pass
class MeshStateError(MeshError): pass

@dataclass(frozen=True, slots=True)
class MeshPolicy:
    heartbeat_ttl: float = 60.0
    lease_ttl: float = 30.0
    auth_clock_skew: float = 60.0
    nonce_ttl: float = 600.0
    failure_threshold: int = 3
    max_inflight_per_node: int = 4
    allow_insecure_local: bool = False

@dataclass(frozen=True, slots=True)
class MeshAuthContext:
    timestamp: float
    nonce: str
    signature: str

@dataclass(frozen=True, slots=True)
class MeshNode:
    node_id: str
    endpoint: str
    capabilities: tuple[str, ...]
    state: str
    weight: float
    health: float
    latency_ms: float | None
    last_heartbeat: float | None
    consecutive_failures: int
    inflight: int
    reason: str | None
    created_at: float
    updated_at: float

    @property
    def score(self) -> float:
        latency = 0.0 if self.latency_ms is None else min(30.0, max(0.0, self.latency_ms) / 100.0)
        load = min(25.0, max(0, self.inflight) * 5.0)
        failures = min(30.0, max(0, self.consecutive_failures) * 10.0)
        return max(0.0, self.health * self.weight - latency - load - failures)

@dataclass(frozen=True, slots=True)
class MeshLease:
    lease_id: str
    request_id: str
    node_id: str
    status: str
    created_at: float
    expires_at: float
    finished_at: float | None = None
    error: str | None = None

def _payload(value: Mapping[str, Any] | None) -> str:
    return json.dumps(value or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)

def _message(action: str, node_id: str, timestamp: float, nonce: str, payload: Mapping[str, Any] | None) -> bytes:
    return json.dumps({
        "action": action, "node_id": node_id, "timestamp": float(timestamp),
        "nonce": nonce, "payload": json.loads(_payload(payload)),
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def sign_mesh_message(secret: bytes | str, action: str, node_id: str, timestamp: float, nonce: str,
                      payload: Mapping[str, Any] | None = None) -> str:
    key = secret.encode() if isinstance(secret, str) else secret
    return hmac.new(key, _message(action, node_id, timestamp, nonce, payload), hashlib.sha256).hexdigest()

def make_mesh_auth(secret: bytes | str, action: str, node_id: str, payload: Mapping[str, Any] | None = None,
                   *, timestamp: float | None = None, nonce: str | None = None) -> MeshAuthContext:
    ts = time.time() if timestamp is None else float(timestamp)
    nonce = nonce or secrets.token_hex(16)
    return MeshAuthContext(ts, nonce, sign_mesh_message(secret, action, node_id, ts, nonce, payload))

def validate_mesh_endpoint(endpoint: str, allow_insecure_local: bool = False) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise MeshSecurityError("mesh endpoint must be an http(s) URL with a hostname")
    if parsed.username or parsed.password or parsed.fragment:
        raise MeshSecurityError("mesh endpoint must not contain credentials or fragments")
    if parsed.scheme == "http":
        host = parsed.hostname.lower()
        local = host == "localhost"
        if not local:
            try:
                addr = ipaddress.ip_address(host)
                local = addr.is_private or addr.is_loopback
            except ValueError:
                local = False
        if not (allow_insecure_local and local):
            raise MeshSecurityError("plaintext http requires explicit local/private development policy")
    return endpoint

class MeshStore:
    def __init__(self, db: RocksoulDB, *, secret: bytes | str | Mapping[str, bytes | str] | None = None,
                 policy: MeshPolicy | None = None) -> None:
        self.db = db
        self.policy = policy or MeshPolicy()
        self._shared: bytes | None = None
        self._keys: dict[str, bytes] = {}
        if isinstance(secret, Mapping):
            self._keys = {str(k): v.encode() if isinstance(v, str) else v for k, v in secret.items()}
        elif isinstance(secret, str):
            self._shared = secret.encode()
        else:
            self._shared = secret
        with self.db.connect() as conn:
            conn.executescript(MESH_SCHEMA)

    def _event(self, node_id: str | None, event: str, detail: Mapping[str, Any] | None = None,
               *, now: float | None = None) -> None:
        now = time.time() if now is None else float(now)
        with self.db.connect() as conn:
            conn.execute("INSERT INTO mesh_events(node_id,event,detail_json,created_at) VALUES(?,?,?,?)",
                         (node_id, event, _payload(detail), now))

    def verify_auth(self, action: str, node_id: str, payload: Mapping[str, Any] | None,
                    auth: MeshAuthContext, *, now: float | None = None) -> None:
        key = self._keys.get(node_id) or self._shared
        if not key:
            raise MeshAuthError(f"mesh secret not configured for node: {node_id}")
        now = time.time() if now is None else float(now)
        if abs(now - auth.timestamp) > max(1.0, self.policy.auth_clock_skew):
            raise MeshAuthError("mesh authentication timestamp outside allowed clock skew")
        expected = sign_mesh_message(key, action, node_id, auth.timestamp, auth.nonce, payload)
        if not hmac.compare_digest(expected, auth.signature):
            raise MeshAuthError("invalid mesh authentication signature")
        with self.db.connect() as conn:
            conn.execute("DELETE FROM mesh_auth_nonces WHERE seen_at<?", (now - max(1.0, self.policy.nonce_ttl),))
            try:
                conn.execute("INSERT INTO mesh_auth_nonces(node_id,nonce,seen_at) VALUES(?,?,?)",
                             (node_id, auth.nonce, now))
            except Exception as exc:
                if "UNIQUE constraint failed" in str(exc):
                    raise MeshAuthError("replayed mesh authentication nonce") from exc
                raise

    @staticmethod
    def _node(row: Any) -> MeshNode:
        return MeshNode(
            str(row["node_id"]), str(row["endpoint"]),
            tuple(sorted(str(x) for x in json.loads(row["capabilities_json"]))),
            str(row["state"]), float(row["weight"]), float(row["health"]),
            None if row["latency_ms"] is None else float(row["latency_ms"]),
            None if row["last_heartbeat"] is None else float(row["last_heartbeat"]),
            int(row["consecutive_failures"]), int(row["inflight"]),
            None if row["reason"] is None else str(row["reason"]),
            float(row["created_at"]), float(row["updated_at"]),
        )

    def get(self, node_id: str) -> MeshNode | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM mesh_nodes WHERE node_id=?", (node_id,)).fetchone()
        return None if row is None else self._node(row)

    def list_nodes(self) -> list[MeshNode]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM mesh_nodes ORDER BY node_id").fetchall()
        return [self._node(r) for r in rows]

    def _register(self, node_id: str, endpoint: str, capabilities: Iterable[str], weight: float, now: float) -> MeshNode:
        if not node_id.strip():
            raise MeshStateError("node_id must not be empty")
        endpoint = validate_mesh_endpoint(endpoint, self.policy.allow_insecure_local)
        caps = tuple(sorted({str(x).strip() for x in capabilities if str(x).strip()}))
        weight = max(0.1, min(float(weight), 10.0))
        with self.db.connect() as conn:
            old = conn.execute("SELECT created_at FROM mesh_nodes WHERE node_id=?", (node_id,)).fetchone()
            created = now if old is None else float(old["created_at"])
            conn.execute("""
                INSERT INTO mesh_nodes(node_id,endpoint,capabilities_json,state,weight,health,latency_ms,
                 last_heartbeat,consecutive_failures,inflight,reason,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(node_id) DO UPDATE SET endpoint=excluded.endpoint,
                 capabilities_json=excluded.capabilities_json,weight=excluded.weight,updated_at=excluded.updated_at
            """, (node_id, endpoint, json.dumps(caps), "REGISTERED", weight, 100.0, None, None, 0, 0,
                  "awaiting_heartbeat", created, now))
        self._event(node_id, "node_registered", {"endpoint": endpoint, "capabilities": caps, "weight": weight}, now=now)
        return self.get(node_id)  # type: ignore[return-value]

    def register_node(self, node_id: str, endpoint: str, capabilities: Iterable[str] = (), *,
                      weight: float = 1.0, auth: MeshAuthContext, now: float | None = None) -> MeshNode:
        now = time.time() if now is None else float(now)
        caps = tuple(sorted({str(x).strip() for x in capabilities if str(x).strip()}))
        payload = {"endpoint": endpoint, "capabilities": caps, "weight": float(weight)}
        self.verify_auth("register", node_id, payload, auth, now=now)
        return self._register(node_id, endpoint, caps, weight, now)

    def register_operator_node(self, node_id: str, endpoint: str, capabilities: Iterable[str] = (), *,
                               weight: float = 1.0, now: float | None = None) -> MeshNode:
        return self._register(node_id, endpoint, capabilities, weight, time.time() if now is None else float(now))

    def heartbeat(self, node_id: str, *, health: float = 100.0, latency_ms: float | None = None,
                  auth: MeshAuthContext, now: float | None = None) -> MeshNode:
        now = time.time() if now is None else float(now)
        payload = {"health": float(health), "latency_ms": None if latency_ms is None else float(latency_ms)}
        self.verify_auth("heartbeat", node_id, payload, auth, now=now)
        with self.db.connect() as conn:
            row = conn.execute("SELECT state FROM mesh_nodes WHERE node_id=?", (node_id,)).fetchone()
            if row is None:
                raise MeshStateError(f"unknown mesh node: {node_id}")
            state = str(row["state"])
            next_state = state if state in {"DRAINING", "QUARANTINED"} else "ACTIVE"
            conn.execute("""UPDATE mesh_nodes SET health=?,latency_ms=?,last_heartbeat=?,
                consecutive_failures=0,state=?,reason=?,updated_at=? WHERE node_id=?""",
                (max(0.0, min(float(health), 100.0)),
                 None if latency_ms is None else max(0.0, float(latency_ms)), now, next_state,
                 "heartbeat_ok" if next_state == "ACTIVE" else state.lower(), now, node_id))
        self._event(node_id, "heartbeat", payload | {"state": next_state}, now=now)
        return self.get(node_id)  # type: ignore[return-value]

    def set_state(self, node_id: str, state: str, reason: str, *, now: float | None = None) -> MeshNode:
        if state not in MESH_STATES:
            raise MeshStateError(f"invalid mesh state: {state}")
        now = time.time() if now is None else float(now)
        with self.db.connect() as conn:
            if conn.execute("SELECT 1 FROM mesh_nodes WHERE node_id=?", (node_id,)).fetchone() is None:
                raise MeshStateError(f"unknown mesh node: {node_id}")
            conn.execute("UPDATE mesh_nodes SET state=?,reason=?,updated_at=? WHERE node_id=?",
                         (state, reason, now, node_id))
        self._event(node_id, "state_changed", {"state": state, "reason": reason}, now=now)
        return self.get(node_id)  # type: ignore[return-value]

    def record_failure(self, node_id: str, reason: str, *, now: float | None = None) -> MeshNode:
        now = time.time() if now is None else float(now)
        with self.db.connect() as conn:
            row = conn.execute("SELECT consecutive_failures,state FROM mesh_nodes WHERE node_id=?", (node_id,)).fetchone()
            if row is None:
                raise MeshStateError(f"unknown mesh node: {node_id}")
            failures = int(row["consecutive_failures"]) + 1
            state = "DRAINING" if row["state"] == "DRAINING" else (
                "QUARANTINED" if failures >= max(1, self.policy.failure_threshold) else "DEGRADED"
            )
            conn.execute("UPDATE mesh_nodes SET consecutive_failures=?,state=?,reason=?,updated_at=? WHERE node_id=?",
                         (failures, state, reason, now, node_id))
        self._event(node_id, "node_failure", {"reason": reason, "failures": failures, "state": state}, now=now)
        return self.get(node_id)  # type: ignore[return-value]

    def refresh_stale(self, *, now: float | None = None) -> list[str]:
        now = time.time() if now is None else float(now)
        cutoff = now - max(1.0, self.policy.heartbeat_ttl)
        changed: list[str] = []
        with self.db.connect() as conn:
            rows = conn.execute("""SELECT node_id FROM mesh_nodes
                WHERE state IN ('REGISTERED','ACTIVE','DEGRADED')
                AND COALESCE(last_heartbeat,created_at)<? ORDER BY node_id""", (cutoff,)).fetchall()
            for row in rows:
                node_id = str(row["node_id"])
                conn.execute("UPDATE mesh_nodes SET state='OFFLINE',reason='heartbeat_expired',updated_at=? WHERE node_id=?",
                             (now, node_id))
                changed.append(node_id)
        for node_id in changed:
            self._event(node_id, "heartbeat_expired", {"state": "OFFLINE"}, now=now)
        return changed

    def expire_leases(self, *, now: float | None = None) -> list[str]:
        now = time.time() if now is None else float(now)
        expired: list[tuple[str, str]] = []
        with self.db.connect() as conn:
            rows = conn.execute("SELECT id,node_id FROM mesh_leases WHERE status='ACTIVE' AND expires_at<=? ORDER BY id",
                                (now,)).fetchall()
            for row in rows:
                lease_id, node_id = str(row["id"]), str(row["node_id"])
                conn.execute("UPDATE mesh_leases SET status='EXPIRED',finished_at=?,error='lease_expired' WHERE id=?",
                             (now, lease_id))
                conn.execute("UPDATE mesh_nodes SET inflight=MAX(inflight-1,0),updated_at=? WHERE node_id=?",
                             (now, node_id))
                expired.append((lease_id, node_id))
        for lease_id, node_id in expired:
            self._event(node_id, "lease_expired", {"lease_id": lease_id}, now=now)
        return [x[0] for x in expired]

    def _eligible(self, conn: Any, capabilities: Sequence[str]) -> list[MeshNode]:
        required = {str(x) for x in capabilities if str(x)}
        rows = conn.execute("SELECT * FROM mesh_nodes WHERE state='ACTIVE' AND inflight<? ORDER BY node_id",
                            (max(1, self.policy.max_inflight_per_node),)).fetchall()
        nodes = [self._node(r) for r in rows if required.issubset(set(json.loads(r["capabilities_json"])))]
        return sorted(nodes, key=lambda n: (-n.score, n.node_id))

    def select(self, capabilities: Sequence[str] = (), *, now: float | None = None) -> MeshNode | None:
        now = time.time() if now is None else float(now)
        self.expire_leases(now=now)
        self.refresh_stale(now=now)
        with self.db.connect() as conn:
            nodes = self._eligible(conn, capabilities)
        return nodes[0] if nodes else None

    def acquire_lease(self, request_id: str, capabilities: Sequence[str] = (), *, ttl: float | None = None,
                      now: float | None = None) -> MeshLease | None:
        if not request_id.strip():
            raise MeshStateError("request_id must not be empty")
        now = time.time() if now is None else float(now)
        self.expire_leases(now=now)
        self.refresh_stale(now=now)
        ttl = max(1.0, self.policy.lease_ttl if ttl is None else float(ttl))
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute("SELECT * FROM mesh_leases WHERE request_id=?", (request_id,)).fetchone()
            if old:
                return MeshLease(str(old["id"]), str(old["request_id"]), str(old["node_id"]), str(old["status"]),
                                 float(old["created_at"]), float(old["expires_at"]),
                                 None if old["finished_at"] is None else float(old["finished_at"]), old["error"])
            nodes = self._eligible(conn, capabilities)
            if not nodes:
                return None
            node = nodes[0]
            lease_id, expires = uuid.uuid4().hex, now + ttl
            conn.execute("INSERT INTO mesh_leases(id,request_id,node_id,status,created_at,expires_at) VALUES(?,?,?,?,?,?)",
                         (lease_id, request_id, node.node_id, "ACTIVE", now, expires))
            conn.execute("UPDATE mesh_nodes SET inflight=inflight+1,updated_at=? WHERE node_id=?", (now, node.node_id))
        self._event(node.node_id, "lease_acquired",
                    {"lease_id": lease_id, "request_id": request_id, "capabilities": tuple(capabilities),
                     "expires_at": expires}, now=now)
        return MeshLease(lease_id, request_id, node.node_id, "ACTIVE", now, expires)

    def release_lease(self, lease_id: str, *, success: bool, latency_ms: float | None = None,
                      error: str | None = None, now: float | None = None) -> MeshLease:
        now = time.time() if now is None else float(now)
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM mesh_leases WHERE id=?", (lease_id,)).fetchone()
            if row is None:
                raise MeshStateError(f"unknown mesh lease: {lease_id}")
            if row["status"] != "ACTIVE":
                return MeshLease(str(row["id"]), str(row["request_id"]), str(row["node_id"]), str(row["status"]),
                                 float(row["created_at"]), float(row["expires_at"]),
                                 None if row["finished_at"] is None else float(row["finished_at"]), row["error"])
            node_id = str(row["node_id"])
            status = "SUCCEEDED" if success else "FAILED"
            conn.execute("UPDATE mesh_leases SET status=?,finished_at=?,error=? WHERE id=?", (status, now, error, lease_id))
            conn.execute("""UPDATE mesh_nodes SET inflight=MAX(inflight-1,0),
                latency_ms=COALESCE(?,latency_ms),updated_at=? WHERE node_id=?""",
                (None if latency_ms is None else max(0.0, float(latency_ms)), now, node_id))
        if success:
            self._event(node_id, "lease_succeeded", {"lease_id": lease_id, "latency_ms": latency_ms}, now=now)
        else:
            self.record_failure(node_id, error or "lease_failed", now=now)
            self._event(node_id, "lease_failed", {"lease_id": lease_id, "error": error}, now=now)
        return MeshLease(lease_id, str(row["request_id"]), node_id, status,
                         float(row["created_at"]), float(row["expires_at"]), now, error)

    def events(self, node_id: str | None = None, *, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        with self.db.connect() as conn:
            if node_id:
                rows = conn.execute("SELECT * FROM mesh_events WHERE node_id=? ORDER BY id DESC LIMIT ?",
                                    (node_id, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM mesh_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": int(r["id"]), "node_id": r["node_id"], "event": str(r["event"]),
                 "detail": json.loads(r["detail_json"]), "created_at": float(r["created_at"])} for r in rows]

    def status(self, *, now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else float(now)
        self.expire_leases(now=now)
        self.refresh_stale(now=now)
        with self.db.connect() as conn:
            rows = conn.execute("SELECT state,COUNT(*) count FROM mesh_nodes GROUP BY state").fetchall()
            active = int(conn.execute("SELECT COUNT(*) FROM mesh_leases WHERE status='ACTIVE'").fetchone()[0])
            total = int(conn.execute("SELECT COUNT(*) FROM mesh_nodes").fetchone()[0])
        states = {state: 0 for state in MESH_STATES}
        states.update({str(r["state"]): int(r["count"]) for r in rows})
        return {"nodes": total, "states": states, "active_leases": active,
                "heartbeat_ttl": self.policy.heartbeat_ttl, "lease_ttl": self.policy.lease_ttl,
                "max_inflight_per_node": self.policy.max_inflight_per_node,
                "authentication": "hmac-sha256+node-key+timestamp+nonce"}
