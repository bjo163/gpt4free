# ROCKSOUL Release Gate

## Rule

A ROCKSOUL release is product-ready only when all mandatory gates below are green on the final candidate and covered by deterministic tests. Documentation cannot override a red implementation or CI gate. F5 Arena remains a separate future phase and is not a blocker for the v0.2.0 F0–F4 baseline.

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

## F4 — Mesh

### Security
- [x] Remote node self-service messages use HMAC-SHA256 authentication.
- [x] Timestamp skew is bounded and replayed `(node_id, nonce)` values are rejected.
- [x] Production supports distinct per-node secrets.
- [x] Mesh secrets are not persisted in node/lease/event tables or emitted by the operator CLI.
- [x] HTTPS is required by default; plaintext HTTP requires explicit local/private development policy.
- [x] Embedded URL credentials/fragments are rejected.

### Lifecycle and coordination
- [x] Canonical states exist: `REGISTERED`, `ACTIVE`, `DEGRADED`, `DRAINING`, `QUARANTINED`, `OFFLINE`.
- [x] Authenticated heartbeat activates normal nodes without overriding draining/quarantine isolation.
- [x] Heartbeat TTL removes stale nodes from normal routing.
- [x] Only active nodes satisfying all requested capabilities are eligible.
- [x] Per-node in-flight capacity is controlled by leases, not heartbeat claims.
- [x] Request IDs are idempotent for lease acquisition.
- [x] Lease TTL is bounded and expiry returns capacity.
- [x] Ranking has deterministic stable node-ID tie breaking.

### Failure isolation and observability
- [x] Failed leases affect only the owning node.
- [x] Node lifecycle is independent from F3 provider lifecycle.
- [x] No eligible node fails closed instead of bypassing state/capability policy.
- [x] Current node state, lease history, replay evidence, and lifecycle events are persisted.
- [x] `rocksoul-mesh` exposes JSON status/list/register/heartbeat/state/select/lease/release/events operations.
- [x] Legacy `rocksoul_platform.MeshRegistry` remains compatibility-only and is not the canonical coordinator.

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
- [x] Offline contract tests for execution-control product commands.
- [x] Failure taxonomy regression suite.
- [x] Retry/quarantine/recovery regression suite.
- [x] Stream lifecycle/evidence regression suite.
- [x] Whole-request in-flight timeout regression suite.
- [x] Verified-only capability-routing regression suite.
- [x] Deterministic Mesh security/lifecycle/routing/lease/failure-isolation tests.
- [x] Deterministic `rocksoul-mesh` CLI contract tests.
- [x] Dedicated Mesh CI requires Ubuntu + Windows / Python 3.13 plus package build.
- [x] Existing ROCKSOUL CI remains required on Ubuntu + Windows / Python 3.13.
- [x] General repository Unittest remains a final compatibility gate.

## F8 — Productization
- [x] ROCKSOUL-first README.
- [x] Product architecture docs.
- [x] Granular backlog.
- [x] Standalone migration plan.
- [x] Contribution/compatibility boundary synchronized.
- [x] F4 Mesh architecture and independent release gate documented.

## Future

- F5 Arena: `DEFERRED` to its own benchmark/reproducibility/provenance/anti-gaming release gate. Its foundation dependency is satisfied, but Arena is not enabled by v0.2.0.

## Final-head evidence policy

A checked implementation/configuration box must map to source code, a deterministic test, or a verified repository configuration. The v0.2.0 candidate may merge only if the exact final head is green on dedicated ROCKSOUL Mesh CI, existing ROCKSOUL CI, and general Unittest. The production release workflow then reruns deterministic regression tests and package build before publishing the version tag and artifacts.
