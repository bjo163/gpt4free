# ROCKSOUL v0.2.1 — CI Hardening & Engineering Mirror

ROCKSOUL v0.2.1 is a maintenance release following the production-certified v0.2.0 Mesh release.

## Included

- Harden scheduled ROCKSOUL live-provider probe execution against CI wall-clock cancellation.
- Increase the scheduled intelligence workflow timeout from 20 to 30 minutes.
- Increase live probe concurrency from 4 to 8 while preserving a 20-second per-provider probe timeout.
- Add a GitLab CI mirror contract for private/self-hosted engineering workflows.
- Keep GitLab shared-runner work limited to deterministic validation and package build; live provider probes, Windows coverage, and scheduled fan-out remain reserved for future self-hosted runner lanes.
- Preserve GitHub as the primary public OSS and release authority.

## Verification

- ROCKSOUL CI — Ubuntu / Python 3.13: PASS.
- ROCKSOUL CI — Windows / Python 3.13: PASS.
- ROCKSOUL CLI smoke: PASS.
- ROCKSOUL package build: PASS.
- General Unittest workflow: PASS.
- AI Code Reviewer: PASS.

## Release boundary

v0.2.1 does not expand the certified product scope into F5 production benchmark certification. F5 Arena remains a verified deterministic foundation; live production benchmark packs remain behind their own provenance, reproducibility, and anti-contamination gate.

---

# ROCKSOUL v0.2.0 — Mesh Coordination

ROCKSOUL v0.2.0 adds the first production-certified distributed coordination plane on top of the v0.1.0 execution-control foundation.

## Certified scope

This release preserves the certified F0–F3 execution, F6 CLI, F7 verification, and F8 productization baseline and adds **F4 Mesh**.

### F4 Mesh coordination

- Transport-neutral node coordinator backed by the existing ROCKSOUL SQLite control-plane database.
- Explicit node lifecycle: `REGISTERED`, `ACTIVE`, `DEGRADED`, `DRAINING`, `QUARANTINED`, and `OFFLINE`.
- HMAC-SHA256 authenticated node self-service messages with timestamp skew enforcement and per-node nonce replay protection.
- Per-node production key support; a shared secret remains development compatibility only.
- HTTPS required by default; plaintext HTTP requires an explicit localhost/private development override.
- Deterministic capability-aware node selection with health, latency, current load, failure penalty, weight, and stable node-ID tie breaking.
- Bounded, idempotent request leases with control-plane-owned in-flight capacity and automatic capacity return on lease expiry.
- Failure isolation: failed leases, heartbeat expiry, draining, and quarantine affect only the relevant node and do not mutate the independent F3 provider lifecycle.
- Persisted Mesh node state, lease history, replay-protection evidence, and operational audit events.

### Mesh operator surface

A new `rocksoul-mesh` command provides JSON-oriented operations for:

- `status`
- `list`
- `register`
- `heartbeat`
- `state`
- `select`
- `lease`
- `release`
- `events`

Production key material is supplied through environment/secret-manager inputs and is never printed by the CLI or persisted in Mesh audit rows.

## Security and failure-boundary hardening

F4 is deliberately separate from the legacy `MeshRegistry` in `g4f/rocksoul_platform.py`. The legacy surface remains compatibility-only and is not a product routing authority.

Mesh also remains separate from provider routing. F3 controls provider health/quarantine/recovery, while F4 controls node coordination. A node failure cannot silently quarantine an unrelated provider, and provider recovery does not implicitly re-admit a Mesh node.

## Verification gate

The F4 candidate is required to pass before merge to `main`:

- dedicated ROCKSOUL Mesh CI on Ubuntu / Python 3.13;
- dedicated ROCKSOUL Mesh CI on Windows / Python 3.13;
- deterministic Mesh core and CLI tests;
- wheel and source-distribution build;
- existing ROCKSOUL Ubuntu/Windows regression CI;
- general repository Unittest compatibility workflow.

The production release workflow runs the deterministic repository regression suite and package build again before creating the version tag and GitHub Release.

## Runtime boundary

Existing g4f provider implementations remain the compatibility/execution substrate and are not duplicated. ROCKSOUL owns routing intelligence, execution policy, health evidence, traceability, recovery, Mesh coordination, and product-facing control interfaces.

## Deferred phase

**F5 Arena remains deferred.** Benchmark methodology, reproducibility, dataset/model provenance, scoring, anti-gaming controls, deterministic fixtures, and an independent release gate are still required before Arena may be enabled as a production feature.
