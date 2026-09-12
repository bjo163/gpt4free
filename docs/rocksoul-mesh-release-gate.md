# ROCKSOUL F4 Mesh Release Gate

F4 becomes production-ready only when every mandatory implementation item is satisfied and the exact final integration head is green on all required CI gates. A green F1–F3 baseline is necessary but not sufficient for Mesh certification.

## Mandatory implementation gates

### Security

- [x] Remote node self-service mutations require HMAC-SHA256 authentication.
- [x] Production supports per-node keys; shared secret is development compatibility only.
- [x] Timestamp skew is bounded.
- [x] `(node_id, nonce)` replay is rejected.
- [x] Mesh secrets are not persisted in database rows or audit events.
- [x] HTTPS is required by default; plaintext HTTP requires explicit private/local development policy.
- [x] Endpoint URLs containing embedded credentials or fragments are rejected.

### Node lifecycle

- [x] Canonical states exist: `REGISTERED`, `ACTIVE`, `DEGRADED`, `DRAINING`, `QUARANTINED`, `OFFLINE`.
- [x] Heartbeat activates a normal registered/offline node.
- [x] Heartbeat cannot silently make `DRAINING` or `QUARANTINED` routable.
- [x] Heartbeat TTL marks stale nodes `OFFLINE`.
- [x] Failure threshold isolates/quarantines only the failing node.
- [x] Operator state changes are explicit and auditable.

### Distributed coordination

- [x] Selection requires `ACTIVE` state.
- [x] Capability requirements are conjunctive and fail closed.
- [x] Per-node in-flight capacity is enforced by the control plane.
- [x] Request IDs are idempotent for lease acquisition.
- [x] Lease TTL is bounded and expiry returns capacity.
- [x] Deterministic ranking has a stable node-ID tie breaker.
- [x] Node-reported heartbeat data cannot overwrite the authoritative lease in-flight counter.

### Failure isolation

- [x] Failed leases affect only their owning node.
- [x] A stale/quarantined/draining/degraded node cannot receive normal work.
- [x] No eligible node returns `None`/no lease rather than policy bypass.
- [x] F4 node lifecycle does not mutate the independent F3 provider lifecycle.

### Observability

- [x] Current node state is persisted.
- [x] Lease history is persisted.
- [x] Operational lifecycle events are queryable.
- [x] Authentication nonce evidence is persisted only for replay detection and expires by policy.
- [x] Operator status exposes state counts and active leases without exposing secrets.

### Operator surface

- [x] `rocksoul-mesh` package entry point exists.
- [x] JSON-oriented status/list/register/heartbeat/state/select/lease/release/events commands are contract-tested.
- [x] Authenticated CLI operations fail clearly when required key material is absent.

## Verification gates — final candidate

These boxes are intentionally left pending until the exact certification-PR head has completed. They are updated only after the final-head runs succeed; changing this file then creates a new head that must be verified once more before merge.

- [ ] Core + CLI Mesh tests are green on final-head Ubuntu / Python 3.13.
- [ ] Core + CLI Mesh tests are green on final-head Windows / Python 3.13.
- [ ] Final-head Mesh wheel/source-distribution build is green.
- [ ] Final-head existing ROCKSOUL CI is green on Ubuntu / Python 3.13.
- [ ] Final-head existing ROCKSOUL CI is green on Windows / Python 3.13.
- [ ] Final-head general repository Unittest workflow is green.

## Compatibility gate

- [x] `g4f/rocksoul_platform.py` legacy `MeshRegistry` remains compatibility-only and is not imported as the canonical F4 coordinator.
- [x] Existing F1–F3 execution/provider behavior remains unchanged unless a future explicit Mesh execution adapter opts in.
- [x] F5 Arena remains deferred.

## Production activation gate

Release certification proves the software contract. A real deployment must additionally satisfy environment-specific controls before sending production work through Mesh:

- [ ] per-node production keys provisioned via an external secret manager;
- [ ] node endpoints deployed behind HTTPS;
- [ ] clocks synchronized within the configured authentication-skew budget;
- [ ] heartbeat/lease TTL and capacity thresholds reviewed for that environment;
- [ ] operational rollback confirmed: stop assigning new Mesh leases and continue direct F1–F3 execution.

These environment-specific activation boxes do not block publishing the software artifact; they block enabling real distributed traffic in a deployment that has not configured them.

## Certification rule

Do not merge F4 to `main` or cut the v0.2.0 production release while any final-candidate verification box is false or any mandatory final-head CI gate is red. The production release workflow must then re-run deterministic regression tests and package build before creating the immutable version tag and GitHub Release artifacts.
