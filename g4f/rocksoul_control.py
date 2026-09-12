from __future__ import annotations

"""Persistent provider control state for the ROCKSOUL product layer."""

import time
import uuid
from dataclasses import dataclass

from .rocksoul_db import RocksoulDB

STATES = ("ACTIVE", "DEGRADED", "QUARANTINED", "PROBING", "RE_ADMITTED")

@dataclass(frozen=True, slots=True)
class ProviderControl:
    provider: str
    state: str
    reason: str | None
    state_until: float
    updated_at: float

    @property
    def blocked(self) -> bool:
        """Return whether normal request routing must exclude this provider.

        Recovery probes are operator-controlled traffic. A provider in PROBING
        must therefore stay isolated from normal execution until the recovery
        manager explicitly transitions it to RE_ADMITTED.
        """
        return self.state in {"QUARANTINED", "PROBING"} or (
            self.state == "DEGRADED" and self.state_until > time.time()
        )

class ProviderControlStore:
    """Persistent provider lifecycle independent from health counters."""
    def __init__(self, db: RocksoulDB | None = None) -> None:
        self.db = db or RocksoulDB()
        with self.db.connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS provider_controls (
                provider_id INTEGER PRIMARY KEY,
                state TEXT NOT NULL,
                reason TEXT,
                state_until REAL NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                FOREIGN KEY(provider_id) REFERENCES providers(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS provider_control_events (
                id TEXT PRIMARY KEY,
                provider_id INTEGER NOT NULL,
                from_state TEXT,
                to_state TEXT NOT NULL,
                reason TEXT,
                state_until REAL NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY(provider_id) REFERENCES providers(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_provider_control_events_provider_time
              ON provider_control_events(provider_id, created_at DESC);
            """)

    def _raw_get(self, provider: str) -> ProviderControl:
        pid = self.db.provider_id(provider)
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT state,reason,state_until,updated_at FROM provider_controls WHERE provider_id=?",
                (pid,),
            ).fetchone()
            if row is None:
                now = time.time()
                conn.execute(
                    "INSERT INTO provider_controls(provider_id,state,reason,state_until,updated_at) VALUES(?,?,?,?,?)",
                    (pid, "ACTIVE", None, 0.0, now),
                )
                return ProviderControl(provider, "ACTIVE", None, 0.0, now)
            return ProviderControl(provider, str(row[0]), row[1], float(row[2]), float(row[3]))

    def get(self, provider: str) -> ProviderControl:
        current = self._raw_get(provider)
        if current.state == "DEGRADED" and current.state_until <= time.time():
            return self.transition(provider, "ACTIVE", "cooldown_expired")
        return current

    def transition(self, provider: str, state: str, reason: str | None = None, state_until: float = 0.0) -> ProviderControl:
        if state not in STATES:
            raise ValueError(f"Unsupported provider state: {state}")
        current = self._raw_get(provider)
        now = time.time()
        expiry = max(0.0, state_until)
        pid = self.db.provider_id(provider)
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO provider_controls(provider_id,state,reason,state_until,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(provider_id) DO UPDATE SET state=excluded.state,
                     reason=excluded.reason,state_until=excluded.state_until,updated_at=excluded.updated_at""",
                (pid, state, reason, expiry, now),
            )
            conn.execute(
                """INSERT INTO provider_control_events(id,provider_id,from_state,to_state,reason,state_until,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (uuid.uuid4().hex, pid, current.state, state, reason, expiry, now),
            )
        return ProviderControl(provider, state, reason, expiry, now)

    def cooldown(self, provider: str, seconds: float, reason: str = "rate_limit") -> ProviderControl:
        return self.transition(provider, "DEGRADED", reason, time.time() + max(0.0, seconds))

    def quarantine(self, provider: str, reason: str = "manual_quarantine") -> ProviderControl:
        return self.transition(provider, "QUARANTINED", reason)

    def begin_recovery(self, provider: str, reason: str = "recovery_probe") -> ProviderControl:
        return self.transition(provider, "PROBING", reason)

    def re_admit(self, provider: str, reason: str = "recovery_success") -> ProviderControl:
        return self.transition(provider, "RE_ADMITTED", reason)

    def active(self, provider: str, reason: str = "manual_reactivate") -> ProviderControl:
        return self.transition(provider, "ACTIVE", reason)

    def list(self, provider: str | None = None) -> list[ProviderControl]:
        with self.db.connect() as conn:
            sql = "SELECT p.name,COALESCE(c.state,'ACTIVE'),c.reason,COALESCE(c.state_until,0),COALESCE(c.updated_at,0) FROM providers p LEFT JOIN provider_controls c ON c.provider_id=p.id"
            args: tuple[object, ...] = ()
            if provider:
                sql += " WHERE p.name=?"
                args = (provider,)
            sql += " ORDER BY p.name"
            rows = conn.execute(sql, args).fetchall()
        return [ProviderControl(str(r[0]), str(r[1]), r[2], float(r[3]), float(r[4])) for r in rows]

    def history(self, provider: str, limit: int = 20) -> list[dict[str, object]]:
        pid = self.db.provider_id(provider)
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT from_state,to_state,reason,state_until,created_at FROM provider_control_events WHERE provider_id=? ORDER BY created_at DESC LIMIT ?",
                (pid, max(1, min(100, int(limit)))),
            ).fetchall()
        return [dict(row) for row in rows]
