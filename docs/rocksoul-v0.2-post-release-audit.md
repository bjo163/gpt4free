# ROCKSOUL v0.2 Post-Release Audit

## Release truth

ROCKSOUL v0.2.0 is the certified baseline for F0-F4/F6-F8. The final main candidate passed the execution CI, Mesh CI, general unit-test workflow, and production release workflow before the GitHub release was published.

## Post-release findings

1. F4 implementation and release evidence are complete.
2. Some backlog wording on `main` still says `DONE subject to final-candidate CI` even though the final candidate has already passed and shipped. That wording should be normalized to `DONE` in a follow-up truth-sync commit.
3. Legacy `rocksoul_platform.Arena` exists but is only a small compatibility helper and is not sufficient as a certified F5 authority.
4. F5 needs a separate implementation, methodology, persistence contract, CLI, deterministic fixture suite, and CI gate so benchmarking cannot affect execution or Mesh state.

## F5 foundation added by this branch

- `g4f/rocksoul_arena.py` — canonical benchmark core.
- `g4f/rocksoul_arena_cli.py` — `rocksoul-arena` operator surface.
- `tests/test_rocksoul_arena.py` — deterministic methodology/storage coverage.
- `tests/test_rocksoul_arena_cli.py` — CLI contract coverage.
- `.github/workflows/rocksoul-arena-ci.yml` — independent Ubuntu/Windows verification gate.
- `docs/rocksoul-arena.md` — benchmark methodology and failure boundary.
- `docs/rocksoul-arena-release-gate.md` — certification checklist.

## Guardrails

The F5 foundation does not change production provider routing, provider health state, recovery state, Mesh node state, or Mesh capacity leases. Latency is stored as evidence but is not part of the default correctness score. Suite content is versioned and content-addressed so benchmark identity is explicit.

## Remaining before F5 production certification

- final-head Arena CI must be green on Ubuntu and Windows;
- existing ROCKSOUL and general repository regression workflows must remain green;
- real benchmark packs need explicit source/version metadata and target revision metadata;
- any future live-model benchmark adapter must preserve the same deterministic evidence contract and must not mutate production lifecycle state.
