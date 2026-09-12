# ROCKSOUL Release Certification

## Release scope

This certification covers the F0–F3 execution control plane, F6 product CLI, F7 deterministic verification matrix, and F8 product documentation. F4 Mesh and F5 Arena are deliberately outside this baseline and require their own implementation/release gates before they may be enabled as product features.

## Certified gates

- **F0 guardrails:** unique request identity, explicit compatibility boundary, hermetic default tests, and no provider implementation duplication.
- **F1 execution:** normalized request, deterministic candidate ordering, bounded provider fallback through the existing client, per-attempt timeout, and whole-request budget enforcement including in-flight calls.
- **F2 trace:** execution runs and provider attempts are persisted; terminal execution outcomes become health evidence; streaming evidence is not double-counted.
- **F3 reliability:** deterministic error taxonomy, bounded global and per-provider attempts, explicit rate-limit cooldown, quarantine, recovery probing, probing isolation, re-admission, canonical route explanation, and safe streaming lifecycle behavior.
- **F6 CLI:** JSON-oriented product commands expose automation-friendly control-plane operations and preserve `--verified-only` when capability filters are used.
- **F7 tests:** offline tests cover routing, control lifecycle, fallback, retry limits, cooldown, trace persistence, stream lifecycle/evidence, total-time budgeting, and CLI contracts on the required Ubuntu/Windows CI matrix.
- **F8 productization:** ROCKSOUL is the product/control-plane identity; g4f remains the compatibility/runtime substrate with truthful attribution and an explicit standalone migration plan.

## Audit hardening included in this candidate

The final F1–F3 audit added regression-proven fixes for:

1. clipping an in-flight provider timeout to the remaining whole-request budget;
2. excluding `PROBING` providers from normal routing until explicit re-admission;
3. recording exactly one terminal health outcome for each streaming execution attempt;
4. preserving model `--verified-only` filtering when capability requirements are present;
5. making the total-budget regression test deterministic across Ubuntu and Windows.

## Non-goals

This certification does not claim that every upstream provider works, that credentials/cookies are always available, that external networks are reliable, or that a timed-out third-party provider thread can be forcibly terminated by Python after control returns. It certifies ROCKSOUL's routing, bounded waiting, lifecycle, trace, and evidence contracts around the existing runtime substrate.

## Release rule

Do not enable Mesh or Arena merely because legacy/future interfaces or scaffolding exist. Each requires a separate gate with its own tests, security model, observability, failure boundaries, and release evidence.

## Certification checklist

```text
[x] F0 guardrails proven
[x] F1 execution contracts and fallback
[x] F2 persistence and trace reconstruction
[x] F3 retry/cooldown/quarantine/probing/recovery controls
[x] F6 CLI contract
[x] F7 offline regression suite + required platform CI gate
[x] F8 product docs and compatibility boundary
[ ] F4 Mesh — deferred to separate gate
[ ] F5 Arena — deferred to separate gate
```

## Final evidence rule

The code and deterministic tests define the candidate. A merge to `main` is allowed only after the latest candidate commit is green on the required ROCKSOUL CI matrix and the general unit-test workflow. Documentation must never be used to override a red code/CI gate.
