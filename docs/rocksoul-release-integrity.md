# ROCKSOUL Release Integrity

The production-release workflow treats package version and release notes as one release contract.

## Invariants

1. `pyproject.toml` is the package-version source.
2. The first non-empty line of `RELEASE_NOTES.md` must identify the same `v<version>`.
3. A mismatched version/notes pair fails before tag or release mutation.
4. Existing version tags are immutable.
5. If a GitHub Release already exists for the current tag, its mutable title and notes are reconciled from `RELEASE_NOTES.md` rather than left stale.
6. Corrective code changes require a new version; only release metadata is reconciled for an existing tag.

## Safe release sequence

A version bump may land before release notes, but the release workflow will fail closed and publish nothing until the notes identify the same version. Once the notes are ready, the next matching workflow run may create the immutable tag/release, or reconcile metadata if that release already exists.

This prevents the v0.2.1 failure mode where a version bump triggered publication before the corresponding release-note update reached `main`.
