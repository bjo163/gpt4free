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

The contract implementation is `VERIFYING` until the exact PR head passes Arena CI on Ubuntu/Windows plus repository regression gates.

## Live activation status

Live production benchmark packs remain `DEFERRED` until a real dataset and real provider/model campaign satisfy every live activation item in `docs/rocksoul-arena-release-gate.md`.

This distinction is intentional: structural evidence support may be production-grade before any specific benchmark dataset or leaderboard claim is certified.
