# ROCKSOUL Execution Control Plane

## Purpose

The ROCKSOUL Execution Control Plane is the reliability layer around the existing g4f client/provider runtime. Its job is to turn a single logical request into a controlled, observable execution lifecycle without duplicating provider implementations.

## Core contracts

### `ExecutionRequest`

Carries the normalized model, messages, capability requirements, provider constraints, retry budgets, timeout, stream mode, extra runtime kwargs, and a unique `request_id`.

### `ExecutionAttempt`

Records one concrete provider attempt: provider, model, start/end timestamps, latency, status, error classification, error detail, and response validity.

### `ExecutionResult`

Represents the terminal result: success/failure, selected provider, response, complete attempt list, outcome, and final error classification.

## Runtime flow

1. Create a unique request identity.
2. Persist a `running` execution record.
3. Ask ROCKSOUL routing for eligible candidates.
4. Execute against the existing `g4f.Client` provider path.
5. Persist every attempt, including failures.
6. Convert actual execution into health evidence.
7. Classify failures through the deterministic policy.
8. Apply a bounded action: next provider, cooldown, recompute, terminal, or bounded retry.
9. Stop when success, terminal policy, maximum attempts, or total-time budget is reached.
10. Persist the terminal execution record.

## Persistence

`ExecutionTraceStore` adds two tables to the existing ROCKSOUL SQLite store:

- `execution_runs`
- `execution_attempts`

Route decisions remain in `route_decisions`, while real execution outcomes are also recorded as `probe_runs` with `probe_type=execution` so health can learn from production behavior.

## Failure taxonomy

| Class | Default action | Rationale |
|---|---|---|
| `timeout` | next provider | another transport may succeed |
| `network` | next provider | failure is normally provider-local/transient |
| `rate_limit` | cooldown + next provider | protect the limited provider and continue elsewhere |
| `auth` | next provider | credentials may only fail for one provider |
| `model_not_found` | recompute candidates | candidate set may be stale |
| `unsupported` | recompute candidates | requirements may eliminate the provider |
| `content_blocked` | terminal | do not bypass policy by replaying elsewhere |
| `unknown` | bounded retry | preserve safety while allowing transient recovery |

The taxonomy is a policy contract, not a substitute for provider-specific error normalization in the runtime.

## Retry budgets

Every execution is bounded by:

- `max_attempts`
- `max_total_time`
- `max_same_provider_attempts`
- per-request timeout
- bounded exponential backoff
- bounded jitter

The runtime must never sleep or retry beyond the remaining total-time budget.

## Required F3 state model

Provider reliability should expose explicit lifecycle states:

`ACTIVE → DEGRADED → QUARANTINED → PROBING → RE_ADMITTED`

A rate-limit decision should apply an explicit cooldown. Quarantine should be a first-class state rather than merely a derived failure streak. Recovery should move through `PROBING` and only re-admit after its recovery criteria pass.

## Route explanation

Routing has one canonical explanation source. The explanation must be derived from the same candidate/scoring path used for selection.

A decision should be able to answer:

- Why was this provider eligible?
- Which model verification supported it?
- Which capabilities were satisfied?
- What health score affected ordering?
- What latency signal affected ordering?
- Was the provider excluded by cooldown/quarantine?
- Why were higher-ranked candidates rejected?

The persisted route decision and execution trace should not disagree about the selected provider.

## Streaming safety

Streaming is different from unary execution because output may become user-visible before failure.

The required state model is:

`NOT_STARTED → STREAMING → COMPLETED`

or

`NOT_STARTED → STREAMING → FAILED_AFTER_PARTIAL`

A stream that fails after partial output must not silently replay the entire user request against another provider unless an explicit higher-level policy says that replay is safe and the caller can handle duplicate output.

## Capability model

Capabilities follow three evidence levels:

`DECLARED → DETECTED → VERIFIED`

A routing requirement must not treat an unverified declaration as equivalent to verified support. Capability checks should be model-aware where behavior is model-specific.

## Test policy

Unit tests are hermetic and must not require live provider access. Fake clients, temporary SQLite databases, deterministic clocks/RNG where needed, and synthetic failures are preferred.

Live probes belong to explicit operator commands and integration environments, not the default unit-test path.

## CLI contract

The target operator surface is:

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
rocksoul quarantine <provider>
rocksoul recover [--provider <provider>]
```

All machine-readable commands should emit stable JSON fields and deterministic exit behavior.

## Product boundary

ROCKSOUL owns orchestration, policy, routing intelligence, traceability, health, recovery, and future distributed control. The g4f runtime owns provider implementations and low-level transport behavior.

Do not create a second provider adapter stack inside ROCKSOUL.

## Release gates

F1-F3 is release-ready only when:

- fallback works;
- all required error classes have bounded actions;
- rate-limit cooldown is explicit;
- same-provider retry budget is enforced;
- all attempts are persisted;
- route decisions are explainable and consistent;
- actual execution feeds health;
- quarantine and recovery are explicit and tested;
- capability requirements are enforced;
- streaming partial-failure behavior is defined and tested;
- CLI contracts are tested;
- default tests remain offline.

F4 Mesh and F5 Arena remain blocked until these gates are green.
