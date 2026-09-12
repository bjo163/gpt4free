# ROCKSOUL

> **Control the route. Control the execution. Learn from every attempt.**

ROCKSOUL is a multi-provider AI execution control plane built on top of an existing g4f provider/runtime substrate. It makes model execution **routable, bounded, observable, explainable, and recoverable** without duplicating provider implementations.

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

### Product pillars

**Route** — rank eligible providers from model verification, capability evidence, health, latency, lifecycle state, and deterministic ordering.

**Execute** — use existing runtime provider implementations with bounded fallback, retry policy, per-provider limits, and whole-request time budgets.

**Learn** — feed terminal execution outcomes back into provider health evidence without double-counting streaming attempts.

**Explain** — preserve why a candidate was accepted, rejected, or selected.

**Recover** — quarantine unhealthy providers, isolate recovery probes from normal routing, and re-admit deliberately.

**Scale later** — Mesh and Arena remain separate future release gates so distributed coordination cannot destabilize the certified execution core.

## Architecture boundary

```text
                ROCKSOUL PRODUCT
┌─────────────────────────────────────────────┐
│ Route • Policy • Execute • Trace • Health  │
│ Recovery • CLI • future API • Mesh • Arena │
└──────────────────────┬──────────────────────┘
                       │
                 existing runtime
                       │
┌──────────────────────▼──────────────────────┐
│              g4f runtime layer              │
│ Client • provider adapters • transports     │
└─────────────────────────────────────────────┘
```

ROCKSOUL does **not** replace or duplicate provider implementations.

## Current status

| Phase | Status | Notes |
|---|---|---|
| F0 Guardrails | ✅ | Runtime boundary, request identity, hermetic unit-test rule |
| F1 Execution | ✅ | Deterministic contracts + bounded provider fallback |
| F2 Trace | ✅ | Runs, attempts, route decisions, terminal execution evidence |
| F3 Reliability | ✅ | Cooldown, retry bounds, quarantine, probing isolation, recovery, streaming integrity, hard total budget |
| F4 Mesh | 💤 | Deferred to its own release/security/observability gate |
| F5 Arena | 💤 | Deferred to its own benchmark/release gate |
| F6 CLI | ✅ | JSON control-plane commands + routing contract coverage |
| F7 Verification | ✅ | Offline regression matrix + Ubuntu/Windows ROCKSOUL CI gate |
| F8 Product Docs | ✅ | Product docs, release gate, migration and compatibility boundary synchronized |

## Quick start

The Python package/import surface remains `g4f` for compatibility. The product command is `rocksoul`.

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

## CLI surface

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

## Execution guarantees

The certified baseline is designed around explicit bounds and traceable state:

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

## Capability trust

Provider capabilities are treated as evidence levels:

`DECLARED → DETECTED → VERIFIED`

A required capability is not satisfied merely because a provider declares support. `route --verified-only` remains enforced even when capability filters are combined with the route request.

## Reliability lifecycle

```text
ACTIVE → DEGRADED → QUARANTINED → PROBING → RE_ADMITTED
```

`PROBING` is recovery-only state. It is deliberately excluded from normal request routing until explicit re-admission.

## Streaming contract

Once a stream is exposed to the caller, ROCKSOUL does not silently replay it after partial output. A stream is persisted as `streaming` while active, then becomes success, failure, or abandonment. Health evidence is recorded only at terminal success/failure so one broken stream is not counted as both a success and a failure.

## Documentation

Start here:

- [`docs/rocksoul-product.md`](docs/rocksoul-product.md) — product identity and architecture.
- [`docs/rocksoul-execution-control-plane.md`](docs/rocksoul-execution-control-plane.md) — execution/retry/trace/recovery contracts.
- [`docs/rocksoul-todo.md`](docs/rocksoul-todo.md) — canonical granular backlog and acceptance evidence.
- [`docs/rocksoul-release-gate.md`](docs/rocksoul-release-gate.md) — mandatory release checklist.
- [`docs/rocksoul-release-certification.md`](docs/rocksoul-release-certification.md) — certified baseline scope.
- [`docs/rocksoul-cli.md`](docs/rocksoul-cli.md) — product CLI contract.
- [`docs/ROCKSOUL-MIGRATION.md`](docs/ROCKSOUL-MIGRATION.md) — standalone migration plan.

## Development rules

Changes should be small, testable, and traceable to a product requirement.

Do not:

- duplicate provider implementations inside ROCKSOUL;
- bypass capability/model verification constraints requested by the caller;
- route normal requests to `QUARANTINED` or `PROBING` providers;
- introduce infinite retry loops;
- hide failed attempts from execution traces;
- double-count one stream attempt as multiple health outcomes;
- enable Mesh/Arena merely because legacy/future scaffolding exists;
- describe unverified provider behavior as guaranteed support.

## Testing philosophy

ROCKSOUL tests are hermetic by default: temporary SQLite databases, fake clients, deterministic synthetic failures, and injected timing/randomness where needed. Live provider probing belongs in explicit integration/operator workflows.

The required ROCKSOUL CI matrix runs on Ubuntu and Windows with Python 3.13 and includes package build validation.

## Compatibility and legacy surface

The package remains `gpt4free`/`g4f` for runtime compatibility while ROCKSOUL is the product/control-plane identity developed in this repository. Upstream runtime/provider implementations and ROCKSOUL-owned orchestration must remain clearly separated.

The `rocksoul-legacy` entry point is compatibility-only. It is **not** the canonical routing/control-plane contract and does not certify legacy Mesh/Arena scaffolding for the current release. Product routing is owned by `ExplainableRouter` and the `rocksoul` CLI.

Preserve accurate attribution, licensing, and compatibility information for the underlying runtime. ROCKSOUL should never imply ownership of upstream work it does not own.

## License

See the repository license files for the governing terms.
