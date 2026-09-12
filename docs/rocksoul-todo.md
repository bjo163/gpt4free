# ROCKSOUL Product Backlog

> Canonical execution backlog for the ROCKSOUL product layer. GitHub Issues are disabled in this repository, so each item below is intentionally small, testable, and traceable from code to release.

## Product identity

ROCKSOUL is the product/control-plane layer built on top of the existing g4f runtime. The runtime remains the provider execution substrate. ROCKSOUL owns routing intelligence, execution policy, health evidence, traceability, recovery, Mesh coordination, and product-facing interfaces. ROCKSOUL does not duplicate provider implementations.

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

## F4 Mesh coordination

### RS-F4-001 — Persistent Mesh coordination foundation
- Status: `DONE`
- Scope: production Mesh state is stored in the existing ROCKSOUL SQLite control-plane database without replacing F1–F3 execution/provider state.
- Implementation: `g4f/rocksoul_mesh.py` tables `mesh_nodes`, `mesh_leases`, `mesh_events`, and `mesh_auth_nonces`.
- Acceptance: node state, lease history, audit events, and replay evidence survive process boundaries and remain separate from provider lifecycle tables.
- Tests: deterministic Mesh core suite.

### RS-F4-002 — Authenticated node identity and replay protection
- Status: `DONE`
- Scope: remote node self-service operations use HMAC-SHA256 with action, node ID, timestamp, nonce, and canonical payload.
- Acceptance: invalid signatures, wrong per-node keys, stale timestamps, and replayed `(node_id, nonce)` values are rejected; secrets are not persisted in audit rows.
- Tests: `test_authenticated_registration_rejects_invalid_signature_and_replay`, `test_per_node_keys_isolate_node_identity`.

### RS-F4-003 — Secure endpoint boundary
- Status: `DONE`
- Scope: production endpoints require HTTPS; plaintext HTTP is allowed only by explicit local/private development policy.
- Acceptance: malformed endpoints, embedded credentials/fragments, and non-local plaintext endpoints fail closed.
- Tests: `test_endpoint_security_requires_https_unless_local_policy_is_explicit`.

### RS-F4-004 — Explicit node lifecycle and stale-node isolation
- Status: `DONE`
- Scope: `REGISTERED`, `ACTIVE`, `DEGRADED`, `DRAINING`, `QUARANTINED`, `OFFLINE`.
- Acceptance: authenticated heartbeat activates normal nodes, heartbeat expiry marks stale nodes offline, and heartbeat cannot silently make draining/quarantined nodes routable.
- Tests: heartbeat/offline lifecycle and state-routing assertions in `tests/test_rocksoul_mesh.py`.

### RS-F4-005 — Deterministic capability/capacity routing
- Status: `DONE`
- Scope: only active nodes satisfying every requested capability and remaining under authoritative capacity are eligible.
- Acceptance: ranking is deterministic from health, weight, latency, load, failure penalty, and stable node-ID tie breaking; no eligible node returns no selection rather than bypassing policy.
- Tests: `test_selection_respects_capabilities_score_capacity_and_idempotency`.

### RS-F4-006 — Bounded idempotent work leases
- Status: `DONE`
- Scope: request IDs map idempotently to bounded leases and reserve control-plane-owned in-flight capacity.
- Acceptance: lease TTL is finite, expiry returns capacity, and node heartbeat claims cannot overwrite authoritative in-flight counts.
- Tests: lease selection, idempotency, capacity, expiry, and release coverage in the Mesh core/CLI suites.

### RS-F4-007 — Per-node failure isolation
- Status: `DONE`
- Scope: failures degrade/quarantine only the owning node while preserving unrelated nodes and the independent F3 provider lifecycle.
- Acceptance: failed leases cannot fan out quarantine state to other nodes/providers; draining/quarantined/offline/degraded nodes remain excluded from normal Mesh work.
- Tests: `test_failure_isolation_quarantines_only_failing_node`, draining/lease-expiry assertions.

### RS-F4-008 — Mesh observability and operator CLI
- Status: `DONE`
- Scope: auditable node/lease events plus JSON-oriented `rocksoul-mesh` operator surface.
- Commands: `status`, `list`, `register`, `heartbeat`, `state`, `select`, `lease`, `release`, `events`.
- Acceptance: operator state and audit evidence are inspectable without exposing configured secrets; missing key material fails clearly.
- Tests: `tests/test_rocksoul_mesh_cli.py` plus Mesh status/event assertions.

### RS-F4-009 — Independent Mesh release gate
- Status: `DONE subject to final-candidate CI`
- Scope: dedicated F4 CI/release contract independent of legacy Mesh/Arena scaffolding.
- Acceptance: Mesh CI must pass Ubuntu/Windows Python 3.13 deterministic core+CLI tests and package build; final `main` candidate must also pass existing ROCKSOUL CI and general Unittest.
- Workflow: `.github/workflows/rocksoul-mesh-ci.yml`.

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

### RS-F7-002 — Mesh release matrix
- Status: `DONE subject to final-candidate CI`
- Coverage: Mesh auth/replay, node identity, endpoint security, lifecycle, capability/capacity routing, lease idempotency/expiry, failure isolation, audit events, and operator CLI.
- Release requirement: dedicated Mesh CI plus existing ROCKSOUL CI and general Unittest must be green on the final release candidate.

## F8 documentation and productization

### RS-F8-001 — Product README
- Status: `DONE`

### RS-F8-002 — Product architecture docs
- Status: `DONE`

### RS-F8-003 — Contributing and compatibility boundary
- Status: `DONE`

### RS-F8-004 — F4 Mesh architecture and release gate
- Status: `DONE`
- Docs: `docs/rocksoul-mesh.md`, `docs/rocksoul-mesh-release-gate.md`.

## F5 future gate

### RS-F5-001 — Arena benchmark plane
- Status: `DEFERRED`
- Foundation dependency: stable execution traces, provider health, Mesh coordination, and release certification satisfied.
- Rule: Arena remains outside the certified product until its own deterministic benchmark methodology, provenance, anti-gaming, and release contract is implemented.

## Definition of Product-Ready v0.2 Baseline

- F1 execution works through existing runtime provider implementations.
- F2 persists every attempt and final outcome.
- F3 has deterministic taxonomy, bounded retries, explicit cooldown, quarantine, probing isolation, recovery, safe streaming semantics, single-counted stream evidence, and whole-request time budgeting including in-flight calls.
- F4 has authenticated node identity, replay protection, explicit lifecycle, deterministic capability/capacity routing, bounded leases, failure isolation, auditable events, and a separate operator CLI.
- F6 execution CLI and F4 Mesh CLI are documented and contract-tested.
- F7 tests are offline by default and CI-certified on required platforms before merge.
- F8 docs use ROCKSOUL product terminology consistently.
- No duplicate provider implementation exists.
- Legacy `MeshRegistry` remains compatibility-only; it is not the canonical F4 path.
- F5 Arena is not enabled merely because legacy/future scaffolding exists.
