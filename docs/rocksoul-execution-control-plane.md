# ROCKSOUL Execution Control Plane

## Scope

The ROCKSOUL execution layer sits above the existing `g4f.Client` and provider implementations. It owns execution policy, bounded fallback, trace persistence, and health feedback. It must not duplicate provider implementations or become a second provider registry.

## Current fast-track

- **F0** — baseline/guardrails: request identity, attempt/result contracts, no live-provider unit-test dependency.
- **F1** — execution engine: deterministic candidates from ROCKSOUL routing, existing `g4f.Client`, bounded fallback.
- **F2** — execution trace: `execution_runs` and `execution_attempts`; failures are persisted as well as successes.
- **F3** — adaptive retry foundation: error taxonomy, bounded backoff, cooldown/quarantine-by-health, and execution evidence.
- **F4 Mesh** — intentionally blocked until F1–F3 are release-stable.

## Execution lifecycle

1. Normalize an `ExecutionRequest` and assign a unique `request_id`.
2. Ask ROCKSOUL routing for eligible provider candidates.
3. Persist the execution run before the first provider attempt.
4. Execute each attempt through the existing `g4f.Client`.
5. Persist every attempt, including timeout/network/rate-limit failures.
6. Feed actual execution evidence into the existing health store.
7. Apply `ExecutionPolicy` and `RetryBudget`.
8. Recompute candidates when the failure class makes the current route invalid.
9. Stop on success, terminal policy, provider exhaustion, attempt budget, or total-time budget.

## Release gates

Before merging F1–F3:

- [x] No duplicate provider implementation.
- [x] Unique request IDs.
- [x] Bounded `max_attempts` and `max_total_time`.
- [x] Deterministic error taxonomy.
- [x] Every execution attempt is traceable.
- [x] Actual execution updates health evidence.
- [x] Content-policy failures are terminal.
- [x] Route candidates respect verified capabilities and health cooldown.
- [x] Offline unit tests cover fallback and policy behavior.
- [x] ROCKSOUL CI passes on Windows and Ubuntu.
- [ ] Unittest workflow fully green on the F1–F3 head.
- [ ] Explicit quarantine/recovery CLI contract is complete.
- [ ] Route-explain output includes execution history where applicable.
- [ ] Streaming fallback semantics are verified end-to-end; do not claim this gate from request acceptance alone.

## CLI surface

Implemented on the fast-track branch:

```text
rocksoul discover
rocksoul health [provider]
rocksoul provider <name>
rocksoul probe <provider>
rocksoul verify <provider>
rocksoul route <model>
rocksoul route-explain <model>
rocksoul execute <model> <message>
rocksoul trace <request_id>
rocksoul recover
rocksoul status
```

`quarantine` is a release-gate item until its persistent state and CLI behavior are explicit rather than inferred only from a three-failure cooldown.

## Mesh/Arena boundary

Do not start F4/F5 merely because CI is green. The execution trace and health feedback are the source of truth for later mesh and arena work. Remote execution and benchmarking must consume these contracts instead of creating parallel execution/provider abstractions.
