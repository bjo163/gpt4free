# ROCKSOUL Platform Overlay

The ROCKSOUL platform is a non-invasive intelligence layer on top of g4f. It does not replace provider implementations or the existing client/retry stack.

## Phase A — Reliability

`ProviderRegistry`, `HealthStore`, `ProviderCircuit`, `classify_error`, and `AdaptiveRouter` provide persisted provider health, capability filtering, latency-aware scoring, error taxonomy, cooldowns, and ordered fallback routing.

State is stored under `%LOCALAPPDATA%/ROCKSOUL/g4f/intelligence/` on Windows and the equivalent local application directory on other platforms.

## Phase B — Compatibility

`normalize_tool_calls()` converts provider-shaped tool calls into one canonical representation with a stable `id`, `index`, function `name`, and stringified JSON `arguments`.

`RocksoulClient` wraps the existing `g4f.client.Client` and delegates provider conversion back to `g4f.client.service.convert_to_provider`.

## Phase C — Intelligence

`Arena` provides deterministic benchmark primitives and produces aggregate success/latency summaries. `ProviderRegistry.bind_model()` records model-provider bindings and optional verification state for later live-probe jobs.

The router deliberately does not perform network probes during discovery. Live probing should be an explicit operation so startup remains predictable.

## Phase D — Platform

`SecurityPolicy` adds URL/tool allowlisting and blocks local/private destinations by default. `MediaStore` content-addresses downloaded media for stable local persistence. `MeshRegistry` tracks nodes with capabilities, health, and latency. `AgentRuntime` supplies a bounded tool-execution loop with the security policy applied to tool selection.

## CLI

```powershell
uv run python -m g4f.rocksoul_platform discover
uv run python -m g4f.rocksoul_platform health
uv run python -m g4f.rocksoul_platform route gpt-4o
uv run python -m g4f.rocksoul_platform route gpt-4o --require-tools --require-vision
uv run python -m g4f.rocksoul_platform normalize '[{"function":{"name":"lookup","arguments":{"q":"test"}}}]'
uv run python -m g4f.rocksoul_platform mesh
```

## Design rule

Provider implementations remain owned by g4f. ROCKSOUL adds observability, policy, routing, and platform behavior around them. This keeps the overlay resilient to upstream provider changes and minimizes merge conflicts.
