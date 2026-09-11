# ROCKSOUL

> **Control the route. Control the execution. Learn from every attempt.**

ROCKSOUL is a multi-provider AI execution control plane built on top of an existing provider runtime. It makes model execution **routable, bounded, observable, explainable, and recoverable** without duplicating provider implementations.

> **Runtime substrate:** g4f compatibility/runtime layer  
> **Product layer:** ROCKSOUL control plane

## What ROCKSOUL does

ROCKSOUL takes a logical AI request and turns provider variability into one controlled execution path:

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

**Route** — rank eligible providers from model verification, capability evidence, health, latency, and deterministic ordering.

**Execute** — use the existing runtime client and provider implementations with bounded fallback and retry policy.

**Learn** — feed real execution outcomes back into provider health evidence.

**Explain** — preserve why a candidate was accepted, rejected, or selected.

**Recover** — quarantine unhealthy providers, probe recovery, and re-admit deliberately.

**Scale later** — Mesh and Arena are separate phases so distributed coordination cannot destabilize the execution core.

## Why this repository is changing

This repository started from a g4f-based runtime. ROCKSOUL is now the product direction: the runtime remains the compatibility/execution substrate while ROCKSOUL becomes the operator-facing intelligence layer.

We intentionally keep the architecture additive:

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
| F0 Guardrails | ✅ | Core boundaries established |
| F1 Execution | ✅ | Contracts + bounded provider fallback |
| F2 Trace | ✅ | Runs, attempts, route decisions, execution evidence |
| F3 Reliability | 🟡 | Cooldown/quarantine/recovery/retry/streaming gates remain |
| F4 Mesh | ⛔ | Blocked by F3 release gate |
| F5 Arena | ⛔ | Blocked until execution evidence is stable |
| F6 CLI/API | 🟡 | CLI exists; full contract suite pending |
| F7 Verification | 🟡 | Expanding offline release matrix |
| F8 Product Docs | ✅ | Product docs/backlog refreshed |

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
rocksoul route <model>
rocksoul route-explain <model>
rocksoul execute <model> <message>
rocksoul trace <request_id>
rocksoul quarantine <provider>   # planned release-gate command
rocksoul recover [--provider <provider>]
```

Provider probes can require network access, credentials, cookies, or provider-specific tooling. Default unit tests do not require live providers.

## Execution guarantees

Every execution is designed around explicit bounds:

- unique `request_id`;
- maximum attempt count;
- maximum total execution time;
- per-provider retry limits;
- bounded backoff/jitter;
- deterministic error taxonomy;
- persisted attempt history;
- explicit terminal outcome.

The system must never retry forever.

## Capability trust

Provider capabilities are treated as evidence levels:

`DECLARED → DETECTED → VERIFIED`

A required capability is not satisfied merely because a provider declares support.

## Reliability model

The target lifecycle is:

`ACTIVE → DEGRADED → QUARANTINED → PROBING → RE_ADMITTED`

Actual execution outcomes and controlled probes are both part of the health signal.

## Documentation

Start here:

- [`docs/rocksoul-product.md`](docs/rocksoul-product.md) — product identity and architecture.
- [`docs/rocksoul-execution-control-plane.md`](docs/rocksoul-execution-control-plane.md) — execution/retry/trace/recovery contracts.
- [`docs/rocksoul-todo.md`](docs/rocksoul-todo.md) — granular implementation backlog and acceptance criteria.
- [`docs/rocksoul-intelligence.md`](docs/rocksoul-intelligence.md) — routing, capability, health, and recovery foundations.
- [`docs/README.md`](docs/README.md) — documentation index.

## Development rules

Changes should be small, testable, and traceable to a product requirement.

Do not:

- duplicate provider implementations inside ROCKSOUL;
- bypass capability verification when a capability is required;
- introduce infinite retry loops;
- hide failed attempts from execution traces;
- start Mesh/Arena before the F1-F3 reliability gates are green;
- describe unverified provider behavior as guaranteed support.

## Testing philosophy

ROCKSOUL tests are hermetic by default: temporary SQLite databases, fake clients, deterministic synthetic failures, and injected timing/randomness where needed. Live provider probing belongs in explicit integration/operator workflows.

## Compatibility and attribution

The package remains `gpt4free`/`g4f` for runtime compatibility while ROCKSOUL is the product/control-plane identity developed in this repository. Upstream runtime/provider implementations and ROCKSOUL-owned orchestration must remain clearly separated.

Preserve accurate attribution, licensing, and compatibility information for the underlying runtime. ROCKSOUL should never imply ownership of upstream work it does not own.

## License

See the repository license files for the governing terms.
