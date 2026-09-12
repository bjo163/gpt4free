# ROCKSOUL Product Backlog

> Canonical execution backlog for the ROCKSOUL product layer. GitHub Issues are disabled in this repository, so each item below is intentionally small, testable, and traceable from code to release.

## Product identity

ROCKSOUL is the product/control-plane layer built on top of the existing g4f runtime. The runtime remains the provider execution substrate. ROCKSOUL owns routing intelligence, execution policy, health evidence, traceability, recovery, future mesh coordination, and product-facing interfaces. ROCKSOUL does not duplicate provider implementations.

## Status legend

- `DONE` implemented and verified by automated tests
- `VERIFYING` implemented; awaiting current CI certification
- `BLOCKED` intentionally waiting on another phase gate
- `DEFERRED` outside the current release and moved to its own future gate

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
- Acceptance: route explanation exposes state, capability, verification, health, latency, and reasons without a second product scoring path.
- Tests: intelligence and CLI route-explain contract tests.

### RS-F3-006 — Streaming fallback safety
- Status: `DONE`
- Scope: conservative stream lifecycle with no automatic replay after stream exposure.
- Implementation: stream wrapper records active, success, abandonment, or failure terminal state.
- Acceptance: partial output is never silently duplicated by fallback.
- Tests: streaming failure/success lifecycle coverage.

### RS-F3-007 — Whole-request execution time budget
- Status: `DONE`
- Scope: `max_total_time` bounds routing plus all attempts/backoff, including the pre-attempt lifecycle.
- Acceptance: a request whose total budget is exhausted before the first provider call produces zero attempts and an explicit `budget_exhausted` outcome.
- Tests: `test_total_time_budget_covers_entire_request_lifecycle`.

### RS-F3-008 — In-flight total-budget enforcement
- Status: `DONE`
- Scope: cap each provider-call timeout by the remaining whole-request budget.
- Acceptance: an attempt cannot overrun `max_total_time` merely because its provider timeout is larger.
- Tests: `test_total_time_budget_caps_inflight_provider_timeout`.

### RS-F3-009 — Recovery probing isolation
- Status: `DONE`
- Scope: keep `PROBING` providers outside normal request routing.
- Acceptance: provider remains unroutable until explicit `RE_ADMITTED` transition.
- Tests: control lifecycle routing assertions in `test_quarantine_and_recovery_state_machine`.

### RS-F3-010 — Single-counted streaming health evidence
- Status: `DONE`
- Scope: do not record stream success before the stream has actually completed.
- Acceptance: one stream attempt contributes at most one terminal execution health signal; failed streams are not counted as both success and failure.
- Tests: `test_stream_failure_after_partial_output_is_terminal_and_single_counted`, `test_successful_stream_records_success_only_after_consumption`.

## F6 product CLI

### RS-F6-001 — CLI contract suite
- Status: `DONE`
- Scope: stable JSON command surface with offline contract tests.
- Commands: `status`, `discover`, `health`, `provider`, `probe`, `verify`, `route`, `route-explain`, `execute`, `trace`, `quarantine`, `recover`.
- Tests: `tests/test_rocksoul_cli.py` plus ROCKSOUL CLI smoke workflow.

### RS-F6-002 — Preserve verified-only capability routing
- Status: `DONE`
- Scope: `route --verified-only` must retain the verification constraint when capability flags are supplied.
- Acceptance: capability-aware selection cannot silently reintroduce unverified model bindings.
- Tests: `test_route_verified_only_is_preserved_with_capability_filter`.

## F7 verification

### RS-F7-001 — Execution release matrix
- Status: `DONE`
- Coverage: fallback ordering, taxonomy, bounded retries, cooldown, quarantine, recovery state machine, trace reconstruction, stream safety/evidence, lifecycle budget, CLI contracts, verified-only capability routing.
- Release requirement: required Ubuntu and Windows ROCKSOUL CI must be green on the final release candidate.

## F8 documentation and productization

### RS-F8-001 — Product README
- Status: `DONE`

### RS-F8-002 — Product architecture docs
- Status: `DONE`

### RS-F8-003 — Contributing and compatibility boundary
- Status: `DONE`

## F4/F5 future gates

### RS-F4-001 — Mesh foundation
- Status: `DEFERRED`
- Foundation dependency: F1-F3 + F6 + F7 certification satisfied.
- Rule: Mesh remains disabled until its own implementation, security, observability, failure-boundary, and verification gate is completed.

### RS-F5-001 — Arena benchmark plane
- Status: `DEFERRED`
- Foundation dependency: stable execution traces, health feedback, and release certification satisfied.
- Rule: Arena remains outside the certified baseline until its own deterministic benchmark/release contract is implemented.

## Definition of Product-Ready Baseline

- F1 execution works through existing runtime provider implementations.
- F2 persists every attempt and final outcome.
- F3 has deterministic taxonomy, bounded retries, explicit cooldown, quarantine, probing isolation, recovery, safe streaming semantics, single-counted stream evidence, and whole-request time budgeting including in-flight calls.
- F6 CLI is documented and contract-tested, including verified-only capability filtering.
- F7 tests are offline by default and CI-certified on required platforms.
- F8 docs use ROCKSOUL product terminology consistently.
- No duplicate provider implementation exists.
- F4/F5 are not enabled merely because legacy/future scaffolding exists.
