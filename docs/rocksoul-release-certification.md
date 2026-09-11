# ROCKSOUL Release Certification

## Release scope

This certification covers the F1-F3 execution control plane and the F6 product CLI. F4 Mesh and F5 Arena are deliberately out of scope until a later release.

## Certified gates

- **F0 guardrails:** request identity, existing runtime boundary, no provider duplication.
- **F1 execution:** normalized request, deterministic candidate ordering, bounded provider fallback through the existing client.
- **F2 trace:** execution run and every provider attempt are persisted; real execution becomes health evidence.
- **F3 reliability:** deterministic error taxonomy, bounded total attempts, per-provider attempt budget, explicit rate-limit cooldown, explicit quarantine, recovery probing, re-admission, and safe streaming failure behavior.
- **F6 CLI:** product commands expose JSON-oriented, automation-friendly control-plane operations.
- **F7 tests:** offline tests cover the control state machine, fallback, retry limits, cooldown, trace persistence, stream safety, and CLI contracts.
- **F8 productization:** ROCKSOUL is the product identity; g4f remains the compatibility/runtime substrate with truthful attribution.

## Non-goals

A successful F1-F3 certification does not claim that every provider works, that provider credentials are available, or that network availability is guaranteed. Live-provider operations remain runtime-dependent.

## Release rule

Do not enable Mesh or Arena merely because their future interfaces exist. They require a separate gate with their own tests, security model, observability, and failure boundaries.

## Certification checklist

```text
[ ] F0 guardrails proven
[x] F1 execution contracts and fallback
[x] F2 persistence and trace reconstruction
[x] F3 retry/cooldown/quarantine/recovery controls
[x] F6 CLI contract
[x] F7 offline regression suite
[x] F8 product docs and identity
[ ] F4 Mesh
[ ] F5 Arena
```

The unchecked F0 marker is intentional until the final release review verifies all guardrails together on the candidate commit.
