# ROCKSOUL F5 Arena Release Gate

F5 Arena is certified independently from the execution and Mesh control planes. The existence of legacy benchmark helpers or an offline fixture does not make Arena production-ready.

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

## Mandatory verification gate

- [ ] `ROCKSOUL Arena CI` passes on Ubuntu / Python 3.13.
- [ ] `ROCKSOUL Arena CI` passes on Windows / Python 3.13.
- [ ] Arena core unit tests pass.
- [ ] Arena CLI contract tests pass.
- [ ] `rocksoul-arena` smoke fixture passes.
- [ ] package wheel + source distribution build succeeds.
- [ ] existing `ROCKSOUL CI` remains green on the final candidate.
- [ ] existing `ROCKSOUL Mesh CI` remains green when applicable.
- [ ] general repository `Unittest` remains green on the final candidate.

## Production benchmark-pack gate

The foundation may merge without claiming broad live-model quality certification. Before a real benchmark pack is advertised as authoritative, it must additionally define:

- versioned source/dataset provenance;
- evaluator version and scoring semantics;
- public/held-out split policy where applicable;
- contamination and leakage review procedure;
- repeat-run and variance policy for non-deterministic targets;
- environment/network requirements;
- target identity and model/provider revision metadata.

## Release decision

Until all mandatory final-head verification boxes are green, F5 status is **VERIFYING / FOUNDATION**, not production-certified Arena. Any future F5 production release must record the exact commit and workflow evidence that satisfied this checklist.
