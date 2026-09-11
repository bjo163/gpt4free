# ROCKSOUL Release Gate

## Rule

A ROCKSOUL release is production-ready only when all mandatory gates below are green on CI and covered by deterministic tests. Open P0/P1 items block release.

## F0 — Guardrails
- [x] Unique request identity.
- [x] Explicit execution attempt/result contracts.
- [x] No live provider dependency in unit tests.
- [x] No provider implementation duplication.

## F1 — Execution
- [x] Existing `g4f.Client` is the execution substrate.
- [x] Candidate selection comes from ROCKSOUL routing data.
- [x] Provider fallback is bounded.
- [x] Response validation is explicit.

## F2 — Trace
- [x] Execution run persisted.
- [x] Every attempt persisted, including failures.
- [x] Actual execution is recorded as health evidence.
- [x] Trace can be retrieved by request ID.

## F3 — Reliability
- [x] Error taxonomy exists.
- [x] Retry decisions are deterministic.
- [x] Global max-attempt and total-time bounds exist.
- [ ] Explicit rate-limit cooldown transition.
- [ ] Enforced same-provider retry budget.
- [ ] Explicit quarantine state and CLI.
- [ ] Recovery/re-admission lifecycle.
- [ ] Canonical route explanation shared by routing and execution.
- [ ] Streaming fallback safety contract.

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
- [ ] quarantine
- [x] recover

## F7 — Certification
- [ ] Offline contract tests for every product CLI command.
- [ ] Failure taxonomy regression suite.
- [ ] Retry/quarantine/recovery regression suite.
- [ ] Stream failure regression suite.
- [ ] Windows + Linux CI green on final release commit.

## F8 — Productization
- [x] ROCKSOUL-first README.
- [x] Product architecture docs.
- [x] Granular backlog.
- [x] Standalone migration plan.
- [ ] Contribution/compatibility boundary fully synchronized.

## Future

- F4 Mesh: BLOCKED until F0–F3/F6/F7 are certified.
- F5 Arena: BLOCKED until execution metrics and F3/F7 are stable.

## Evidence policy

A checked box must map to source code, a deterministic test, or a verified repository configuration. Documentation alone cannot close an implementation gate.
