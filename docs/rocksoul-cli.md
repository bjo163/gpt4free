# ROCKSOUL CLI Contract

The `rocksoul` command is the product-facing control-plane CLI. It is intentionally JSON-oriented so automation and the future web/API layers can consume stable output.

## Core commands

```text
rocksoul status
rocksoul discover
rocksoul health [provider]
rocksoul provider <provider>
rocksoul probe <provider> [--model <model>] [--type smoke|stream]
rocksoul verify <provider> [--capability <capability>]
rocksoul route <model> [capability flags]
rocksoul route-explain <model> [capability flags]
rocksoul execute <model> <message> [execution limits]
rocksoul trace <request_id>
rocksoul quarantine <provider> [--reason <reason>]
rocksoul recover [--provider <provider>]
```

`mesh` and `arena` commands remain reserved for later product phases and are not enabled by the F1-F3 release.

## Safety rules

Live-provider commands (`probe`, `verify`, `execute`, `recover`) require an explicit user invocation. Unit tests and CLI contract tests use synthetic/local data and do not call a live provider.

`execute` enforces total-attempt, per-provider-attempt, request timeout, and total-time budgets. A rate-limit failure places the provider in an explicit bounded cooldown. A quarantined provider is not selected by the router.

Streaming is intentionally conservative: once a stream is exposed to the caller, a later stream failure is terminal for that execution attempt. ROCKSOUL does not silently replay the request after partial output.

## Stable output

All product commands emit JSON on stdout. Errors terminate the command with a non-zero exit status. State-changing control operations return the resulting provider state, reason, and expiry where applicable.
