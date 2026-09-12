# ROCKSOUL

> **Control the route. Control the execution. Coordinate the mesh. Learn from every attempt.**

ROCKSOUL is a multi-provider AI execution control plane built on top of an existing g4f provider/runtime substrate. It makes model execution **routable, bounded, observable, explainable, recoverable, and coordinatable across trusted ROCKSOUL nodes** without duplicating provider implementations.

> **Runtime substrate:** g4f compatibility/provider layer  
> **Product layer:** ROCKSOUL control plane  
> **Current product runtime:** Python 3.13+

## What ROCKSOUL does

ROCKSOUL turns a logical AI request into one controlled execution path:

```text
REQUEST
   ↓
NORMALIZE
   ↓
CAPABILITY + MODEL ELIGIBILITY
   ↓
ROUTE + EXPLAIN
   ↓
EXECUTE
   ↓
TRACE EVERY ATTEMPT
   ↓
LEARN HEALTH
   ↓
RECOVER / RE-ADMIT
```

For distributed ROCKSOUL deployments, F4 adds a separate coordination plane:

```text
REQUEST / WORK ID
      ↓
MESH ELIGIBILITY
      ↓
ACTIVE NODE + CAPABILITY + CAPACITY
      ↓
BOUNDED LEASE
      ↓
NODE EXECUTION
      ↓
RELEASE / EXPIRE / ISOLATE FAILURE
```

### Product pillars

**Route** — rank eligible providers from model verification, capability evidence, health, latency, lifecycle state, and deterministic ordering.

**Execute** — use existing runtime provider implementations with bounded fallback, retry policy, per-provider limits, and whole-request time budgets.

**Learn** — feed terminal execution outcomes back into provider health evidence without double-counting streaming attempts.

**Explain** — preserve why a candidate was accepted, rejected, or selected.

**Recover** — quarantine unhealthy providers, isolate recovery probes from normal routing, and re-admit deliberately.

**Coordinate** — assign work across trusted ROCKSOUL nodes using authenticated lifecycle state, capability-aware selection, bounded capacity leases, deterministic ordering, and per-node failure isolation.

**Benchmark** — F5 now has a separately verified deterministic Arena foundation for immutable suite provenance, correctness scoring, persisted evidence, offline fixtures, and stable leaderboard semantics. Real production benchmark packs remain behind their own provenance and anti-contamination gate.

## Architecture boundary

```text
                     ROCKSOUL PRODUCT
┌─────────────────────────────────────────────────────────┐
│ Route • Policy • Execute • Trace • Health • Recovery   │
│ CLI • Mesh Coordination • Arena Benchmark • future API │
└──────────────────────────┬──────────────────────────────┘
                           │
                     existing runtime
                           │
┌──────────────────────────▼──────────────────────────────┐
│                   g4f runtime layer                    │
│            Client • provider adapters • transports     │
└─────────────────────────────────────────────────────────┘
```

ROCKSOUL does **not** replace or duplicate provider implementations. F3 provider lifecycle, F4 node lifecycle, and F5 benchmark evidence are deliberately separate failure/authority domains.

## Current status

| Phase | Status | Notes |
|---|---|---|
| F0 Guardrails | ✅ | Runtime boundary, request identity, hermetic unit-test rule |
| F1 Execution | ✅ | Deterministic contracts + bounded provider fallback |
| F2 Trace | ✅ | Runs, attempts, route decisions, terminal execution evidence |
| F3 Reliability | ✅ | Cooldown, retry bounds, quarantine, probing isolation, recovery, streaming integrity, hard total budget |
| F4 Mesh | ✅ | Authenticated node lifecycle, capability/capacity routing, bounded leases, observability, failure isolation |
| F5 Arena | 🧪 Foundation | Deterministic provenance/scoring/storage/CLI/CI verified; production benchmark packs deferred |
| F6 CLI | ✅ | JSON control-plane commands + routing contract coverage |
| F7 Verification | ✅ | Offline regression matrix + Ubuntu/Windows ROCKSOUL, Mesh, and Arena gates |
| F8 Product Docs | ✅ | Product docs, release gates, migration and compatibility boundary synchronized |

The published production release remains **v0.2.0**, which certifies the execution + Mesh baseline. The F5 Arena foundation was merged later and does not retroactively expand the v0.2.0 release scope or imply a new version tag.

## Quick start

The Python package/import surface remains `g4f` for compatibility. The primary execution command is `rocksoul`.

```bash
uv sync

uv run rocksoul status
uv run rocksoul discover
uv run rocksoul health
uv run rocksoul route-explain gpt-4o-mini
```

For an execution test against currently eligible providers:

```bash
uv run rocksoul execute gpt-4o-mini "Hello from ROCKSOUL"
```

Every execution returns a `request_id` for trace inspection.

## Execution CLI surface

```text
rocksoul status
rocksoul discover
rocksoul health [provider]
rocksoul provider <name>
rocksoul probe <provider>
rocksoul verify <provider>
rocksoul route <model> [--verified-only] [capability flags]
rocksoul route-explain <model> [capability flags]
rocksoul execute <model> <message>
rocksoul trace <request_id>
rocksoul quarantine <provider>
rocksoul recover [--provider <provider>]
```

Provider probes can require network access, credentials, cookies, or provider-specific tooling. Default unit tests do not require live providers.

## Mesh operator surface

F4 exposes a separate `rocksoul-mesh` command so node coordination does not get mixed into provider routing commands.

```text
rocksoul-mesh status
rocksoul-mesh list
rocksoul-mesh register <node> <endpoint> [--capability <name>] [--weight <n>]
rocksoul-mesh heartbeat <node> [--health <n>] [--latency-ms <n>]
rocksoul-mesh state <node> <state> [--reason <text>]
rocksoul-mesh select [--capability <name>]
rocksoul-mesh lease <request-id> [--capability <name>] [--ttl <seconds>]
rocksoul-mesh release <lease-id> --success|--failure [--latency-ms <n>] [--error <text>]
rocksoul-mesh events [--node <node>] [--limit <n>]
```

Production deployments should provision **per-node secrets** through a secret manager using `ROCKSOUL_MESH_KEYS_JSON`. `ROCKSOUL_MESH_SECRET` is available for development compatibility. Node endpoints require HTTPS by default; local/private HTTP requires an explicit development override.

## Arena foundation surface

F5 exposes a separate `rocksoul-arena` command so benchmark evidence remains isolated from provider routing and Mesh coordination.

```text
rocksoul-arena status
rocksoul-arena fixture [--target perfect|mixed|failing]
rocksoul-arena fixture-manifest [--register]
rocksoul-arena runs [--suite-digest <digest>] [--limit <n>]
rocksoul-arena show <run-id>
rocksoul-arena leaderboard [--suite-digest <digest>]
```

The built-in fixture is deterministic and offline. It proves the Arena methodology/storage/CLI contract; it does **not** claim live provider/model quality. The canonical F5 implementation is `g4f/rocksoul_arena.py`; legacy `rocksoul_platform.Arena` remains compatibility-only.

## Execution guarantees

The certified execution baseline is designed around explicit bounds and traceable state:

- unique `request_id`;
- maximum global attempt count;
- maximum same-provider attempt count;
- whole-request execution budget;
- in-flight provider timeout clipped to the remaining whole-request budget;
- bounded backoff/jitter;
- deterministic error taxonomy;
- persisted attempt history;
- explicit cooldown/quarantine/recovery lifecycle;
- `PROBING` isolation from normal traffic;
- one terminal health signal per streaming attempt;
- explicit terminal or active-stream outcome.

The system must never retry forever.

## Mesh guarantees

F4 adds independent node-level coordination invariants:

- HMAC-SHA256 node authentication with bounded timestamp skew;
- `(node_id, nonce)` replay protection;
- explicit `REGISTERED`, `ACTIVE`, `DEGRADED`, `DRAINING`, `QUARANTINED`, and `OFFLINE` states;
- heartbeat expiry removes stale nodes from normal selection;
- only `ACTIVE` nodes can receive normal work;
- requested capabilities are conjunctive and fail closed;
- authoritative in-flight capacity is owned by control-plane leases, not heartbeat claims;
- one request ID maps idempotently to at most one lease;
- lease TTL returns abandoned capacity;
- repeated failures isolate only the failing node;
- state transitions and leases are persisted as audit evidence.

## Arena foundation guarantees

F5 foundation adds independent benchmark invariants:

- suite name/version and content-addressed SHA-256 identity;
- immutable content under one `(name, version)` pair;
- deterministic case ordering and explicit bounded weights;
- deterministic `exact` / `json_exact` correctness evaluators;
- failed executions remain visible as zero-score evidence;
- latency is recorded as evidence but does not alter the default correctness score;
- suite/run/per-case evidence is persisted in SQLite;
- raw outputs are not retained by default; output digests are stored instead;
- leaderboard uses each target's latest run instead of historical-best cherry-picking;
- Arena cannot mutate F3 provider or F4 Mesh lifecycle state.

## Capability trust

Provider capabilities are treated as evidence levels:

`DECLARED → DETECTED → VERIFIED`

A required provider capability is not satisfied merely because a provider declares support. `route --verified-only` remains enforced even when capability filters are combined with the route request.

Mesh node capabilities are authenticated node advertisements used for node eligibility; they do not replace F3 provider capability verification inside the selected node's execution path.

## Reliability lifecycle

Provider lifecycle:

```text
ACTIVE → DEGRADED → QUARANTINED → PROBING → RE_ADMITTED
```

`PROBING` is recovery-only state and is deliberately excluded from normal provider routing until explicit re-admission.

Mesh node lifecycle:

```text
REGISTERED → ACTIVE → DEGRADED → QUARANTINED
                 ↘ DRAINING
                 ↘ OFFLINE
```

The two lifecycles are deliberately independent.

## Streaming contract

Once a stream is exposed to the caller, ROCKSOUL does not silently replay it after partial output. A stream is persisted as `streaming` while active, then becomes success, failure, or abandonment. Health evidence is recorded only at terminal success/failure so one broken stream is not counted as both a success and a failure.

## Documentation

Start here:

- [`docs/rocksoul-product.md`](docs/rocksoul-product.md) — product identity and architecture.
- [`docs/rocksoul-execution-control-plane.md`](docs/rocksoul-execution-control-plane.md) — execution/retry/trace/recovery contracts.
- [`docs/rocksoul-mesh.md`](docs/rocksoul-mesh.md) — F4 security, lifecycle, coordination, failure-boundary, and deployment contract.
- [`docs/rocksoul-mesh-release-gate.md`](docs/rocksoul-mesh-release-gate.md) — independent F4 production gate.
- [`docs/rocksoul-arena.md`](docs/rocksoul-arena.md) — F5 deterministic benchmark methodology and failure boundary.
- [`docs/rocksoul-arena-release-gate.md`](docs/rocksoul-arena-release-gate.md) — F5 foundation verification + production benchmark-pack gate.
- [`docs/rocksoul-v0.2-post-release-audit.md`](docs/rocksoul-v0.2-post-release-audit.md) — post-release truth audit and F5 handoff.
- [`docs/rocksoul-todo.md`](docs/rocksoul-todo.md) — canonical granular backlog and acceptance evidence.
- [`docs/rocksoul-release-gate.md`](docs/rocksoul-release-gate.md) — aggregate mandatory release checklist.
- [`docs/rocksoul-release-certification.md`](docs/rocksoul-release-certification.md) — certified production scope.
- [`docs/rocksoul-cli.md`](docs/rocksoul-cli.md) — execution control-plane CLI contract.
- [`docs/ROCKSOUL-MIGRATION.md`](docs/ROCKSOUL-MIGRATION.md) — standalone migration plan.

## Development rules

Changes should be small, testable, and traceable to a product requirement.

Do not:

- duplicate provider implementations inside ROCKSOUL;
- bypass capability/model verification constraints requested by the caller;
- route normal requests to `QUARANTINED` or `PROBING` providers;
- route Mesh work to non-`ACTIVE` nodes;
- let node heartbeat claims overwrite control-plane lease capacity;
- introduce infinite retry loops or unbounded leases;
- hide failed attempts, leases, lifecycle changes, or benchmark failures from evidence;
- double-count one stream attempt as multiple health outcomes;
- use the compatibility-only legacy `MeshRegistry` as the canonical F4 coordinator;
- use compatibility-only `rocksoul_platform.Arena` as the canonical F5 benchmark authority;
- let Arena benchmark results mutate production provider or Mesh lifecycle state;
- describe unverified provider behavior or unqualified benchmark results as guaranteed support/quality.

## Testing philosophy

ROCKSOUL tests are hermetic by default: temporary SQLite databases, fake clients, deterministic synthetic failures, and injected timing/randomness where needed. Live provider probing, real distributed node traffic, and live benchmark packs belong in explicit integration/operator workflows.

The required execution ROCKSOUL CI matrix runs on Ubuntu and Windows with Python 3.13 and includes package build validation. F4 additionally has a dedicated ROCKSOUL Mesh CI matrix on Ubuntu and Windows. F5 foundation adds a dedicated ROCKSOUL Arena CI matrix with deterministic core/CLI tests, CLI smoke, and package build validation. The repository's general Unittest workflow remains an additional compatibility gate.

## Compatibility and legacy surface

The package remains `gpt4free`/`g4f` for runtime compatibility while ROCKSOUL is the product/control-plane identity developed in this repository. Upstream runtime/provider implementations and ROCKSOUL-owned orchestration must remain clearly separated.

The `rocksoul-legacy` entry point is compatibility-only. It is **not** the canonical routing, Mesh, or Arena control-plane contract. Product provider routing is owned by `ExplainableRouter` and the `rocksoul` CLI; product Mesh coordination is owned by `g4f.rocksoul_mesh.MeshStore` and the `rocksoul-mesh` CLI; the F5 benchmark foundation is owned by `g4f.rocksoul_arena.ArenaStore` and the `rocksoul-arena` CLI.

Preserve accurate attribution, licensing, and compatibility information for the underlying runtime. ROCKSOUL should never imply ownership of upstream work it does not own.

## License

See the repository license files for the governing terms.
