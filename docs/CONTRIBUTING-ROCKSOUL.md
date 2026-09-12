# Contributing to ROCKSOUL

ROCKSOUL is the product/control-plane layer. Provider implementations and compatibility behavior belong to the underlying runtime boundary; product work must not duplicate those implementations.

## Change boundary

Use `g4f/rocksoul_*` for ROCKSOUL-specific control-plane logic. Reuse the existing `g4f.Client`, provider conversion, and runtime adapters instead of creating parallel provider code.

Routing changes must remain explainable and deterministic. Execution changes must preserve a unique request identity, bounded retry/timeout behavior, and persistence of every attempt. Health improvements should use real execution evidence where appropriate.

## Testing boundary

Unit and contract tests must be offline by default. Live-provider tests belong behind explicit operator commands and are never required for merge certification.

Every change that affects routing, retry, provider state, execution trace, or CLI behavior should update the corresponding product backlog item in `docs/rocksoul-todo.md` and its acceptance criteria.

## Upstream boundary

Keep the runtime compatibility layer usable independently. Avoid broad refactors of provider code from the ROCKSOUL product layer. When upstream behavior is needed, integrate through the narrowest existing runtime interface.

## Release discipline

Do not enable a later phase simply because its files exist. F4 Mesh and F5 Arena are gated on the release certification documented in `docs/rocksoul-release-certification.md`.
