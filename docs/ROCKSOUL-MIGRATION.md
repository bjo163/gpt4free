# ROCKSOUL Standalone Migration

## Goal

Promote ROCKSOUL from a product layer inside a fork into a standalone product repository while keeping the existing runtime compatibility boundary explicit.

## Current state

This repository is a fork. GitHub Issues are disabled. ROCKSOUL work currently lives on `rocksoul/execution-f1-f3`.

## Target state

```text
ROCKSOUL repository
  ├─ product/control plane
  ├─ routing intelligence
  ├─ execution policy
  ├─ trace + health
  ├─ recovery
  ├─ CLI/API
  └─ future mesh/arena

runtime substrate
  └─ existing g4f compatibility/provider layer
```

## Migration rules

1. Preserve existing provider implementations and runtime behavior until a replacement is explicitly designed.
2. Move ROCKSOUL-owned code and docs as a coherent product surface.
3. Keep attribution and license obligations intact.
4. Do not rename `g4f` imports merely for branding if that would break compatibility.
5. Add an explicit compatibility layer so the product API does not depend on internal provider details.
6. Establish product repository issues/projects after the standalone repository is created.
7. Do not delete the current fork branch until the standalone repository is verified and reproducible.

## Cutover checklist

- [ ] Create standalone repository under the product owner.
- [ ] Import the certified ROCKSOUL baseline branch.
- [ ] Rewire repository metadata, links, badges, release URLs, and contribution links.
- [ ] Re-create GitHub Issues/Projects/Milestones because the current repository has Issues disabled.
- [ ] Verify package metadata and compatibility imports.
- [ ] Run full CI on the standalone repository.
- [ ] Tag first product release only after F1–F3/F6/F7 certification.
- [ ] Keep upstream g4f attribution and license notices.
- [ ] Document upstream sync strategy.

## Why we do not rename everything now

The current implementation depends on the g4f runtime surface. A mechanical rename would create unnecessary breakage and obscure the real architectural boundary. Product identity is therefore separated first; package/runtime migration happens only where technically justified.
