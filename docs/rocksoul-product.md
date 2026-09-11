# ROCKSOUL Product

## What it is

ROCKSOUL is an execution intelligence product for multi-provider AI runtimes.

It adds a control plane around an existing provider runtime instead of replacing it. The product makes provider execution observable, routable, bounded, recoverable, and explainable.

## Product promise

**One request. Many possible providers. One controlled execution path.**

ROCKSOUL turns provider variability into a managed execution system:

`request → capability filter → ranked route → bounded execution → trace → health evidence → recovery`

## Product pillars

### Route
Choose eligible providers using model verification, capabilities, health, latency, and deterministic ordering.

### Execute
Run through the existing runtime client. ROCKSOUL owns policy and orchestration, not provider-specific implementation.

### Learn
Convert real execution outcomes into health evidence so routing improves from actual behavior.

### Explain
Expose why a provider was selected or rejected and preserve the decision for later trace inspection.

### Recover
Quarantine unhealthy providers, probe them deliberately, and re-admit them only after recovery criteria pass.

### Scale later
Mesh and Arena are deliberately separate phases. Distributed execution and benchmarking are not allowed to destabilize the local execution core.

## Architecture boundary

```text
                    ROCKSOUL PRODUCT
┌──────────────────────────────────────────────────────────┐
│ Route • Policy • Execute • Trace • Health • Recovery    │
│ CLI • future API • future Mesh • future Arena            │
└───────────────────────────┬──────────────────────────────┘
                            │
                    existing runtime API
                            │
┌───────────────────────────▼──────────────────────────────┐
│                    g4f runtime substrate                 │
│       Client • provider adapters • model transports      │
└──────────────────────────────────────────────────────────┘
```

### Ownership rule

ROCKSOUL owns the **control plane**. The runtime owns the **provider implementations**.

ROCKSOUL must never become a second provider registry, a second HTTP adapter library, or a forked implementation of provider behavior merely to gain execution control.

## Execution lifecycle

```text
REQUEST
  ↓
NORMALIZE
  ↓
CAPABILITY / MODEL ELIGIBILITY
  ↓
ROUTE + EXPLAIN
  ↓
EXECUTE ATTEMPT #1
  ├─ success → TRACE → HEALTH EVIDENCE → DONE
  └─ failure → CLASSIFY → POLICY
                    ├─ terminal → DONE
                    ├─ cooldown → NEXT PROVIDER
                    ├─ recompute → ROUTE AGAIN
                    └─ bounded retry → RETRY POLICY
```

## Reliability contract

Every execution has:

- a unique request ID;
- bounded total attempts;
- bounded total execution time;
- per-provider retry limits;
- a deterministic error taxonomy;
- a persisted attempt history;
- an explicit terminal outcome.

A request must never enter an infinite retry loop.

## Provider state

The target lifecycle is:

`ACTIVE → DEGRADED → QUARANTINED → PROBING → RE_ADMITTED`

Health evidence should come from both controlled probes and real execution. Manual quarantine must not require synthetic failures.

## Capability trust levels

Capabilities are intentionally separated into:

`DECLARED → DETECTED → VERIFIED`

Routing that requires a capability should only accept a provider when the capability satisfies the required trust level.

## Product roadmap

### F0 — Guardrails
Freeze boundaries, identity, terminal outcomes, and test rules.

### F1 — Execution
Introduce request/attempt/result contracts and bounded fallback through the existing client.

### F2 — Trace
Persist runs, attempts, route decisions, and actual execution evidence.

### F3 — Adaptive reliability
Complete retry policy, cooldown, quarantine, recovery, re-admission, and safe streaming semantics.

### F4 — Mesh
Local-first node abstraction followed by remote nodes.

### F5 — Arena
Repeatable benchmarks, metrics, and provider comparison.

### F6 — Product CLI/API
Stable operator-facing interfaces and machine-readable output.

### F7 — Verification
Offline tests and release matrix.

### F8 — Product documentation
Product-facing documentation, contributor rules, compatibility boundary, and release notes.

## Current release rule

F4 Mesh and F5 Arena remain blocked until F1-F3 reliability gates are green. A feature being scaffolded is not equivalent to the release gate being satisfied.

## Relationship to g4f

This repository contains a g4f-based runtime plus the ROCKSOUL product layer. Product documentation should describe ROCKSOUL as the primary control-plane experience while remaining accurate about the underlying runtime and upstream attribution.

Do not claim that ROCKSOUL owns or authored upstream provider implementations that it does not own.
