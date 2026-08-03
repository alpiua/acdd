---
title: "Example governed runtime milestone"
priority: high
area: agent-infrastructure
status: active
kind: plan
planning_profile: acdd/plan/v1
planning_shape: acdd/plan/simple/v1
planning_mode: create
planning_status: planning
plan_binding:
  owner_kind: milestone
  owner_path: PLAN.md
  owner_ref: governed-runtime
  spans_phases: []
planning_set:
  primary: PLAN.md
  roadmap: []
  phases: []
  milestones: []
  task_drafts: []
  live_evidence:
    - README.md
  dependencies: []
---

# Example governed runtime milestone

## Planning intent

- **Outcome:** Deliver one bounded governed runtime through the embedded tasks below.
- **Scope:** Runtime contracts, implementation, tests, and documentation.
- **Non-goals:** Roadmap management, issue-tracker projection, and task activation during planning.
- **Area:** agent infrastructure.
- **Lifecycle:** planning.
- **Bound owner:** `milestone` → `PLAN.md#governed-runtime`.
- **Phase span:** none.

## Planning-set manifest

`PLAN.md` is the primary planning artifact. Source and tests supply live evidence.

## Evidence and contradictions

| Evidence | Current fact | Contradiction | Resolution |
|---|---|---|---|
| `README.md` | The current public contract is documented. | none | Use it as the starting evidence. |

## Architecture coherence

The runtime owns deterministic transitions and delegates domain evidence to explicit owner adapters. Missing authority fails closed.

## Impact

| Artifact | Domains | Owner | Change | Propagation | Mitigation | Authorization | Status |
|---|---|---|---|---|---|---|---|
| `PLAN.md` | runtime-contract, operations | governed-runtime milestone | define the governed runtime boundary and executable slices | embedded tasks and repository gates | preserve deterministic terminal behavior and bounded owner commands | bound planning intent | approved |

## Plan shape

The plan is publishable when all embedded tasks are executable, ordered, evidence-bound, and free of unresolved implementation decisions.

## Roadmap shape

The primary plan records `rationale=self-contained milestone plan` for
`roadmap-shape/v1`.

## Milestone shape

### Milestone: governed-runtime

The milestone is complete only when every embedded task is `done`, its acceptance evidence is current, and plan blockers are empty.

## Tasks

### GW-1 — Freeze the runtime boundary

- **Status:** todo
- **Outcome:** Define the owner/runtime authority boundary.
- **Scope:** Runtime schemas and public documentation.
- **Prerequisites:** none
- **Acceptance:**
  - Runtime authority and owner authority are explicit.
  - Missing owner authority fails closed.
- **Evidence:**
  - Schema tests.
  - Documentation link check.

### GW-2 — Implement bounded execution

- **Status:** todo
- **Outcome:** Execute one bounded owner operation with deterministic terminal behavior.
- **Scope:** Runtime implementation and focused tests.
- **Prerequisites:** GW-1
- **Acceptance:**
  - Success, failure, timeout, and cancellation are terminal.
  - Late results cannot overwrite current state.
- **Evidence:**
  - Focused runtime tests.
  - Full package test suite.

## Decomposition

The ordered entries under `## Tasks` are the complete decomposition with
planning status `todo`.

## ACDD inputs

```yaml
apiVersion: acdd/inputs/v1
kind: inputs
paths:
  - type: source
    path: examples/simple-plan/README.md
  - type: dependency
    path: examples/simple-plan/.acdd-legacy/references/simple-plan.md
```

## ACDD gate evidence

```yaml
[]
```

## ACDD plan receipts

| Gate | Status | Evidence | Input fingerprint | Recorded at |
|---|---|---|---|---|
| intent/v1 | pending | pending | pending | pending |
| evidence/v1 | pending | pending | pending | pending |
| architecture/v1 | pending | pending | pending | pending |
| plan-shape/v1 | pending | pending | pending | pending |
| roadmap-shape/v1 | pending | pending | pending | pending |
| milestone-shape/v1 | pending | pending | pending | pending |
| decomposition/v1 | pending | pending | pending | pending |
| review/v1 | pending | pending | pending | pending |
| publish/v1 | pending | pending | pending | pending |
| handoff/v1 | pending | pending | pending | pending |

## Blockers

- None.

## Handoff

A later `acdd/task/v1` session promotes exactly one task selected by
`PLAN.md#<task-id>`.
