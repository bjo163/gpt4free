# ROCKSOUL F4 Mesh Release Gate

F4 becomes production-ready only when every mandatory item below is true on the final integration head. A green F1–F3 baseline is necessary but not sufficient for Mesh certification.

## Mandatory implementation gates

### Security

- [ ] Remote node self-service mutations require HMAC-SHA256 authentication.
- [ ] Production supports per-node keys; shared secret is development compatibility only.
- [ ] Timestamp skew is bounded.
- [ ] `(node_id, nonce)` replay is rejected.
- [ ] Mesh secrets are not persisted in database rows or audit events.
- [ ] HTTPS is required by default; plaintext HTTP requires explicit private/local development policy.
- [ ] Endpoint URLs containing embedded credentials are rejected.

### Node lifecycle

- [ ] Canonical states exist: `REGISTERED`, `ACTIVE`, `DEGRADED`, `DRAINING`, `QUARANTINED`, `OFFLINE`.
- [ ] Heartbeat activates a normal registered/offline node.
- [ ] Heartbeat cannot silently make `DRAINING` or `QUARANTINED` routable.
- [ ] Heartbeat TTL marks stale nodes `OFFLINE`.
- [ ] Failure threshold isolates/quarantines only the failing node.
- [ ] Operator state changes are explicit and auditable.

### Distributed coordination

- [ ] Selection requires `ACTIVE` state.
- [ ] Capability requirements are conjunctive and fail closed.
- [ ] Per-node in-flight capacity is enforced by the control plane.
- [ ] Request IDs are idempotent for lease acquisition.
- [ ] Lease TTL is bounded and expiry returns capacity.
- [ ] Deterministic ranking has a stable node-ID tie breaker.
- [ ] Node-reported heartbeat data cannot overwrite the authoritative lease in-flight counter.

### Failure isolation

- [ ] Failed leases affect only their owning node.
- [ ] A stale/quarantined/draining node cannot receive normal work.
- [ ] No eligible node returns `None`/no lease rather than policy bypass.
- [ ] F4 node lifecycle does not mutate the independent F3 provider lifecycle.

### Observability

- [ ] Current node state is persisted.
- [ ] Lease history is persisted.
- [ ] Operational lifecycle events are queryable.
- [ ] Authentication nonce evidence is persisted only for replay detection and expires by policy.
- [ ] Operator status exposes state counts and active leases without exposing secrets.

### Operator surface

- [ ] `rocksoul-mesh` package entry point exists.
- [ ] JSON-oriented status/list/register/heartbeat/state/select/lease/release/events commands are contract-tested.
- [ ] Authenticated CLI operations fail clearly when required key material is absent.

## Verification gates

- [ ] Core Mesh tests are deterministic and offline by default.
- [ ] Mesh CLI tests are deterministic and offline by default.
- [ ] Dedicated ROCKSOUL Mesh CI is green on Ubuntu / Python 3.13.
- [ ] Dedicated ROCKSOUL Mesh CI is green on Windows / Python 3.13.
- [ ] Wheel and source-distribution build gate is green.
- [ ] Existing ROCKSOUL CI remains green.
- [ ] General repository Unittest workflow remains green.

## Compatibility gate

- [ ] `g4f/rocksoul_platform.py` legacy `MeshRegistry` remains compatibility-only and is not imported as the canonical F4 coordinator.
- [ ] Existing F1–F3 execution/provider behavior remains unchanged unless a future explicit Mesh execution adapter opts in.
- [ ] F5 Arena remains deferred.

## Production activation gate

Before a deployment actually sends work through Mesh:

- [ ] per-node production keys are provisioned via secret manager;
- [ ] node endpoints are HTTPS;
- [ ] clocks are synchronized within the configured auth-skew budget;
- [ ] heartbeat/lease TTL and capacity thresholds are reviewed for the environment;
- [ ] rollback path is documented: stop assigning new Mesh leases and continue direct F1–F3 execution.

## Certification rule

Do not mark `RS-F4-*` as `DONE`, merge F4 to `main`, or cut the F4 production release while any mandatory checkbox is false or any mandatory final-head CI gate is red.
