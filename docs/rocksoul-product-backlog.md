# ROCKSOUL Product Backlog

Canonical granular execution ledger for the ROCKSOUL product layer.

GitHub Issues are disabled for this repository. These items are intentionally small, testable, and traceable from code to release.

## Product identity

ROCKSOUL is the product/control-plane layer. The existing g4f runtime/provider layer is a compatibility substrate and is not duplicated.

## F3 — Adaptive execution reliability

### RS-F3-001 — Explicit rate-limit cooldown
- Priority: P1
- Scope: Persist an explicit provider cooldown transition after rate-limit failures.
- Files: `g4f/rocksoul_policy.py`, `g4f/rocksoul_db.py`, `g4f/rocksoul_execution.py`, tests.
- Acceptance: rate-limit immediately records bounded cooldown; routing excludes provider until expiry; expiry permits routing again.

### RS-F3-002 — Same-provider retry budget
- Priority: P1
- Scope: Enforce `max_same_provider_attempts` separately from provider fallback.
- Files: `g4f/rocksoul_policy.py`, `g4f/rocksoul_execution.py`, tests.
- Acceptance: same provider cannot exceed configured retry count; global attempts and total-time limits still dominate; no loops.

### RS-F3-003 — Explicit quarantine state + CLI
- Priority: P1
- Scope: Persist an explicit quarantine lifecycle and expose `rocksoul quarantine`.
- Files: `g4f/rocksoul_db.py`, `g4f/rocksoul_intelligence.py`, `g4f/rocksoul_db_cli.py`, tests.
- Acceptance: quarantine reason/timestamp persist; quarantined providers are excluded from routing; CLI can inspect and trigger quarantine.

### RS-F3-004 — Recovery / re-admission lifecycle
- Priority: P1
- Scope: Formalize `QUARANTINED → PROBING → RE-ADMITTED`.
- Files: `g4f/rocksoul_intelligence.py`, `g4f/rocksoul_db.py`, tests.
- Acceptance: successful verification clears quarantine; failed recovery keeps it quarantined; transitions persist.

### RS-F3-005 — Canonical route explanation
- Priority: P1
- Scope: One authoritative routing explanation model.
- Files: `g4f/rocksoul_intelligence.py`, `g4f/rocksoul_execution.py`, `g4f/rocksoul_db.py`, tests.
- Acceptance: route-explain and execution trace share explanation semantics including rejection reasons, capability evidence, score inputs, and selected provider.

### RS-F3-006 — Streaming fallback safety
- Priority: P1
- Scope: Define safe fallback behavior before and after partial stream output.
- Files: `g4f/rocksoul_execution.py`, execution store, tests, docs.
- Acceptance: stream-open failure may fallback; mid-stream failure follows explicit terminal policy; trace records stream state; no hidden duplicate output.

## F6 — Product CLI

### RS-F6-001 — CLI contract coverage
- Priority: P1
- Scope: Offline contract tests for `status`, `discover`, `health`, `provider`, `probe`, `verify`, `route`, `route-explain`, `execute`, `trace`, `quarantine`, `recover`.
- Acceptance: JSON shape, help, bounded failure, and no-live-provider behavior are tested.

## F7 — Certification

### RS-F7-001 — Execution release matrix
- Priority: P0
- Scope: Map release requirements to code, tests, and CI.
- Acceptance: no production-ready claim while any mandatory gate is red/open.

## F8 — Product documentation

### RS-F8-001 — Product README
- Status: DONE

### RS-F8-002 — Product architecture docs
- Status: DONE

### RS-F8-003 — Contribution / compatibility boundary
- Priority: P1
- Acceptance: contributors can identify ROCKSOUL-owned code versus runtime/provider substrate and avoid provider duplication.

## Future phases

### F4 — Mesh
BLOCKED until F1–F3 and F7 are certified.

### F5 — Arena
BLOCKED until execution metrics and F3/F7 are stable.

## Release rule

Do not merge or market the system as production-ready while P0/P1 execution-control gates remain open.
