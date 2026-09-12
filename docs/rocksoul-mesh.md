# ROCKSOUL Mesh — F4 Coordination Contract

ROCKSOUL Mesh is the distributed coordination plane that sits above the certified F1–F3 execution foundation. It does **not** replace provider implementations, provider routing, or the existing execution engine. Its job is to decide which healthy ROCKSOUL node may accept a unit of work, reserve bounded capacity, and preserve an auditable node lifecycle.

## Product boundary

The production Mesh implementation is `g4f/rocksoul_mesh.py`. The older `MeshRegistry` inside `g4f/rocksoul_platform.py` remains compatibility-only legacy scaffolding and is not a production routing authority.

Mesh is transport-neutral. An HTTP, worker, RPC, or queue adapter may carry Mesh messages, but the security/lifecycle/lease rules in this document are the canonical contract. F4 does not certify arbitrary remote-code execution.

## Trust model

### Node identity

Remote node self-service operations use HMAC-SHA256 authentication over a canonical envelope containing:

- action
- node ID
- timestamp
- nonce
- canonical JSON payload

Production deployments should provision a distinct secret per node. A single shared secret remains supported for local/development compatibility only.

Secrets are injected into the process and are never persisted in Mesh SQLite tables or written into audit events.

### Replay protection

Each authenticated nonce is stored with the node ID. A reused `(node_id, nonce)` pair is rejected. Old nonce records are garbage-collected after the configured nonce TTL. Authentication also rejects messages outside the configured clock-skew window.

### Endpoint policy

Production node endpoints must use HTTPS. Plain HTTP is rejected unless `allow_insecure_local` is explicitly enabled and the endpoint is `localhost`, loopback, or a private literal IP address. URLs containing embedded credentials or fragments are rejected.

### Operator boundary

Trusted local operator actions use explicit operator methods/CLI commands. They are deliberately separate from authenticated node-self-service calls, so remote nodes cannot silently inherit operator authority.

## Node lifecycle

Canonical states:

`REGISTERED → ACTIVE → DEGRADED → QUARANTINED`

Additional operator/runtime states:

- `DRAINING` — registered but intentionally excluded from new work.
- `OFFLINE` — heartbeat TTL expired.

Lifecycle rules:

1. Registration creates or refreshes a `REGISTERED` node.
2. A valid authenticated heartbeat activates a normal node.
3. `DRAINING` and `QUARANTINED` remain non-routable even when heartbeats arrive.
4. Failures increment a per-node streak. Before the threshold the node becomes `DEGRADED`; at the threshold it becomes `QUARANTINED`.
5. Heartbeat expiry moves `REGISTERED`, `ACTIVE`, or `DEGRADED` nodes to `OFFLINE`.
6. Operator state changes are explicit and audited.

No state transition in Mesh changes the provider-control lifecycle from F3; node health and provider health are separate failure domains.

## Coordination and leases

A node is eligible only when all of the following are true:

- state is `ACTIVE`;
- every requested capability is advertised by the node;
- the node is below its configured in-flight capacity;
- its heartbeat has not expired.

Eligible nodes are ordered deterministically by health/weight score, latency penalty, current load, failure penalty, then node ID as the stable tie breaker.

Work is assigned through a bounded lease:

- each request ID is idempotent and maps to at most one lease;
- lease creation reserves one unit of control-plane capacity;
- lease expiry automatically returns capacity;
- release records `SUCCEEDED` or `FAILED`;
- a failed lease degrades/quarantines only the node that owned that lease.

Remote heartbeat payloads do **not** control the authoritative in-flight counter. Capacity is owned by the control plane through leases.

## Failure isolation

Mesh must fail closed for routing without spreading one node's failure to unrelated nodes.

- stale node → `OFFLINE`, other nodes remain routable;
- repeated node failure → only that node is quarantined;
- expired lease → only its reserved capacity is released;
- `DRAINING`, `QUARANTINED`, `OFFLINE`, and `DEGRADED` nodes are excluded from normal selection;
- a missing eligible node produces no lease instead of silently bypassing capability/state policy.

## Observability

Mesh persists four state surfaces in the existing ROCKSOUL SQLite database:

- `mesh_nodes` — current lifecycle/capacity snapshot;
- `mesh_leases` — request-to-node coordination history;
- `mesh_events` — append-only operational audit events;
- `mesh_auth_nonces` — replay-protection evidence.

Audited events include registration, heartbeat, state changes, heartbeat expiry, lease acquisition, lease success/failure, node failure, and lease expiry.

## Operator CLI

`rocksoul-mesh` is the product operator surface.

Commands:

- `rocksoul-mesh status`
- `rocksoul-mesh list`
- `rocksoul-mesh register NODE ENDPOINT [--capability ...] [--weight N]`
- `rocksoul-mesh heartbeat NODE [--health N] [--latency-ms N]`
- `rocksoul-mesh state NODE STATE [--reason TEXT]`
- `rocksoul-mesh select [--capability ...]`
- `rocksoul-mesh lease REQUEST_ID [--capability ...] [--ttl SEC]`
- `rocksoul-mesh release LEASE_ID --success|--failure [--latency-ms N] [--error TEXT]`
- `rocksoul-mesh events [--node NODE] [--limit N]`

Useful environment variables:

- `ROCKSOUL_MESH_KEYS_JSON` — JSON object mapping node IDs to secrets; preferred in production when supplied through a secret manager.
- `ROCKSOUL_MESH_SECRET` — shared development secret.
- `ROCKSOUL_MESH_ALLOW_INSECURE_LOCAL=1` — explicit local/private HTTP development override.

The CLI never prints configured secrets.

## Deployment invariants

Before enabling Mesh traffic in production:

- provision per-node keys through a secret manager;
- terminate node endpoints with HTTPS;
- keep coordinator and nodes time-synchronized so the authentication skew window remains meaningful;
- set heartbeat TTL, lease TTL, capacity, and failure threshold deliberately for the deployment;
- keep the F3 provider lifecycle enabled independently of node lifecycle;
- retain SQLite durability/backup policy appropriate to the control-plane host.

## Non-goals of F4

F4 does not certify F5 Arena benchmarking, dataset provenance, benchmark scoring, or anti-gaming rules. It also does not convert the compatibility-only `rocksoul-legacy` Mesh/Arena code into a canonical product path.
