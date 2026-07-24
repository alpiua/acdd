---
title: "ACDD task and plan flows"
priority: high
area: agent-infrastructure
status: active
kind: plan
planning_profile: acdd/plan/v1
planning_shape: acdd/plan/simple/v1
planning_mode: improve
planning_status: planning
plan_binding:
  owner_kind: milestone
  owner_path: PLAN.md
  owner_ref: acdd-workflow
  spans_phases: []
planning_set:
  primary: PLAN.md
  roadmap: []
  phases: []
  milestones: []
  task_drafts: []
  live_evidence:
    - README.md
    - INSTALL.md
    - examples/README.md
  dependencies: []
---
# ACDD task and plan flows

## Planning intent

- **Outcome:** Deliver explicit task and plan profiles with runtime owner adapters.
- **Scope:** Host-neutral profiles, routing, capabilities, receipts, validation, skills, examples, and package documentation.
- **Non-goals:** Product roadmap placement and external issue activation.
- **Area:** agent infrastructure.
- **Lifecycle:** planning.
- **Bound owner:** `milestone` → `PLAN.md#acdd-workflow`.
- **Phase span:** none.

## Planning-set manifest

`PLAN.md` is the primary planning artifact. Plugin contracts, scripts, skills,
tests, and documentation provide live evidence.

## Evidence and contradictions

| Evidence | Current fact | Contradiction | Resolution |
|---|---|---|---|
| `profiles/task/v1.yaml` | Task delivery has nine ordered gates. | Review capability previously came from a detached role. | Route review through the implementation adapter. |
| `profiles/plan/v1.yaml` | Planning has ten ordered gates. | Plan review previously came from a detached role. | Route review through the plan adapter. |
| `contracts/receipt/` | Task gates use gate-specific invalidation. | Plan gates previously shared one undifferentiated input set. | Add plan gate policies. |
| `code_map_query(operation=impact)` | One bounded ContextUnity tool now provides reverse impact, risk profile, evidence, and gate recommendations. | Examples previously implied a second graph traversal was required. | Bind the dependency capability to one actual impact operation and keep the profile host-neutral. |
| `contracts/adapter/v1.yaml` | Adapters previously had no common protected-write policy. | A delivery agent could treat `.agents/**` or `AGENTS.md` as ordinary implementation scope. | Deny protected instruction paths by default and require a scoped adapter exception plus an explicit user request. |

## Architecture coherence

- `acdd/task/v1` binds one implementation task, nine ordered gates, task-owned receipts, and `acdd-task`.
- `acdd/plan/v1` binds one primary plan plus a declared planning set, ten ordered gates, primary-plan receipts, and `acdd-plan`.
- Task and implementation adapters compose delivery; the implementation adapter owns code review.
- The plan adapter owns planning-set validation and plan review.
- The optional audit adapter publishes selected terminal reports.
- Every gate route names one executor adapter: Planner task execution owns
  `architecture/v1`; ContextUnity implementation execution owns task `review/v1`.
- `architecture/v1` uses four read-only partitions and one coordinator. On FAIL,
  update only the bound G0 task contract/evidence, recompute the fingerprint, and
  launch a fresh verification. Repeat until PASS without asking whether to continue;
  never rerun an unchanged FAIL fingerprint.

## Impact

| Artifact | Domains | Owner | Change | Propagation | Mitigation | Authorization | Status |
|---|---|---|---|---|---|---|---|
| `PLAN.md` | API compatibility, operations | ACDD workflow milestone | define task, plan, review, audit, and adapter composition | profiles, adapters, validators, skills, examples, owner integrations | validate both profiles and every example/owner adapter together | bound planning intent | approved |

## Plan shape

The milestone is publishable when both profiles load independently, adapters
cover their exact capabilities, receipts follow gate-specific invalidation, and
the documented commands pass.

## Roadmap shape

The primary plan records `rationale=self-contained milestone plan` for
`roadmap-shape/v1`.

## Milestone shape

This plan is the complete `acdd-workflow` milestone slice.

## Milestone: acdd-workflow

The milestone closes only when every embedded task is `done`, its acceptance evidence is current, and plan blockers are empty.

## Tasks

### ACDD-1 — Stabilize host-neutral contracts

- **Status:** todo
- **Outcome:** Make task and plan profiles load with exact owner capability and receipt contracts.
- **Scope:** Profiles, routing, capability contracts, adapter contract, receipt policies, and validator.
- **Prerequisites:** none
- **Acceptance:**
  - Task review resolves through the implementation adapter.
  - Plan review resolves through the plan adapter.
  - Audit is an optional output extension.
  - Task and plan receipts expose exact gate policies.
  - `architecture/v1.executorAdapter` is `task`; task `review/v1.executorAdapter`
    is `implementation`.
  - The generic and Planner verification contracts require four read-only,
    non-writing, non-receipt partitions and one authoritative coordinator.
  - Capability-based validation rejects incomplete coverage or multiple verdicts.
  - Adapter write policy denies `.agents/**` and `AGENTS.md` by default,
    validates allow/deny patterns, and admits only scoped explicitly
    user-requested protected writes.
  - FAIL is retried until PASS only after task/evidence changes produce a new
    fingerprint; unchanged FAIL fingerprints are never rerun.
- **Evidence:**
  - `python3 -m pytest tests -q`.
  - Both real workspace compositions pass `validate_acdd.py`.

### ACDD-2 — Complete adapters, examples, and validation

- **Status:** todo
- **Outcome:** Provide executable `.acdd` examples for planning, code, impact, review, and audit.
- **Scope:** Linear, Jira, Planner, reviewer, codebase, audit, and simple-plan examples.
- **Prerequisites:** ACDD-1
- **Acceptance:**
  - Linear, Jira, and Planner preserve canonical hierarchy semantics.
  - Impact variants cover software, data, regulated, product, and commercial domains.
  - Reviewer adapters demonstrate task inbound verification, implementation
    closure review, plan review, and single-tool Code Map impact binding.
  - Simple-plan validation checks executable embedded tasks and closure.
- **Evidence:**
  - Adapter-loading tests.
  - `python3 scripts/check_simple_plan.py --plan examples/simple-plan/PLAN.md --strict`.

### ACDD-3 — Publish task and plan flow documentation

- **Status:** todo
- **Outcome:** Publish copyable installation and owner-integration routes.
- **Scope:** README, INSTALL, AGENTS, task/plan skills, and references.
- **Prerequisites:** ACDD-2
- **Acceptance:**
  - Commands use `.acdd` owner bundles and explicit adapters.
  - Review ownership and audit publication are described once at their owning boundaries.
  - Every local Markdown link resolves.
- **Evidence:**
  - Link validation.
  - `git diff --check`.


## Decomposition

The ordered embedded tasks are the complete decomposition with planning status
`todo`.

## ACDD inputs

```yaml
apiVersion: acdd/inputs/v1
kind: inputs
paths:
  - type: source
    path: README.md
  - type: dependency
    path: INSTALL.md
  - type: dependency
    path: examples/README.md
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

A later `acdd/task/v1` session promotes one embedded task selected by
`PLAN.md#<task-id>`.
