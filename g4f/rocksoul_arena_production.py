from __future__ import annotations

"""Production benchmark contract for ROCKSOUL F5 Arena.

This module deliberately sits on top of the deterministic Arena foundation. It
adds the evidence required before benchmark results may be treated as
production-authoritative: dataset provenance, evaluator revision, split and
contamination policy, exact target identity, execution-environment evidence,
and bounded repeat-run variance.
"""

import json
import math
import re
import statistics
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping

from .rocksoul_arena import (
    ArenaCase,
    ArenaRun,
    ArenaStore,
    ArenaSuite,
    ArenaValidationError,
    canonical_json,
    digest_value,
)

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ALLOWED_SPLIT_POLICIES = {
    "public_only",
    "public_and_held_out",
    "held_out_only",
    "not_applicable",
}
_ALLOWED_NETWORK_MODES = {"offline", "restricted", "online"}


@dataclass(frozen=True, slots=True)
class ArenaDatasetProvenance:
    source: str
    revision: str
    sha256: str
    split_policy: str
    contamination_review: str
    license: str | None = None

    def manifest(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ArenaRepeatPolicy:
    runs: int = 3
    max_score_stddev: float = 5.0

    def manifest(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ArenaProductionPack:
    name: str
    version: str
    suite: ArenaSuite
    dataset: ArenaDatasetProvenance
    evaluator_revision: str
    repeat_policy: ArenaRepeatPolicy = field(default_factory=ArenaRepeatPolicy)
    environment_requirements: Mapping[str, Any] = field(default_factory=dict)
    network_requirements: Mapping[str, Any] = field(default_factory=dict)

    def manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "suite_digest": self.suite.digest,
            "suite_name": self.suite.name,
            "suite_version": self.suite.version,
            "dataset": self.dataset.manifest(),
            "evaluator": self.suite.evaluator,
            "evaluator_revision": self.evaluator_revision,
            "repeat_policy": self.repeat_policy.manifest(),
            "environment_requirements": dict(self.environment_requirements),
            "network_requirements": dict(self.network_requirements),
        }

    @property
    def digest(self) -> str:
        return digest_value(self.manifest())


@dataclass(frozen=True, slots=True)
class ArenaTargetIdentity:
    provider: str
    model: str
    revision: str
    runtime_revision: str

    def manifest(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def digest(self) -> str:
        return digest_value(self.manifest())


@dataclass(frozen=True, slots=True)
class ArenaEnvironmentEvidence:
    runtime: str
    os: str
    python: str
    network_mode: str
    region: str = "unspecified"
    extra: Mapping[str, Any] = field(default_factory=dict)

    def manifest(self) -> dict[str, Any]:
        value = asdict(self)
        value["extra"] = dict(self.extra)
        return value


@dataclass(frozen=True, slots=True)
class ArenaCampaign:
    campaign_id: str
    pack_digest: str
    target_digest: str
    target: Mapping[str, Any]
    environment: Mapping[str, Any]
    run_ids: tuple[str, ...]
    scores: tuple[float, ...]
    score_mean: float
    score_stddev: float
    variance_accepted: bool
    started_at: float
    finished_at: float


ARENA_PRODUCTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS arena_production_packs (
 digest TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 version TEXT NOT NULL,
 suite_digest TEXT NOT NULL,
 manifest_json TEXT NOT NULL,
 created_at REAL NOT NULL,
 UNIQUE(name, version)
);
CREATE TABLE IF NOT EXISTS arena_campaigns (
 id TEXT PRIMARY KEY,
 pack_digest TEXT NOT NULL,
 target_digest TEXT NOT NULL,
 target_json TEXT NOT NULL,
 environment_json TEXT NOT NULL,
 run_ids_json TEXT NOT NULL,
 scores_json TEXT NOT NULL,
 score_mean REAL NOT NULL,
 score_stddev REAL NOT NULL,
 variance_accepted INTEGER NOT NULL,
 started_at REAL NOT NULL,
 finished_at REAL NOT NULL,
 FOREIGN KEY(pack_digest) REFERENCES arena_production_packs(digest) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_arena_campaign_pack_time
 ON arena_campaigns(pack_digest, finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_arena_campaign_target_time
 ON arena_campaigns(target_digest, finished_at DESC);
"""


class ArenaProductionStore:
    def __init__(self, arena: ArenaStore) -> None:
        self.arena = arena
        with self.arena.db.connect() as conn:
            conn.executescript(ARENA_PRODUCTION_SCHEMA)

    @staticmethod
    def validate_pack(pack: ArenaProductionPack) -> None:
        if not pack.name.strip():
            raise ArenaValidationError("production pack name must not be empty")
        if not pack.version.strip():
            raise ArenaValidationError("production pack version must not be empty")
        if not pack.evaluator_revision.strip():
            raise ArenaValidationError("evaluator_revision must not be empty")

        dataset = pack.dataset
        if not dataset.source.strip():
            raise ArenaValidationError("dataset source must not be empty")
        if not dataset.revision.strip():
            raise ArenaValidationError("dataset revision must not be empty")
        if not _SHA256_RE.fullmatch(dataset.sha256.strip()):
            raise ArenaValidationError("dataset sha256 must be exactly 64 hexadecimal characters")
        if dataset.split_policy not in _ALLOWED_SPLIT_POLICIES:
            raise ArenaValidationError(f"unsupported split_policy: {dataset.split_policy}")
        if not dataset.contamination_review.strip():
            raise ArenaValidationError("contamination_review must not be empty")

        repeat = pack.repeat_policy
        if repeat.runs < 2 or repeat.runs > 100:
            raise ArenaValidationError("repeat_policy.runs must be between 2 and 100")
        if not math.isfinite(repeat.max_score_stddev) or repeat.max_score_stddev < 0:
            raise ArenaValidationError("repeat_policy.max_score_stddev must be a finite non-negative number")
        if not pack.environment_requirements:
            raise ArenaValidationError("environment_requirements must be explicit for a production pack")
        if not pack.network_requirements:
            raise ArenaValidationError("network_requirements must be explicit for a production pack")

    @staticmethod
    def validate_target(target: ArenaTargetIdentity) -> None:
        for field_name, value in target.manifest().items():
            if not str(value).strip():
                raise ArenaValidationError(f"target {field_name} must not be empty")

    @staticmethod
    def validate_environment(environment: ArenaEnvironmentEvidence) -> None:
        if not environment.runtime.strip():
            raise ArenaValidationError("environment runtime must not be empty")
        if not environment.os.strip():
            raise ArenaValidationError("environment os must not be empty")
        if not environment.python.strip():
            raise ArenaValidationError("environment python must not be empty")
        if environment.network_mode not in _ALLOWED_NETWORK_MODES:
            raise ArenaValidationError(f"unsupported network_mode: {environment.network_mode}")

    def register_pack(self, pack: ArenaProductionPack, *, now: float | None = None) -> str:
        self.validate_pack(pack)
        suite_digest = self.arena.register_suite(pack.suite, now=now)
        digest = pack.digest
        manifest_json = canonical_json(pack.manifest())
        created_at = time.time() if now is None else float(now)
        with self.arena.db.connect() as conn:
            existing = conn.execute(
                "SELECT digest FROM arena_production_packs WHERE name=? AND version=?",
                (pack.name, pack.version),
            ).fetchone()
            if existing is not None and str(existing["digest"]) != digest:
                raise ArenaValidationError(
                    f"production pack {pack.name!r} version {pack.version!r} already exists with different content; bump the version"
                )
            conn.execute(
                """
                INSERT INTO arena_production_packs(digest,name,version,suite_digest,manifest_json,created_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(digest) DO NOTHING
                """,
                (digest, pack.name, pack.version, suite_digest, manifest_json, created_at),
            )
        return digest

    def run_campaign(
        self,
        pack: ArenaProductionPack,
        target: ArenaTargetIdentity,
        environment: ArenaEnvironmentEvidence,
        executor: Callable[[ArenaCase], Any],
        *,
        now: Callable[[], float] = time.time,
    ) -> ArenaCampaign:
        self.validate_pack(pack)
        self.validate_target(target)
        self.validate_environment(environment)
        pack_digest = self.register_pack(pack, now=now())
        target_digest = target.digest
        campaign_id = uuid.uuid4().hex
        started_at = now()
        runs: list[ArenaRun] = []

        for repeat_index in range(pack.repeat_policy.runs):
            metadata = {
                "production_benchmark": True,
                "pack_digest": pack_digest,
                "pack_name": pack.name,
                "pack_version": pack.version,
                "dataset": pack.dataset.manifest(),
                "evaluator_revision": pack.evaluator_revision,
                "target_identity": target.manifest(),
                "target_digest": target_digest,
                "environment": environment.manifest(),
                "repeat_index": repeat_index + 1,
                "repeat_count": pack.repeat_policy.runs,
            }
            runs.append(
                self.arena.run(
                    pack.suite,
                    target=f"{target.provider}:{target.model}@{target.revision}",
                    executor=executor,
                    metadata=metadata,
                )
            )

        scores = tuple(float(run.score) for run in runs)
        mean = statistics.fmean(scores)
        stddev = statistics.pstdev(scores)
        variance_accepted = stddev <= pack.repeat_policy.max_score_stddev
        finished_at = now()
        campaign = ArenaCampaign(
            campaign_id=campaign_id,
            pack_digest=pack_digest,
            target_digest=target_digest,
            target=target.manifest(),
            environment=environment.manifest(),
            run_ids=tuple(run.run_id for run in runs),
            scores=scores,
            score_mean=mean,
            score_stddev=stddev,
            variance_accepted=variance_accepted,
            started_at=started_at,
            finished_at=finished_at,
        )
        self._persist_campaign(campaign)
        return campaign

    def _persist_campaign(self, campaign: ArenaCampaign) -> None:
        with self.arena.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO arena_campaigns(
                    id,pack_digest,target_digest,target_json,environment_json,
                    run_ids_json,scores_json,score_mean,score_stddev,
                    variance_accepted,started_at,finished_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    campaign.campaign_id,
                    campaign.pack_digest,
                    campaign.target_digest,
                    canonical_json(dict(campaign.target)),
                    canonical_json(dict(campaign.environment)),
                    canonical_json(list(campaign.run_ids)),
                    canonical_json(list(campaign.scores)),
                    campaign.score_mean,
                    campaign.score_stddev,
                    int(campaign.variance_accepted),
                    campaign.started_at,
                    campaign.finished_at,
                ),
            )

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        with self.arena.db.connect() as conn:
            row = conn.execute("SELECT * FROM arena_campaigns WHERE id=?", (campaign_id,)).fetchone()
        if row is None:
            return None
        value = dict(row)
        value["target"] = json.loads(value.pop("target_json"))
        value["environment"] = json.loads(value.pop("environment_json"))
        value["run_ids"] = json.loads(value.pop("run_ids_json"))
        value["scores"] = json.loads(value.pop("scores_json"))
        value["variance_accepted"] = bool(value["variance_accepted"])
        return value

    def status(self) -> dict[str, Any]:
        with self.arena.db.connect() as conn:
            packs = int(conn.execute("SELECT COUNT(*) FROM arena_production_packs").fetchone()[0])
            campaigns = int(conn.execute("SELECT COUNT(*) FROM arena_campaigns").fetchone()[0])
        return {
            "phase": "F5",
            "authority": "rocksoul_arena_production",
            "state": "production-contract",
            "packs": packs,
            "campaigns": campaigns,
            "required_evidence": [
                "dataset_provenance",
                "evaluator_revision",
                "split_policy",
                "contamination_review",
                "repeat_variance",
                "environment",
                "network",
                "exact_target_identity",
            ],
        }


def campaign_to_dict(campaign: ArenaCampaign) -> dict[str, Any]:
    value = asdict(campaign)
    value["run_ids"] = list(campaign.run_ids)
    value["scores"] = list(campaign.scores)
    value["target"] = dict(campaign.target)
    value["environment"] = dict(campaign.environment)
    return value
