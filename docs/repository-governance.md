# ROCKSOUL Repository Governance

This document defines the repository-level controls required for a production release authority.

## Protected production branch

`main` is the production and release-authority branch. It should be protected by a GitHub repository ruleset with the following minimum policy:

- require changes through pull requests;
- require the branch to be up to date before merge;
- require successful ROCKSOUL execution CI;
- require successful ROCKSOUL Mesh CI;
- require successful ROCKSOUL Arena CI for changes that affect Arena or shared package/runtime surfaces;
- require successful general repository Unittest compatibility validation;
- require successful package/release validation where applicable;
- block force pushes;
- block branch deletion;
- require conversation resolution before merge;
- require code-owner review for release, workflow, package-version, and release-gate changes where repository plan/settings support it.

GitHub repository settings remain the enforcement authority. This file documents the expected policy and is intentionally not presented as proof that the server-side ruleset is enabled.

## Branch model

The stable topology is:

- `main` — production / release authority;
- short-lived feature or fix branches — implementation work;
- pull request into `main` — verification and merge boundary.

Merged feature branches should be deleted after their commits are reachable from `main`, unless a branch is intentionally retained for a documented long-running integration purpose.

## Release integrity

A production release is valid only when package version and release notes describe the same version. The production-release workflow must fail closed when those inputs disagree.

If a GitHub Release already exists for the current immutable version tag, the workflow must reconcile its title and notes to repository release-note truth rather than silently leaving stale metadata in place.

Version tags are immutable. Corrective changes to shipped code require a new package version; only mutable release metadata may be reconciled for an existing tag.

## Ownership

`.github/CODEOWNERS` records the expected owner for repository-sensitive surfaces. CODEOWNERS becomes an enforcement mechanism only when corresponding GitHub branch/ruleset settings require code-owner review.

## Certification boundaries

F3 execution, F4 Mesh, and F5 Arena maintain independent certification boundaries. A green foundation does not silently expand the production scope of another phase. In particular, deterministic Arena foundation certification does not by itself authorize broad live-provider/model benchmark claims.
