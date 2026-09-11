# ROCKSOUL Intelligence Plane

ROCKSOUL uses SQLite as the canonical local source of truth for provider intelligence.
The default database lives at `%LOCALAPPDATA%\ROCKSOUL\g4f\rocksoul.db`.

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

## Routing

```powershell
uv run rocksoul route gpt-4o
uv run rocksoul route gpt-4o --verified-only
```

Only provider/model bindings known to the database participate in SQLite routing. A successful live probe upgrades that binding to verified. Health ranking is derived from probe history, while active/auth metadata contributes bounded routing bonuses and penalties.

## CI boundary

The repository uses GitHub-hosted runners for normal CI. CI runs dependency resolution, import smoke tests, unit tests, CLI read-only smoke tests, and package builds on Ubuntu and Windows.

Live provider probing is deliberately excluded from default CI because provider availability, credentials, quotas, and external service behavior are not deterministic. Live probing is an explicit operator action or a future scheduled job with its own policy.

## State locations

```text
%LOCALAPPDATA%\ROCKSOUL\g4f\
  rocksoul.db
  intelligence\*.json        # legacy/compatibility state
  media\                     # local content-addressed media
```
