from __future__ import annotations

"""Execution-specific persistence layered on the existing ROCKSOUL SQLite store."""

import sqlite3
import time
from pathlib import Path
from typing import Any

from .rocksoul_db import RocksoulDB


EXECUTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_runs (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    model TEXT NOT NULL,
    started_at REAL NOT NULL,
    finished_at REAL,
    status TEXT NOT NULL,
    selected_provider_id INTEGER,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    final_error_class TEXT,
    FOREIGN KEY(selected_provider_id) REFERENCES providers(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS execution_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    attempt_no INTEGER NOT NULL,
    provider_id INTEGER NOT NULL,
    model_id INTEGER,
    started_at REAL NOT NULL,
    finished_at REAL NOT NULL,
    latency_ms REAL,
    status TEXT NOT NULL,
    error_class TEXT,
    error TEXT,
    response_valid INTEGER,
    UNIQUE(run_id, attempt_no),
    FOREIGN KEY(run_id) REFERENCES execution_runs(id) ON DELETE CASCADE,
    FOREIGN KEY(provider_id) REFERENCES providers(id) ON DELETE CASCADE,
    FOREIGN KEY(model_id) REFERENCES models(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_execution_runs_request ON execution_runs(request_id);
CREATE INDEX IF NOT EXISTS idx_execution_attempts_run ON execution_attempts(run_id, attempt_no);
"""


class ExecutionTraceStore:
    def __init__(self, db: RocksoulDB) -> None:
        self.db = db
        with self.db.connect() as conn:
            conn.executescript(EXECUTION_SCHEMA)

    def _ids(self, provider: str, model: str) -> tuple[int, int]:
        return self.db.provider_id(provider), self.db.upsert_model(model)

    def record_execution_run(
        self,
        request_id: str,
        model: str,
        started_at: float,
        finished_at: float | None,
        status: str,
        selected_provider: str | None,
        attempt_count: int,
        final_error_class: str | None,
    ) -> str:
        run_id = request_id
        provider_id = self.db.provider_id(selected_provider) if selected_provider else None
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO execution_runs(id,request_id,model,started_at,finished_at,status,selected_provider_id,attempt_count,final_error_class)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(request_id) DO UPDATE SET finished_at=excluded.finished_at,
                status=excluded.status,selected_provider_id=excluded.selected_provider_id,
                attempt_count=excluded.attempt_count,final_error_class=excluded.final_error_class
                """,
                (run_id, request_id, model, started_at, finished_at, status, provider_id, attempt_count, final_error_class),
            )
        return run_id

    def record_execution_attempt(
        self,
        request_id: str,
        attempt_no: int,
        provider: str,
        model: str,
        started_at: float,
        finished_at: float,
        latency_ms: float,
        status: str,
        error_class: str | None,
        error: str | None,
        response_valid: bool | None,
    ) -> None:
        provider_id, model_id = self._ids(provider, model)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO execution_runs(id,request_id,model,started_at,status,attempt_count)
                VALUES(?,?,?,?,?,?) ON CONFLICT(request_id) DO NOTHING
                """,
                (request_id, request_id, model, started_at, "running", 0),
            )
            conn.execute(
                """
                INSERT INTO execution_attempts(run_id,attempt_no,provider_id,model_id,started_at,finished_at,latency_ms,status,error_class,error,response_valid)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(run_id,attempt_no) DO UPDATE SET finished_at=excluded.finished_at,
                latency_ms=excluded.latency_ms,status=excluded.status,error_class=excluded.error_class,
                error=excluded.error,response_valid=excluded.response_valid
                """,
                (request_id, attempt_no, provider_id, model_id, started_at, finished_at, latency_ms,
                 status, error_class, error, None if response_valid is None else int(response_valid)),
            )

    def record_execution_evidence(
        self,
        provider: str,
        model: str,
        ok: bool,
        latency_ms: float,
        error_class: str | None = None,
        error: str | None = None,
    ) -> None:
        self.db.record_probe(
            provider,
            "execution",
            ok,
            latency_ms=latency_ms,
            model=model,
            error_class=error_class,
            error=error,
            response_valid=ok,
        )

    def trace(self, request_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            run = conn.execute("SELECT * FROM execution_runs WHERE request_id=?", (request_id,)).fetchone()
            if run is None:
                return None
            attempts = conn.execute(
                """
                SELECT ea.*, p.name provider, m.name model_name
                FROM execution_attempts ea
                JOIN providers p ON p.id=ea.provider_id
                LEFT JOIN models m ON m.id=ea.model_id
                WHERE ea.run_id=? ORDER BY ea.attempt_no
                """,
                (request_id,),
            ).fetchall()
        return {
            "request_id": request_id,
            "model": run["model"],
            "status": run["status"],
            "selected_provider": None if run["selected_provider_id"] is None else self.db.connect().execute("SELECT name FROM providers WHERE id=?", (run["selected_provider_id"],)).fetchone()[0],
            "attempt_count": run["attempt_count"],
            "final_error_class": run["final_error_class"],
            "attempts": [dict(row) for row in attempts],
        }
