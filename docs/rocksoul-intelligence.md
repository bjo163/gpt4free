# ROCKSOUL Intelligence Plane

ROCKSOUL uses SQLite as the canonical local source of truth for provider intelligence. The default database lives at `%LOCALAPPDATA%\ROCKSOUL\g4f\rocksoul.db`.

## Data model

- `providers` — provider metadata and lifecycle status.
- `models` — canonical model names.
- `provider_models` — provider/model compatibility and verification state.
- `capabilities` — declared, detected, and verified capabilities.
- `probe_runs` — immutable live probe observations.
- `health_snapshots` — derived health history.
- `route_decisions` — routing decisions and candidate scores.

JSON state from the original ROCKSOUL overlay is legacy/export state. It is not the canonical intelligence store.

## Discovery

```powershell
uv run rocksoul discover
uv run rocksoul status
uv run rocksoul provider Gemini
```

Discovery is local metadata inspection. It does not make provider requests.

## Live probes

Live network calls are explicit and never run as part of ordinary `health`, `discover`, or `route` commands.

```powershell
uv run rocksoul probe Gemini --model gemini-2.5-flash
uv run rocksoul probe Gemini --model gemini-2.5-flash --type stream --timeout 30
uv run rocksoul probe-all --model gpt-4o-mini --concurrency 4 --timeout 30
```

A successful smoke probe verifies a non-empty chat response. A stream probe consumes the complete stream and requires at least one chunk. Every probe persists latency, outcome, error classification, and model verification state to SQLite.

## Capability verification

Capability state is deliberately separated into `DECLARED`, `DETECTED`, and `VERIFIED`. Routing requires `VERIFIED` evidence when a capability is explicitly requested.

```powershell
uv run rocksoul verify Gemini --model gemini-2.5-flash --capability streaming
uv run rocksoul verify Gemini --model gemini-2.5-flash --capability tools
uv run rocksoul verify Gemini --model gemini-2.5-flash --capability structured_output
uv run rocksoul verify Gemini --model gemini-2.5-flash --capability vision
uv run rocksoul verify Gemini --model gemini-2.5-flash --capability image
```

Verification makes real requests only when explicitly invoked. A failed verification never upgrades the capability to verified.

## Explainable routing

```powershell
uv run rocksoul route-explain gpt-4o-mini --tools --streaming
uv run rocksoul route gpt-4o-mini --capability tools --capability streaming
uv run rocksoul route gpt-4o-mini --verified-only
```

The explainable route path records the selected provider, candidate scores, capability states, model verification, health evidence, and latency evidence. A provider with only declared/detected capability evidence is rejected when that capability is required.

## Quarantine and recovery

Three consecutive recent probe failures put a provider into a computed cooldown/quarantine state. Recovery is evidence-driven: a provider is re-admitted only after a successful smoke probe.

```powershell
uv run rocksoul recover
uv run rocksoul recover --provider Gemini --model gpt-4o-mini --timeout 20
```

No separate mutable quarantine registry is required; the state is derived from probe history and persisted health snapshots.

## CI boundary

The repository uses GitHub-hosted runners for normal CI. CI runs dependency resolution, import smoke tests, unit tests, CLI read-only smoke tests, and package builds on Ubuntu and Windows.

Live provider probing is deliberately excluded from default CI because provider availability, credentials, quotas, and external service behavior are not deterministic.

A separate scheduled/manual workflow runs bounded smoke probes on GitHub-hosted infrastructure. It is an operational intelligence job, not a merge gate; failures indicate provider health drift rather than repository build failure.

## State locations

```text
%LOCALAPPDATA%\ROCKSOUL\g4f\
  rocksoul.db
  intelligence\*.json        # legacy/compatibility state
  media\                     # local content-addressed media
```
