# ROCKSOUL Intelligence Plane

## Role

The Intelligence Plane provides the evidence and ranking data used by the ROCKSOUL execution control plane.

It answers four questions:

1. **What can this provider/model do?**
2. **Has that capability been verified?**
3. **How healthy has this provider been?**
4. **Which eligible provider should execute the request?**

## Evidence model

Provider/model facts are not treated as equally trustworthy.

```text
DECLARED → DETECTED → VERIFIED
```

- **DECLARED**: provided by provider metadata.
- **DETECTED**: observed by an inspection or controlled signal.
- **VERIFIED**: confirmed by a successful capability-specific probe.

A required capability should be enforced using verified evidence unless the product explicitly defines another trust rule.

## Health model

Health is derived from recorded probe and execution evidence. Relevant signals include:

- total attempts;
- successes/failures;
- success rate;
- average and p95 latency;
- consecutive failures;
- cooldown state;
- last error and error classification.

Actual execution is recorded as execution evidence so the control plane learns from real behavior rather than only synthetic probes.

## Route scoring

Current route candidates combine:

- model verification;
- health score;
- default activation preference;
- authentication penalty;
- latency signal;
- required capability eligibility.

Ordering is deterministic. Provider name is the final tie-breaker so repeated decisions are reproducible.

## Explainability contract

`ExplainableRouter` is the intended canonical route explanation path. A route explanation should expose enough evidence to understand:

- eligibility;
- capability state;
- model verification;
- health score;
- latency;
- rejection reason;
- selected candidate.

Future execution traces must reuse this decision path rather than independently calculating a conflicting explanation.

## Recovery

The target lifecycle is:

`ACTIVE → DEGRADED → QUARANTINED → PROBING → RE_ADMITTED`

The current implementation has recovery probing and failure-streak-derived quarantine behavior. Explicit state and CLI controls are tracked in `docs/rocksoul-todo.md`.

## Database

The SQLite-backed intelligence store contains provider, model, provider/model binding, capability, probe, route-decision, and health-snapshot tables. Execution adds run/attempt trace tables through `ExecutionTraceStore`.

The database is deliberately local-first. It is not a shared distributed control plane yet.

## Operating commands

```bash
uv run rocksoul status
uv run rocksoul discover
uv run rocksoul health
uv run rocksoul provider <name>
uv run rocksoul probe <provider>
uv run rocksoul verify <provider>
uv run rocksoul route <model>
uv run rocksoul route-explain <model>
uv run rocksoul recover
```

Live probing is an operator/integration activity and is not required by the default unit-test suite.

## Product boundary

The Intelligence Plane is ROCKSOUL-owned control-plane logic. Provider-specific execution remains in the runtime/provider layer.

Do not move provider implementations into this plane simply to make routing easier.

## Roadmap

F0 guardrails → F1 execution → F2 trace → F3 adaptive reliability → F4 mesh → F5 arena → F6 product interfaces → F7 verification → F8 product docs.

F4 and F5 remain blocked until F3 reliability gates are complete.
