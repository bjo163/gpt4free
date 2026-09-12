from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from g4f.rocksoul_arena import ArenaCase, ArenaStore, ArenaSuite, ArenaValidationError
from g4f.rocksoul_arena_production import (
    ArenaDatasetProvenance,
    ArenaEnvironmentEvidence,
    ArenaProductionPack,
    ArenaProductionStore,
    ArenaRepeatPolicy,
    ArenaTargetIdentity,
)
from g4f.rocksoul_db import RocksoulDB


class RocksoulArenaProductionTests(unittest.TestCase):
    def make_store(self) -> ArenaProductionStore:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        arena = ArenaStore(RocksoulDB(Path(temp.name) / "rocksoul.db"))
        return ArenaProductionStore(arena)

    def suite(self) -> ArenaSuite:
        return ArenaSuite(
            name="production-unit-suite",
            version="1",
            evaluator="exact",
            provenance={"source": "unit-test", "network": False},
            cases=(
                ArenaCase("a", 1, 1),
                ArenaCase("b", 2, 2),
            ),
        )

    def pack(self, *, version="1", runs=3, max_score_stddev=0.0) -> ArenaProductionPack:
        dataset_bytes = b"rocksoul-production-unit-dataset-v1"
        return ArenaProductionPack(
            name="production-unit-pack",
            version=version,
            suite=self.suite(),
            dataset=ArenaDatasetProvenance(
                source="repository://tests/fixtures/production-unit",
                revision="v1",
                sha256=hashlib.sha256(dataset_bytes).hexdigest(),
                split_policy="public_only",
                contamination_review="synthetic fixture; no model-derived content",
                license="test-only",
            ),
            evaluator_revision="exact-v1",
            repeat_policy=ArenaRepeatPolicy(runs=runs, max_score_stddev=max_score_stddev),
            environment_requirements={"python": "3.13", "os": "portable"},
            network_requirements={"required": False, "mode": "offline"},
        )

    def target(self) -> ArenaTargetIdentity:
        return ArenaTargetIdentity(
            provider="fixture-provider",
            model="fixture-model",
            revision="model-rev-1",
            runtime_revision="runtime-rev-1",
        )

    def environment(self) -> ArenaEnvironmentEvidence:
        return ArenaEnvironmentEvidence(
            runtime="rocksoul-test-runtime",
            os="test-os",
            python="3.13",
            network_mode="offline",
            region="local",
        )

    def test_pack_requires_complete_production_provenance(self):
        store = self.make_store()
        invalid = ArenaProductionPack(
            name="invalid",
            version="1",
            suite=self.suite(),
            dataset=ArenaDatasetProvenance(
                source="",
                revision="v1",
                sha256="not-a-digest",
                split_policy="unknown",
                contamination_review="",
            ),
            evaluator_revision="",
            repeat_policy=ArenaRepeatPolicy(runs=1, max_score_stddev=-1),
        )
        with self.assertRaises(ArenaValidationError):
            store.register_pack(invalid)

    def test_pack_name_version_is_immutable(self):
        store = self.make_store()
        first = self.pack()
        store.register_pack(first)
        changed = ArenaProductionPack(
            name=first.name,
            version=first.version,
            suite=first.suite,
            dataset=first.dataset,
            evaluator_revision="exact-v2",
            repeat_policy=first.repeat_policy,
            environment_requirements=first.environment_requirements,
            network_requirements=first.network_requirements,
        )
        with self.assertRaises(ArenaValidationError):
            store.register_pack(changed)

    def test_campaign_persists_exact_target_environment_and_repeat_evidence(self):
        store = self.make_store()
        pack = self.pack(runs=3, max_score_stddev=0.0)
        campaign = store.run_campaign(
            pack,
            self.target(),
            self.environment(),
            lambda case: case.expected,
        )
        self.assertEqual(len(campaign.run_ids), 3)
        self.assertEqual(campaign.scores, (100.0, 100.0, 100.0))
        self.assertEqual(campaign.score_stddev, 0.0)
        self.assertTrue(campaign.variance_accepted)

        stored = store.get_campaign(campaign.campaign_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["target"]["provider"], "fixture-provider")
        self.assertEqual(stored["target"]["model"], "fixture-model")
        self.assertEqual(stored["target"]["revision"], "model-rev-1")
        self.assertEqual(stored["environment"]["network_mode"], "offline")
        self.assertEqual(len(stored["run_ids"]), 3)

        for run_id in campaign.run_ids:
            run = store.arena.get_run(run_id)
            self.assertIsNotNone(run)
            self.assertTrue(run["metadata"]["production_benchmark"])
            self.assertEqual(run["metadata"]["target_identity"]["runtime_revision"], "runtime-rev-1")
            self.assertEqual(run["metadata"]["evaluator_revision"], "exact-v1")

    def test_variance_policy_fails_closed_when_repeats_are_unstable(self):
        store = self.make_store()
        pack = self.pack(runs=2, max_score_stddev=10.0)
        calls = 0

        def unstable(case: ArenaCase):
            nonlocal calls
            calls += 1
            repeat = (calls - 1) // len(pack.suite.cases)
            if repeat == 0:
                return case.expected
            return -1

        campaign = store.run_campaign(pack, self.target(), self.environment(), unstable)
        self.assertEqual(campaign.scores, (100.0, 0.0))
        self.assertGreater(campaign.score_stddev, 10.0)
        self.assertFalse(campaign.variance_accepted)

    def test_target_and_environment_identity_are_required(self):
        store = self.make_store()
        with self.assertRaises(ArenaValidationError):
            store.run_campaign(
                self.pack(),
                ArenaTargetIdentity("", "model", "rev", "runtime"),
                self.environment(),
                lambda case: case.expected,
            )
        with self.assertRaises(ArenaValidationError):
            store.run_campaign(
                self.pack(),
                self.target(),
                ArenaEnvironmentEvidence("runtime", "os", "3.13", "unknown"),
                lambda case: case.expected,
            )


if __name__ == "__main__":
    unittest.main()
