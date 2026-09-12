# ROCKSOUL F5 Arena

F5 Arena is the benchmark and comparison plane for ROCKSOUL. It is isolated from F1-F3 provider execution policy and F4 Mesh coordination so benchmark logic cannot change production routing or node lifecycle.

## Canonical authority

The canonical F5 path is `g4f/rocksoul_arena.py` with the `rocksoul-arena` CLI. The older `Arena` class in `g4f/rocksoul_platform.py` remains compatibility-only.

## Benchmark model

A suite contains a name, version, evaluator, provenance object, and weighted cases. Cases are sorted by `case_id`, serialized canonically, and hashed with SHA-256. The same suite name/version cannot be reused with different content; changed content requires a version bump.

Each run records a target, suite digest, per-case correctness, weight, latency evidence, output digest, errors, aggregate score, and timestamps in the ROCKSOUL SQLite control-plane database.

## Deterministic scoring

The foundation supports `exact` and `json_exact` evaluators. A correct case scores `1.0`; an incorrect or failed case scores `0.0`.

```text
score = 100 * sum(case_score * weight) / sum(weight)
```

Latency is recorded but does not affect the default score. This keeps correctness ranking independent from machine load and timing jitter.

## Reproducibility rules

- suite name and version are required;
- case IDs are non-empty and unique;
- case order is canonicalized by ID;
- weights are positive, finite, and bounded;
- suite content is identified by SHA-256 digest;
- execution errors remain explicit result evidence;
- the leaderboard uses the latest run for each target instead of a historical best run;
- raw output is not stored by default; an output digest is persisted instead.

## Provenance

Production suites should record source revision, dataset or fixture identifier, curation method, evaluator version, benchmark owner, and network requirements. A mutable unversioned dataset is not considered reproducible evidence.

## Persistence

Arena uses independent tables:

- `arena_suites` for immutable manifests and digests;
- `arena_runs` for aggregate run evidence;
- `arena_results` for per-case evidence.

## Operator CLI

```text
rocksoul-arena status
rocksoul-arena fixture [--target perfect|mixed|failing]
rocksoul-arena fixture-manifest [--register]
rocksoul-arena runs [--suite-digest <digest>] [--limit <n>]
rocksoul-arena show <run-id>
rocksoul-arena leaderboard [--suite-digest <digest>]
```

The built-in fixture is offline and synthetic. It validates the Arena contract without claiming live provider quality.

## Failure boundary

F5 does not mutate F3 provider health or lifecycle, F4 Mesh node state or leases, or production routing decisions. Arena certification is independent and requires the gate in `docs/rocksoul-arena-release-gate.md`.
