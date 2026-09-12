# ROCKSOUL Product Backlog

This document is the product-level summary. The canonical granular execution ledger is [`rocksoul-todo.md`](rocksoul-todo.md).

GitHub Issues are disabled for this repository, so the repository-owned backlog remains versioned with the code and must stay traceable to deterministic tests and release evidence.

## Product identity

ROCKSOUL is the product/control-plane layer. The existing g4f runtime/provider layer is the compatibility and execution substrate and is not duplicated.

## Certified F1–F3 baseline

### F3 — Adaptive execution reliability

- **RS-F3-001 Explicit rate-limit cooldown — DONE**  
  Persist bounded `DEGRADED` cooldown state and exclude it from routing until expiry.

- **RS-F3-002 Same-provider retry budget — DONE**  
  Enforce per-provider attempt bounds separately from global attempt count.

- **RS-F3-003 Explicit quarantine state + CLI — DONE**  
  Persist quarantine lifecycle and expose operator control without manufacturing fake failures.

- **RS-F3-004 Recovery / re-admission lifecycle — DONE**  
  Formalize `QUARANTINED → PROBING → RE_ADMITTED|QUARANTINED` and persist transitions.

- **RS-F3-005 Canonical route explanation — DONE**  
  Use `ExplainableRouter` as the product routing/explanation authority.

- **RS-F3-006 Streaming lifecycle safety — DONE**  
  Once a stream is exposed, do not silently replay after partial output; persist active and terminal stream state.

- **RS-F3-007 Whole-request time budget — DONE**  
  Bound routing, attempts, and backoff by one request budget.

- **RS-F3-008 In-flight budget enforcement — DONE**  
  Cap each provider wait by the remaining whole-request budget.

- **RS-F3-009 Recovery probing isolation — DONE**  
  Exclude `PROBING` providers from normal traffic until explicit re-admission.

- **RS-F3-010 Single-counted stream health evidence — DONE**  
  Record terminal success/failure evidence once per streaming attempt rather than marking success before consumption.

## F6 — Product CLI

- **RS-F6-001 CLI contract coverage — DONE**  
  Stable JSON-oriented command surface for status, discovery, health, provider inspection, probing, verification, routing, execution, tracing, quarantine, and recovery.

- **RS-F6-002 Verified-only capability routing — DONE**  
  `route --verified-only` remains enforced when capability filters are present.

## F7 — Certification

- **RS-F7-001 Execution release matrix — DONE subject to final-candidate CI**  
  Deterministic coverage exists for fallback, taxonomy, budgets, cooldown, quarantine, probing isolation, recovery, trace reconstruction, stream lifecycle/evidence, and CLI routing contracts. The candidate may merge only when the latest head is green on the required Ubuntu/Windows ROCKSOUL matrix and the general unit-test workflow.

## F8 — Product documentation

- **RS-F8-001 Product README — DONE**
- **RS-F8-002 Product architecture docs — DONE**
- **RS-F8-003 Contribution / compatibility boundary — DONE**
- **RS-F8-004 Release gate / certification truth sync — DONE**

## Future phase gates

### F4 — Mesh

**DEFERRED.** The F1–F3 foundation dependency is satisfied, but Mesh is not enabled or certified by this release. Before activation it needs a dedicated distributed-coordination contract, authentication/security model, node lifecycle, observability, failure isolation, deterministic tests, and its own CI/release gate.

### F5 — Arena

**DEFERRED.** Stable trace/health foundations now exist, but Arena is not enabled or certified by this release. It requires a separate benchmark methodology, reproducibility rules, dataset/model provenance, scoring contract, anti-gaming controls, deterministic fixtures, and its own release gate.

## Release rule

Do not merge or market the baseline as certified while the latest candidate has a red mandatory CI gate. Do not treat legacy Mesh/Arena scaffolding as product readiness; future phases become available only after their own gates are implemented and verified.
