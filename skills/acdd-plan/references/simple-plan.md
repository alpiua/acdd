# Simple plan

Use `acdd/plan/simple/v1` when one self-contained plan represents one milestone and keeps its executable tasks in the same document. The format is repository-neutral; a plugin, library, tool, or other bounded owner may adopt it without introducing a new ACDD owner kind.

## Ownership

The primary plan binds to `milestone`. `plan_binding.owner_path` names the primary plan itself and `owner_ref` names its `## Milestone: ...` section. This is a self-binding document shape, not a separate package or repository entity.

A simple plan declares no roadmap, phase, milestone-file, or task-file artifacts. `roadmap-shape/v1` is `inapplicable` with a plan-owned rationale. `milestone-shape/v1` validates the self-binding milestone and embedded task membership.

## Embedded task format

Under one `## Tasks` section, each task is a level-three heading:

```markdown
### GW-1 — Remove residual interpretation

- **Status:** todo
- **Outcome:** The runtime remains methodology-neutral.
- **Scope:** `src/`, `test/`, `README.md`.
- **Prerequisites:** none
- **Acceptance:**
  - No bundled methodology profile remains.
  - A generic external workflow compiles.
- **Evidence:**
  - Focused tests.
  - Residual scan.
```

Required fields are `Status`, `Outcome`, `Scope`, `Prerequisites`, `Acceptance`, and `Evidence`. Task IDs are unique. Prerequisites reference earlier embedded task IDs or use `none`; cycles and forward references are invalid.

During planning every newly authored task stays `todo`. `in_progress`, `blocked`, and `done` are execution states written only by a later authorized task session. A simple plan does not require task files, `CURRENT_EXECUTION.md`, an issue tracker, activation metadata, or Planner indexes.

## Adapter posture

The adopting repository keeps a small owner-controlled adapter. It identifies the primary plan and this format, supplies the normal plan capabilities, and may name repository-local evidence or publication commands. It does not need roadmap, phase, task-file, issue-tracker, or derived-index scripts.

The adapter does not redefine the format. Canonical task fields, statuses, milestone self-binding, and gate treatment come from `contracts/plan/simple/v1.yaml`.

## Execution handoff

A later `acdd/task/v1` session addresses one embedded task by immutable plan path plus task ID, for example `PLAN.md#GW-2`. The task adapter owns activation, execution receipts, evidence, and status mutation. Planning itself never activates an embedded task.
