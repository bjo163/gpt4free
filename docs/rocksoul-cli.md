# ROCKSOUL CLI Contract

The `rocksoul` command is the product-facing control-plane CLI. It is JSON-oriented so automation and future web/API layers can consume stable output.

## Core commands

```text
rocksoul status
rocksoul discover
rocksoul health [provider]
rocksoul provider <provider>
rocksoul probe <provider> [--model <model>] [--type smoke|stream]
rocksoul verify <provider> [--capability <capability>]
rocksoul route <model> [--verified-only] [capability flags]
rocksoul route-explain <model> [capability flags]
rocksoul execute <model> <message> [execution limits]
rocksoul trace <request_id>
rocksoul quarantine <provider> [--reason <reason>]
rocksoul recover [--provider <provider>]
```

`mesh` and `arena` are not part of the certified F1–F3 product CLI. Legacy/future scaffolding does not enable those phases; each requires a separate release gate.

## Routing contract

`rocksoul route` and execution use the ROCKSOUL routing evidence model: provider lifecycle state, model binding/verification, required capability verification, health, latency, and deterministic scoring/order.

`--verified-only` is a model-binding constraint, not a scoring hint. It remains enforced when capability filters such as `--streaming`, `--tools`, `--vision`, `--structured-output`, or `--image` are also supplied.

A provider in `QUARANTINED` or `PROBING` state is excluded from normal routing. `PROBING` is reserved for explicit recovery validation and becomes routable only after successful re-admission.

## Safety rules

Live-provider commands (`probe`, `verify`, `execute`, `recover`) require an explicit user invocation. Unit tests and CLI contract tests use synthetic/local data and do not call a live provider.

`execute` enforces total-attempt, per-provider-attempt, provider-timeout, and whole-request time budgets. The effective provider wait is clipped to the remaining whole-request budget. A rate-limit failure places the provider in an explicit bounded cooldown.

Streaming is intentionally conservative: once a stream is exposed to the caller, a later stream failure is terminal for that attempt. ROCKSOUL does not silently replay the request after partial output. Health evidence is recorded at terminal stream success/failure so one stream attempt is not counted twice.

## Stable output

Product commands emit JSON on stdout. State-changing control operations return the resulting provider state, reason, and expiry where applicable. Invalid command usage or uncaught operational errors terminate with a non-zero process status.
