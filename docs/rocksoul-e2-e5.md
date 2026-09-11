# ROCKSOUL E2–E5 Intelligence Control Plane

## E2 — Verified capabilities

Provider metadata is treated as a declaration, not proof. Capability state progresses through `DECLARED` → `DETECTED` → `VERIFIED` and is persisted in SQLite.

Supported live verification contracts:

- `streaming`: real streaming request and non-empty chunk validation.
- `tools`: real tool-enabled chat request and tool-call presence.
- `structured_output`: JSON-object response with the expected probe token.
- `vision`: image-input chat request using a tiny embedded PNG.
- `image`: image-generation request and non-empty response.

Use `uv run rocksoul verify <provider> --model <model> --capability <capability>`; repeat `--capability` to verify several capabilities. Verification is intentionally opt-in because it consumes provider quota.

## E3 — Explainable routing

`route-explain` exposes the reasons behind each candidate: model verification, health score, latency, and capability state. Required capabilities only pass when the DB contains verified evidence.

Examples:

```text
uv run rocksoul route-explain gpt-4o-mini --tools --streaming
uv run rocksoul route gpt-4o-mini --tools --streaming
```

When a capability is only declared or detected, the candidate is rejected for a required capability. This prevents provider metadata from silently becoming routing truth.

## E4 — Quarantine and recovery

Three consecutive failures place a provider into cooldown. The existing health engine calculates an exponential cooldown. `recover` explicitly probes quarantined providers and re-admits a provider only after a successful smoke probe.

```text
uv run rocksoul recover
uv run rocksoul recover --provider <provider> --model <model>
```

Recovery is evidence-producing: the successful probe also refreshes model verification and health telemetry.

## E5 — Adaptive routing

The SQLite router combines model verification, health, latency, activity defaults, authentication penalty, cooldown state, and verified capability constraints. Every routing decision is persisted in `route_decisions` for later analysis.

The intended control loop is:

```text
provider metadata
  -> live evidence
  -> SQLite intelligence
  -> health / quarantine
  -> capability filter
  -> score candidates
  -> select
  -> persist decision
```

## CI boundary

GitHub-hosted CI runs deterministic import, unit, CLI, and packaging checks. Live provider probes remain manual or scheduled so provider outages do not make normal pull requests flaky. Self-hosted runners are reserved for future private-network, local-model, GPU, or continuously running mesh nodes.
