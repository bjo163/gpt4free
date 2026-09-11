# ROCKSOUL Product Backlog

> Canonical execution backlog for the ROCKSOUL product layer. GitHub Issues are disabled in this repository, so each item below is intentionally small, testable, and traceable from code to release.

## Product identity

ROCKSOUL is the product/control-plane layer built on top of the existing g4f runtime. The runtime remains the provider execution substrate. ROCKSOUL owns routing intelligence, execution policy, health evidence, traceability, recovery, future mesh coordination, and product-facing interfaces. ROCKSOUL does not duplicate provider implementations.

## Status legend

- `DONE` implemented and verified
- `READY` next executable item
- `BLOCKED` intentionally waiting on another gate
- `DEFERRED` planned but not in the current release

## F3 execution intelligence

### RS-F3-001 — Explicit rate-limit cooldown
- Status: `READY`
- Scope: apply `RATE_LIMIT` policy decision to provider state.
- Files: `g4f/rocksoul_policy.py`, `g4f/rocksoul_db.py`, `g4f/rocksoul_execution.py`, tests.
- TODO:
  - Add explicit cooldown mutation with reason and expiry.
  - Apply `PolicyDecision.cooldown_seconds` after rate-limit failure.
  - Ensure router skips active cooldown.
  - Expose cooldown in health/status output.
  - Cover apply/skip/expiry in offline tests.
- Acceptance:
  - A rate-limit failure immediately suppresses that provider for the policy cooldown window.
  - No extra retry is performed against a provider under active cooldown.
  - Cooldown never exceeds the configured upper bound.

### RS-F3-002 — Same-provider retry budget
- Status: `READY`
- Scope: make `max_same_provider_attempts` a real runtime control instead of only using a global `tried` set.
- TODO:
  - Track attempts per provider.
  - Permit same-provider retry only when the policy explicitly requests it.
  - Enforce `max_same_provider_attempts` independently from total attempts.
  - Add tests for zero/one/multiple bounded retries.
- Acceptance:
  - A provider can never exceed its configured per-provider budget.
  - Provider fallback still works when same-provider retry is exhausted.
  - Total attempts and total-time limits always win.

### RS-F3-003 — Explicit quarantine state
- Status: `READY`
- Scope: replace implicit failure-streak interpretation with an explicit lifecycle state.
- TODO:
  - Model `ACTIVE`, `DEGRADED`, `QUARANTINED`, `PROBING`, `RE_ADMITTED`.
  - Persist quarantine reason and timestamps.
  - Add `quarantine` CLI command.
  - Make routing honor explicit quarantine.
- Acceptance:
  - A provider can be manually quarantined without fake probe failures.
  - Quarantine is visible in `health` and `status`.
  - Router excludes quarantined providers.

### RS-F3-004 — Recovery and re-admission lifecycle
- Status: `READY`
- Scope: make recovery a deterministic state transition.
- TODO:
  - Move quarantined provider to `PROBING` before a recovery probe.
  - Record probe result as recovery evidence.
  - Re-admit only on successful verification.
  - Keep provider quarantined on failed recovery.
  - Add offline state-machine tests.
- Acceptance:
  - Recovery cannot silently re-admit an unhealthy provider.
  - Recovery history is traceable.

### RS-F3-005 — Single canonical route explanation
- Status: `READY`
- Scope: eliminate parallel explanation logic.
- TODO:
  - Make `ExplainableRouter` the canonical explanation engine.
  - Have execution consume its selected candidate plus reasons.
  - Persist the same reasons used for selection.
  - Cover capability rejection, health, verification, latency, cooldown, and ordering.
- Acceptance:
  - `route-explain` and execution trace describe the same decision.
  - No second scoring/explanation implementation can drift from routing behavior.

### RS-F3-006 — Streaming fallback safety
- Status: `READY`
- Scope: define safe fallback behavior once a stream has started.
- TODO:
  - Define states: `NOT_STARTED`, `STREAMING`, `COMPLETED`, `FAILED_AFTER_PARTIAL`.
  - Never silently replay a request after partial output unless an explicit policy permits it.
  - Persist partial-stream failure in execution trace.
  - Add fake streaming tests.
- Acceptance:
  - No duplicate unsafe user-visible generation after partial output.
  - Stream failures are observable and bounded.

## F6 product CLI

### RS-F6-001 — CLI contract suite
- Status: `READY`
- TODO:
  - Add offline command tests for `status`, `discover`, `health`, `provider`, `route`, `route-explain`, `execute`, `trace`, `quarantine`, `recover`.
  - Assert stable JSON keys and exit behavior.
  - Keep live-provider operations opt-in.
- Acceptance:
  - CI validates the documented CLI contract.

## F7 verification

### RS-F7-001 — Execution release matrix
- Status: `READY`
- TODO:
  - Add tests for every error taxonomy branch.
  - Add fallback ordering tests.
  - Add total-time and per-provider budgets.
  - Add persistence and trace reconstruction tests.
  - Add capability enforcement tests.
  - Add explicit quarantine/recovery lifecycle tests.
- Acceptance:
  - No release gate depends on a live provider.

## F8 documentation and productization

### RS-F8-001 — Product README
- Status: `DONE`
- Scope: present ROCKSOUL as the primary product identity while preserving accurate g4f attribution.

### RS-F8-002 — Product architecture docs
- Status: `DONE`
- Scope: document product boundaries, execution plane, state model, and roadmap.

### RS-F8-003 — Contributing and compatibility boundary
- Status: `READY`
- TODO:
  - Document upstream/runtime boundary.
  - State that provider implementations remain in the runtime layer.
  - Document how ROCKSOUL changes should avoid breaking g4f compatibility.

## F4/F5 gates

### RS-F4-001 — Mesh foundation
- Status: `BLOCKED`
- Do not start until RS-F3-001 through RS-F3-006 and RS-F7-001 are green.

### RS-F5-001 — Arena benchmark plane
- Status: `BLOCKED`
- Do not start until execution traces and health feedback are stable.

## Definition of Product-Ready

- F1 execution works through existing runtime provider implementations.
- F2 persists every attempt and the final outcome.
- F3 has deterministic taxonomy, bounded retries, explicit cooldown, quarantine, and recovery.
- F6 CLI is documented and contract-tested.
- F7 tests are offline by default.
- F8 docs use ROCKSOUL product terminology consistently.
- No duplicate provider implementation exists.
- F4/F5 are not enabled merely because the scaffolding exists.
