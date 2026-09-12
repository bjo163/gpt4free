# ROCKSOUL v0.1.0 — Production Foundation

First production baseline of the ROCKSOUL multi-provider AI execution control plane.

## Certified scope

- F0 guardrails and explicit product/runtime compatibility boundary.
- F1 deterministic execution contracts with bounded provider fallback.
- F2 persistent execution runs, attempts, route decisions, and trace retrieval.
- F3 reliability controls: deterministic error taxonomy, per-provider retry limits, rate-limit cooldown, quarantine, recovery probing, PROBING traffic isolation, re-admission, canonical route explanation, hard whole-request time budgeting, and conservative streaming semantics.
- F6 JSON-oriented product CLI for status, discovery, health, provider inspection, probe, verification, routing, route explanation, execution, tracing, quarantine, and recovery.
- F7 deterministic regression coverage across Ubuntu and Windows plus the repository's general compatibility unittest workflow.
- F8 synchronized product README, architecture, backlog, CLI contract, release gate, certification, contribution boundary, and migration documentation.

## Audit hardening included

- In-flight provider calls are clipped to the remaining whole-request `max_total_time` budget.
- Providers in `PROBING` state are excluded from normal production routing.
- Streaming health evidence is terminal and single-counted: a broken stream is not recorded as both success and failure.
- `rocksoul route --verified-only` remains enforced when capability filters are used.
- Total-time regression coverage is deterministic across operating systems.

## Verification evidence

The release candidate passed:

- ROCKSOUL CI on Ubuntu / Python 3.13.
- ROCKSOUL CI on Windows / Python 3.13.
- ROCKSOUL CLI smoke tests.
- Wheel and source-distribution build gate.
- General repository Unittest compatibility workflow.

## Runtime boundary

ROCKSOUL owns routing intelligence, execution policy, health evidence, traceability, recovery, and product-facing control interfaces. Existing g4f provider implementations remain the compatibility/execution substrate and are not duplicated.

## Deferred phases

F4 Mesh and F5 Arena are intentionally not activated by this release. Their foundation dependency is satisfied, but each requires a separate implementation, security, observability, and verification gate before production activation.
