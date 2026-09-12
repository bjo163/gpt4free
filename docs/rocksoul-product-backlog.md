# ROCKSOUL Product Backlog

This document is the product-level summary. The canonical granular execution ledger is [`rocksoul-todo.md`](rocksoul-todo.md).

GitHub Issues are disabled for this repository, so the repository-owned backlog remains versioned with the code and must stay traceable to deterministic tests and release evidence.

## Product identity

ROCKSOUL is the product/control-plane layer. The existing g4f runtime/provider layer is the compatibility and execution substrate and is not duplicated.

## Certified execution baseline

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

## F4 — Mesh coordination

F4 is implemented as a new product path in `g4f/rocksoul_mesh.py`; the old `MeshRegistry` in `rocksoul_platform.py` remains compatibility-only.

- **RS-F4-001 Persistent Mesh coordination — DONE**  
  Store current nodes, leases, operational events, and replay evidence in the ROCKSOUL SQLite control plane.
- **RS-F4-002 Authenticated node identity — DONE**  
  HMAC-SHA256 authentication with timestamp-skew enforcement, nonce replay protection, and per-node production keys.
- **RS-F4-003 Secure endpoint policy — DONE**  
  HTTPS by default; plaintext HTTP requires explicit localhost/private development policy.
- **RS-F4-004 Explicit node lifecycle — DONE**  
  `REGISTERED`, `ACTIVE`, `DEGRADED`, `DRAINING`, `QUARANTINED`, `OFFLINE` with heartbeat expiry and fail-closed selection.
- **RS-F4-005 Deterministic capability/capacity routing — DONE**  
  Only active nodes satisfying every requested capability and available control-plane capacity are eligible.
- **RS-F4-006 Bounded idempotent leases — DONE**  
  Request IDs map to bounded leases, reserve authoritative in-flight capacity, and return capacity at terminal release/expiry.
- **RS-F4-007 Per-node failure isolation — DONE**  
  Failed leases and node failures affect only the owning node and do not mutate F3 provider lifecycle.
- **RS-F4-008 Mesh observability + operator CLI — DONE**  
  `rocksoul-mesh` exposes JSON status/list/register/heartbeat/state/select/lease/release/events without exposing configured secrets.
- **RS-F4-009 Independent Mesh verification — DONE subject to final-candidate CI**  
  Dedicated Ubuntu/Windows Mesh CI covers deterministic core/CLI tests and package build; final merge also requires existing ROCKSOUL CI and general Unittest.

## F6 — Product CLI

- **RS-F6-001 CLI contract coverage — DONE**  
  Stable JSON-oriented command surface for status, discovery, health, provider inspection, probing, verification, routing, execution, tracing, quarantine, and recovery.
- **RS-F6-002 Verified-only capability routing — DONE**  
  `route --verified-only` remains enforced when capability filters are present.

## F7 — Certification

- **RS-F7-001 Execution release matrix — DONE subject to final-candidate CI**  
  Deterministic coverage exists for fallback, taxonomy, budgets, cooldown, quarantine, probing isolation, recovery, trace reconstruction, stream lifecycle/evidence, and CLI routing contracts.
- **RS-F7-002 Mesh release matrix — DONE subject to final-candidate CI**  
  Deterministic coverage exists for Mesh authentication, replay defense, node lifecycle, capability/capacity routing, leases, failure isolation, observability, and operator CLI.

## F8 — Product documentation

- **RS-F8-001 Product README — DONE**
- **RS-F8-002 Product architecture docs — DONE**
- **RS-F8-003 Contribution / compatibility boundary — DONE**
- **RS-F8-004 Release gate / certification truth sync — DONE**
- **RS-F8-005 F4 Mesh architecture + independent release gate — DONE**

## Future phase gate

### F5 — Arena

**DEFERRED.** Stable execution/trace/health and Mesh coordination foundations now exist, but Arena is not enabled or certified by v0.2.0. It requires a separate benchmark methodology, reproducibility rules, dataset/model provenance, scoring contract, anti-gaming controls, deterministic fixtures, and its own release gate.

## Release rule

Do not merge or market a candidate as certified while any mandatory final-head CI gate is red. F4 is certified only when the final candidate is green on dedicated ROCKSOUL Mesh CI, existing ROCKSOUL CI, and general Unittest. Do not treat legacy Mesh/Arena scaffolding as product readiness; F5 becomes available only after its own gate is implemented and verified.
