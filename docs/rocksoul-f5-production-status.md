# ROCKSOUL F5 Production Benchmark Status

This file tracks the production-benchmark transition without overstating live-provider certification.

## Contract layer

- `ArenaProductionPack` — immutable pack identity and manifest.
- `ArenaDatasetProvenance` — source, revision, SHA-256, split policy, contamination review.
- `ArenaRepeatPolicy` — bounded repeated runs and maximum accepted score standard deviation.
- `ArenaTargetIdentity` — exact provider, model, revision, and runtime revision.
- `ArenaEnvironmentEvidence` — runtime, OS, Python version, network mode, region, and extra evidence.
- `ArenaProductionStore` — persistent production-pack and campaign evidence linked to underlying Arena runs.

## Verification status

The structural production-evidence contract is `CERTIFIED` for merge. PR #20 candidate `c778e811cdf44c3400262e4736555df386e6b869` passed `ROCKSOUL Arena CI`, `ROCKSOUL CI`, and general `Unittest`.

This certification covers the evidence contract, persistence model, deterministic tests, cross-platform Arena CI, and regression compatibility. It does not certify a specific live benchmark pack.

## Live activation status

Live production benchmark packs remain `DEFERRED` until a real dataset and real campaign satisfy every live activation item in `docs/rocksoul-arena-release-gate.md`.
