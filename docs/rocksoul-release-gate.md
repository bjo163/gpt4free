# ROCKSOUL Release Gate

## Rule

A ROCKSOUL release is product-ready only when all mandatory gates below are green on CI and covered by deterministic tests. Open P0/P1 execution-control items block release. F4 Mesh and F5 Arena are separate future phases and are not release blockers for the F1–F3 baseline.

## F0 — Guardrails
- [x] Unique request identity.
- [x] Explicit execution attempt/result contracts.
- [x] No live provider dependency in unit tests.
- [x] No provider implementation duplication.
- [x] Existing g4f provider/runtime layer remains the execution substrate.

## F1 — Execution
- [x] Existing `g4f.Client` is the execution substrate.
- [x] Candidate selection comes from ROCKSOUL routing data.
- [x] Provider fallback is bounded.
- [x] Response validation is explicit.
- [x] In-flight provider timeout is capped by the remaining whole-request budget.

## F2 — Trace
- [x] Execution run persisted.
- [x] Every attempt persisted, including failures.
- [x] Actual execution is recorded as health evidence.
- [x] Trace can be retrieved by request ID.
- [x] Streaming health evidence is terminal and single-counted.

## F3 — Reliability
- [x] Error taxonomy exists.
- [x] Retry decisions are deterministic.
- [x] Global max-attempt and total-time bounds exist.
- [x] Explicit rate-limit cooldown transition.
- [x] Enforced same-provider retry budget.
- [x] Explicit quarantine state and CLI.
- [x] Recovery/re-admission lifecycle.
- [x] `PROBING` providers are isolated from normal routing until re-admission.
- [x] Canonical route explanation shared by routing and execution.
- [x] Streaming failure safety contract.

## F6 — CLI
- [x] status
- [x] discover
- [x] health
- [x] provider
- [x] probe
- [x] verify
- [x] route
- [x] route-explain
- [x] execute
- [x] trace
- [x] quarantine
- [x] recover
- [x] `route --verified-only` remains enforced when capability filters are present.

## F7 — Certification
- [x] Offline contract tests for product CLI commands in the certified baseline.
- [x] Failure taxonomy regression suite.
- [x] Retry/quarantine/recovery regression suite.
- [x] Stream lifecycle/evidence regression suite.
- [x] Whole-request in-flight timeout regression suite.
- [x] Verified-only capability-routing regression suite.
- [x] Windows + Linux ROCKSOUL CI required on the final release candidate.

## F8 — Productization
- [x] ROCKSOUL-first README.
- [x] Product architecture docs.
- [x] Granular backlog.
- [x] Standalone migration plan.
- [x] Contribution/compatibility boundary synchronized.

## Future

- F4 Mesh: `DEFERRED` to its own implementation/release gate. Foundation dependency is satisfied; Mesh is not enabled by this baseline.
- F5 Arena: `DEFERRED` to its own implementation/release gate. Foundation dependency is satisfied; Arena is not enabled by this baseline.

## Evidence policy

A checked box must map to source code, a deterministic test, or a verified repository/CI configuration. Documentation alone cannot close an implementation gate.
