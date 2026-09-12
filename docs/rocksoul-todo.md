# ROCKSOUL Product Backlog

> Canonical execution backlog for the ROCKSOUL product layer. GitHub Issues are disabled in this repository, so each item below is intentionally small, testable, and traceable from code to release.

## Product identity

ROCKSOUL is the product/control-plane layer built on top of the existing g4f runtime. The runtime remains the provider execution substrate. ROCKSOUL owns routing intelligence, execution policy, health evidence, traceability, recovery, future mesh coordination, and product-facing interfaces. ROCKSOUL does not duplicate provider implementations.

## Status legend

- `DONE` implemented and verified by automated tests
- `VERIFYING` implemented; awaiting the current CI certification
- `BLOCKED` intentionally waiting on another phase gate
- `DEFERRED` planned but not in the current release

## F3 execution intelligence

### RS-F3-001 — Explicit rate-limit cooldown
- Status: `DONE`
- Scope: explicit persisted cooldown with reason and expiry.
- Implementation: `g4f/rocksoul_control.py`, `g4f/rocksoul_execution.py`, `g4f/rocksoul_db.py` routing integration.
- Acceptance: rate-limit immediately places the provider in bounded `DEGRADED` cooldown; routing excludes it until expiry.
- Tests: `test_rate_limit_applies_explicit_control_cooldown`, `test_rate_limit_cooldown_blocks_until_expiry`.

### RS-F3-002 — Same-provider retry budget
- Status: `DONE`
- Scope: per-provider retry counter independent from total-attempt budget.
- Implementation: `ExecutionRequest.max_same_provider_attempts` and execution provider counters.
- Acceptance: no provider exceeds its configured retry budget; fallback continues when that budget is exhausted.
- Tests: `test_same_provider_retry_is_bounded`.

### RS-F3-003 — Explicit quarantine state
- Status: `DONE`
- Scope: persisted lifecycle state and operator command.
- Implementation: `ProviderControlStore`, `rocksoul quarantine`, route filtering, health/status output, failure-streak convergence.
- Acceptance: manual quarantine requires no fake failures and quarantined providers are never selected; a three-failure legacy streak converges to explicit `QUARANTINED`.
- Tests: control state machine + `test_provider_enters_legacy_health_cooldown_after_failure_streak`.

### RS-F3-004 — Recovery and re-admission lifecycle
- Status: `DONE`
- Scope: `QUARANTINED → PROBING → RE_ADMITTED|QUARANTINED`.
- Implementation: `RecoveryManager` + provider control event history.
- Acceptance: failed recovery stays quarantined; successful recovery is traceable.
- Tests: control state-machine coverage; live recovery remains operator-only.

### RS-F3-005 — Single canonical route explanation
- Status: `DONE`
- Scope: `ExplainableRouter` is the canonical explanation source.
- Implementation: execution candidate selection and CLI route-explain both consume it; capability failures remain visible as rejection reasons.
- Acceptance: route explanation exposes state, capability, verification, health, latency, and reasons without a second scoring path.
- Tests: intelligence and CLI route-explain contract tests.

### RS-F3-006 — Streaming fallback safety
- Status: `DONE`
- Scope: conservative stream lifecycle with no automatic replay after stream exposure.
- Implementation: stream wrapper records `stream_failed_before_output` or `stream_failed_after_partial`.
- Acceptance: partial output is never silently duplicated by fallback.
- Tests: `test_stream_failure_after_partial_output_is_terminal_and_traced`.

### RS-F3-007 — Whole-request execution time budget
- Status: `DONE`
- Scope: `max_total_time` bounds routing plus all attempts/backoff, including the pre-attempt lifecycle.
- Implementation: `RetryBudget` construction and explicit `budget_exhausted` terminal outcome in `g4f/rocksoul_execution.py`.
- Acceptance: a request whose total budget is exhausted before the first provider call produces zero attempts and an explicit `budget_exhausted` outcome.
- Tests: `test_total_time_budget_covers_entire_request_lifecycle`.

## F6 product CLI

### RS-F6-001 — CLI contract suite
- Status: `VERIFYING`
- Scope: stable JSON command surface with offline contract tests.
- Commands: `status`, `discover`, `health`, `provider`, `probe`, `verify`, `route`, `route-explain`, `execute`, `trace`, `quarantine`, `recover`.
- Tests: `tests/test_rocksoul_cli.py` plus existing ROCKSOUL CLI smoke workflow.

## F7 verification

### RS-F7-001 — Execution release matrix
- Status: `VERIFYING`
- Coverage: fallback ordering, taxonomy, bounded retries, cooldown, quarantine, recovery state machine, trace reconstruction, stream safety, lifecycle budget, CLI contracts.
- Current evidence: Ubuntu ROCKSOUL CI unit tests pass all 37 tests on head `77845568ebeb25e963bf295e4adab1ba553968f2`.
- Release requirement: current CI must be green on both Ubuntu and Windows before certification is marked complete.

## F8 documentation and productization

### RS-F8-001 — Product README
- Status: `DONE`

### RS-F8-002 — Product architecture docs
- Status: `DONE`

### RS-F8-003 — Contributing and compatibility boundary
- Status: `DONE`

## F4/F5 gates

### RS-F4-001 — Mesh foundation
- Status: `BLOCKED`
- Dependency: F1-F3 + F6 + F7 certification.

### RS-F5-001 — Arena benchmark plane
- Status: `BLOCKED`
- Dependency: stable execution traces and health feedback plus release certification.

## Definition of Product-Ready

- F1 execution works through existing runtime provider implementations.
- F2 persists every attempt and the final outcome.
- F3 has deterministic taxonomy, bounded retries, explicit cooldown, quarantine, recovery, safe streaming semantics, and explicit whole-request time budgeting.
- F6 CLI is documented and contract-tested.
- F7 tests are offline by default and CI-certified on required platforms.
- F8 docs use ROCKSOUL product terminology consistently.
- No duplicate provider implementation exists.
- F4/F5 are not enabled merely because scaffolding exists.
