# ROCKSOUL F5 Arena Release Gate

F5 Arena is certified independently from the execution and Mesh control planes. The existence of legacy benchmark helpers or an offline fixture does not make a real provider/model benchmark pack production-authoritative.

## Mandatory architecture gate

- [x] Canonical implementation is separate from `rocksoul_platform.Arena`.
- [x] F5 cannot mutate F3 provider lifecycle or F4 Mesh lifecycle.
- [x] Suite identity is content-addressed with SHA-256.
- [x] Suite name/version is immutable once registered.
- [x] Result evidence is persisted in the ROCKSOUL SQLite control plane.

## Mandatory methodology gate

- [x] Deterministic case ordering.
- [x] Explicit positive bounded weights.
- [x] Deterministic correctness scoring.
- [x] Execution errors remain visible as zero-score evidence.
- [x] Latency is evidence-only in the default score.
- [x] Leaderboard uses the latest run per target rather than historical best-run selection.
- [x] Offline repository fixture has explicit provenance and no network dependency.

## Mandatory foundation verification gate

- [x] `ROCKSOUL Arena CI` passes on Ubuntu / Python 3.13.
- [x] `ROCKSOUL Arena CI` passes on Windows / Python 3.13.
- [x] Arena core unit tests pass.
- [x] Arena CLI contract tests pass.
- [x] `rocksoul-arena` smoke fixture passes.
- [x] package wheel + source distribution build succeeds.
- [x] existing `ROCKSOUL CI` remains green on the final candidate.
- [x] existing `ROCKSOUL Mesh CI` remains green on the final candidate.
- [x] general repository `Unittest` remains green on the final candidate.

### Foundation certification evidence

- PR #17 exact head: `10d16d58b6257396acd7dad00d614f3ac31e46a3`.
- Exact PR head passed `ROCKSOUL Arena CI`, `ROCKSOUL Mesh CI`, `ROCKSOUL CI`, and general `Unittest` before merge.
- Merge commit on `main`: `d3123a9ff8d00828d0043cd0bb3937cbc16dab8a`.
- Post-merge `main` passed `ROCKSOUL Arena CI`, `ROCKSOUL Mesh CI`, `ROCKSOUL CI`, and general `Unittest` again.
- The production-release workflow re-ran deterministic regression and package build successfully, detected that `v0.2.0` already existed, and correctly skipped duplicate tag/release creation.

## Production benchmark-pack gate

The deterministic Arena foundation is verified, but a real benchmark pack must satisfy the following before it is advertised as authoritative for live provider/model quality:

- [ ] versioned source/dataset provenance;
- [ ] evaluator version and scoring semantics;
- [ ] public/held-out split policy where applicable;
- [ ] contamination and leakage review procedure;
- [ ] repeat-run and variance policy for non-deterministic targets;
- [ ] environment/network requirements;
- [ ] exact target identity and model/provider revision metadata.

## Release decision

The **F5 Arena foundation gate is GREEN** at `d3123a9ff8d00828d0043cd0bb3937cbc16dab8a`. This certifies the deterministic benchmark core, persistence contract, CLI, fixtures, and independent CI boundary.

It does **not** certify broad live-provider/model benchmark claims and does not change the published `v0.2.0` production-release scope. Production benchmark packs remain `DEFERRED` until every benchmark-pack gate above is satisfied. No new version tag or production release is implied by foundation certification alone.
