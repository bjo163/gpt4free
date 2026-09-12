# ROCKSOUL Documentation

ROCKSOUL is the product/control-plane layer in this repository. It adds routing intelligence, bounded execution, traceability, health learning, recovery, and future mesh/arena capabilities around an existing provider runtime.

## Start here

- [ROCKSOUL Product](rocksoul-product.md) — product positioning, architecture, ownership boundary, and roadmap.
- [Execution Control Plane](rocksoul-execution-control-plane.md) — F1-F3 execution contracts, policy, trace, reliability, CLI, and release gates.
- [Granular Product Backlog](rocksoul-todo.md) — small implementation TODOs, acceptance criteria, dependencies, and phase gates.
- [ROCKSOUL Intelligence](rocksoul-intelligence.md) — routing, capability evidence, health, and recovery foundations.
- [ROCKSOUL Platform](rocksoul-platform.md) — broader platform architecture.
- [Build Workflow](build-workflow.md) — repository build and verification workflow.

## Product development rule

The ROCKSOUL layer must remain additive and compatible with the existing runtime. Provider implementations stay in the runtime/provider layer. ROCKSOUL owns control-plane behavior.

F4 Mesh and F5 Arena are blocked until F1-F3 release gates are green.
