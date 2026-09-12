from __future__ import annotations

"""Canonical F5 Arena benchmark foundation for ROCKSOUL.

The Arena is deliberately isolated from provider routing and Mesh coordination.
It evaluates explicit benchmark suites through a caller-supplied executor,
persists provenance and result evidence in the ROCKSOUL SQLite control plane,
and ranks targets from deterministic correctness scores. Latency is recorded as
observability evidence but is not part of the default score.
"""

import hashlib
import json
import math
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .rocksoul_db import RocksoulDB


class ArenaError(RuntimeError):
    pass


class ArenaValidationError(ArenaError, ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ArenaPolicy:
    max_cases: int = 1000
    max_weight: float = 1000.0
    allowed_evaluators: tuple[str, ...] = ("exact", "json_exact")


@dataclass(frozen=True, slots=True)
class ArenaCase:
    case_id: str
    input: Any
    expected: Any
    weight: float = 1.0
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ArenaSuite:
    name: str
    version: str
    cases: tuple[ArenaCase, ...]
    evaluator: str = "exact"
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "evaluator": self.evaluator,
            "provenance": dict(self.provenance),
            "cases": [
                {
                    "case_id": case.case_id,
                    "input": case.input,
                    "expected": case.expected,
                    "weight": case.weight,
                    "tags": list(case.tags),
                }
                for case in sorted(self.cases, key=lambda item: item.case_id)
            ],
        }

    @property
    def digest(self) -> str:
        return digest_value(self.manifest())


@dataclass(frozen=True, slots=True)
class ArenaResult:
    case_id: str
    ok: bool
    score: float
    weight: float
    latency_ms: float
    output_digest: str | None
    error: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ArenaRun:
    run_id: str
    suite_digest: str
    suite_name: str
    suite_version: str
    target: str
    score: float
    passed: int
    failed: int
    total: int
    started_at: float
    finished_at: float
    results: tuple[ArenaResult, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


ARENA_SCHEMA = """
CREATE TABLE IF NOT EXISTS arena_suites (
 digest TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 version TEXT NOT NULL,
 evaluator TEXT NOT NULL,
 manifest_json TEXT NOT NULL,
 created_at REAL NOT NULL,
 UNIQUE(name, version)
);
CREATE TABLE IF NOT EXISTS arena_runs (
 id TEXT PRIMARY KEY,
 suite_digest TEXT NOT NULL,
 target TEXT NOT NULL,
 score REAL NOT NULL,
 passed INTEGER NOT NULL,
 failed INTEGER NOT NULL,
 total INTEGER NOT NULL,
 metadata_json TEXT NOT NULL,
 started_at REAL NOT NULL,
 finished_at REAL NOT NULL,
 FOREIGN KEY(suite_digest) REFERENCES arena_suites(digest) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS arena_results (
 run_id TEXT NOT NULL,
 case_id TEXT NOT NULL,
 ok INTEGER NOT NULL,
 score REAL NOT NULL,
 weight REAL NOT NULL,
 latency_ms REAL NOT NULL,
 output_digest TEXT,
 error TEXT,
 details_json TEXT NOT NULL,
 PRIMARY KEY(run_id, case_id),
 FOREIGN KEY(run_id) REFERENCES arena_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_arena_runs_suite_time ON arena_runs(suite_digest, finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_arena_runs_target_time ON arena_runs(target, finished_at DESC);
"""


class ArenaStore:
    def __init__(self, db: RocksoulDB, policy: ArenaPolicy | None = None) -> None:
        self.db = db
        self.policy = policy or ArenaPolicy()
        with self.db.connect() as conn:
            conn.executescript(ARENA_SCHEMA)

    def validate_suite(self, suite: ArenaSuite) -> None:
        if not suite.name.strip():
            raise ArenaValidationError("suite name must not be empty")
        if not suite.version.strip():
            raise ArenaValidationError("suite version must not be empty")
        if suite.evaluator not in self.policy.allowed_evaluators:
            raise ArenaValidationError(f"unsupported evaluator: {suite.evaluator}")
        if not suite.cases:
            raise ArenaValidationError("suite must contain at least one case")
        if len(suite.cases) > self.policy.max_cases:
            raise ArenaValidationError(f"suite exceeds max_cases={self.policy.max_cases}")
        seen: set[str] = set()
        for case in suite.cases:
            case_id = case.case_id.strip()
            if not case_id:
                raise ArenaValidationError("case_id must not be empty")
            if case_id in seen:
                raise ArenaValidationError(f"duplicate case_id: {case_id}")
            seen.add(case_id)
            if not math.isfinite(case.weight) or case.weight <= 0 or case.weight > self.policy.max_weight:
                raise ArenaValidationError(f"invalid weight for {case_id}: {case.weight}")

    def register_suite(self, suite: ArenaSuite, *, now: float | None = None) -> str:
        self.validate_suite(suite)
        digest = suite.digest
        manifest_json = canonical_json(suite.manifest())
        created_at = time.time() if now is None else float(now)
        with self.db.connect() as conn:
            existing = conn.execute(
                "SELECT digest FROM arena_suites WHERE name=? AND version=?",
                (suite.name, suite.version),
            ).fetchone()
            if existing is not None and str(existing["digest"]) != digest:
                raise ArenaValidationError(
                    f"suite {suite.name!r} version {suite.version!r} already exists with different content; bump the version"
                )
            conn.execute(
                """
                INSERT INTO arena_suites(digest,name,version,evaluator,manifest_json,created_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(digest) DO NOTHING
                """,
                (digest, suite.name, suite.version, suite.evaluator, manifest_json, created_at),
            )
        return digest

    @staticmethod
    def _evaluate(evaluator: str, expected: Any, output: Any) -> tuple[bool, float, dict[str, Any]]:
        if evaluator == "exact":
            ok = output == expected
        elif evaluator == "json_exact":
            ok = canonical_json(output) == canonical_json(expected)
        else:
            raise ArenaValidationError(f"unsupported evaluator: {evaluator}")
        return ok, 1.0 if ok else 0.0, {"evaluator": evaluator}

    def run(
        self,
        suite: ArenaSuite,
        target: str,
        executor: Callable[[ArenaCase], Any],
        *,
        metadata: Mapping[str, Any] | None = None,
        now: Callable[[], float] = time.time,
        timer: Callable[[], float] = time.perf_counter,
    ) -> ArenaRun:
        target = target.strip()
        if not target:
            raise ArenaValidationError("target must not be empty")
        suite_digest = self.register_suite(suite, now=now())
        run_id = uuid.uuid4().hex
        started_at = now()
        results: list[ArenaResult] = []

        for case in sorted(suite.cases, key=lambda item: item.case_id):
            started = timer()
            output_digest: str | None = None
            try:
                output = executor(case)
                latency_ms = max(0.0, (timer() - started) * 1000.0)
                output_digest = digest_value(output)
                ok, score, details = self._evaluate(suite.evaluator, case.expected, output)
                result = ArenaResult(case.case_id, ok, score, case.weight, latency_ms, output_digest, None, details)
            except Exception as exc:
                latency_ms = max(0.0, (timer() - started) * 1000.0)
                result = ArenaResult(
                    case.case_id,
                    False,
                    0.0,
                    case.weight,
                    latency_ms,
                    output_digest,
                    f"{type(exc).__name__}: {exc}",
                    {"evaluator": suite.evaluator, "execution_error": True},
                )
            results.append(result)

        weight_total = sum(item.weight for item in results)
        weighted = sum(item.score * item.weight for item in results)
        score = 100.0 * weighted / weight_total if weight_total else 0.0
        passed = sum(1 for item in results if item.ok)
        total = len(results)
        finished_at = now()
        run = ArenaRun(
            run_id,
            suite_digest,
            suite.name,
            suite.version,
            target,
            score,
            passed,
            total - passed,
            total,
            started_at,
            finished_at,
            tuple(results),
            dict(metadata or {}),
        )
        self._persist_run(run)
        return run

    def _persist_run(self, run: ArenaRun) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO arena_runs(id,suite_digest,target,score,passed,failed,total,metadata_json,started_at,finished_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    run.run_id,
                    run.suite_digest,
                    run.target,
                    run.score,
                    run.passed,
                    run.failed,
                    run.total,
                    canonical_json(dict(run.metadata)),
                    run.started_at,
                    run.finished_at,
                ),
            )
            conn.executemany(
                """
                INSERT INTO arena_results(run_id,case_id,ok,score,weight,latency_ms,output_digest,error,details_json)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        run.run_id,
                        item.case_id,
                        int(item.ok),
                        item.score,
                        item.weight,
                        item.latency_ms,
                        item.output_digest,
                        item.error,
                        canonical_json(dict(item.details)),
                    )
                    for item in run.results
                ],
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            run = conn.execute("SELECT * FROM arena_runs WHERE id=?", (run_id,)).fetchone()
            if run is None:
                return None
            results = conn.execute(
                "SELECT * FROM arena_results WHERE run_id=? ORDER BY case_id",
                (run_id,),
            ).fetchall()
        value = dict(run)
        value["metadata"] = json.loads(value.pop("metadata_json"))
        value["results"] = []
        for row in results:
            item = dict(row)
            item["ok"] = bool(item["ok"])
            item["details"] = json.loads(item.pop("details_json"))
            value["results"].append(item)
        return value

    def list_runs(self, suite_digest: str | None = None, *, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        query = "SELECT * FROM arena_runs"
        params: list[Any] = []
        if suite_digest:
            query += " WHERE suite_digest=?"
            params.append(suite_digest)
        query += " ORDER BY finished_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        values: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            values.append(item)
        return values

    def latest_suite_digest(self) -> str | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT digest FROM arena_suites ORDER BY created_at DESC, digest DESC LIMIT 1").fetchone()
        return None if row is None else str(row["digest"])

    def leaderboard(self, suite_digest: str | None = None) -> list[dict[str, Any]]:
        suite_digest = suite_digest or self.latest_suite_digest()
        if not suite_digest:
            return []
        runs = self.list_runs(suite_digest, limit=1000)
        latest_by_target: dict[str, dict[str, Any]] = {}
        for run in runs:
            latest_by_target.setdefault(str(run["target"]), run)
        ranked = list(latest_by_target.values())
        ranked.sort(key=lambda item: (-float(item["score"]), -int(item["passed"]), str(item["target"])))
        return [
            {
                "rank": index + 1,
                "target": item["target"],
                "score": item["score"],
                "passed": item["passed"],
                "failed": item["failed"],
                "total": item["total"],
                "run_id": item["id"],
                "suite_digest": item["suite_digest"],
                "finished_at": item["finished_at"],
            }
            for index, item in enumerate(ranked)
        ]

    def status(self) -> dict[str, Any]:
        with self.db.connect() as conn:
            suites = int(conn.execute("SELECT COUNT(*) FROM arena_suites").fetchone()[0])
            runs = int(conn.execute("SELECT COUNT(*) FROM arena_runs").fetchone()[0])
            results = int(conn.execute("SELECT COUNT(*) FROM arena_results").fetchone()[0])
        return {
            "phase": "F5",
            "authority": "rocksoul_arena",
            "state": "foundation",
            "suites": suites,
            "runs": runs,
            "results": results,
            "scoring": "weighted deterministic correctness",
            "latency_role": "evidence-only",
            "legacy_arena": "compatibility-only",
        }


def run_to_dict(run: ArenaRun) -> dict[str, Any]:
    value = asdict(run)
    value["results"] = [asdict(item) for item in run.results]
    return value
