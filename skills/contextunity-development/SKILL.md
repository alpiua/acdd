---
name: contextunity-development
description: Host-neutral ContextUnity delivery router for a Planner-bound ACDD task.
---

# ContextUnity Development

Use this skill for one selected Planner task. The active contract is
[`contextunity-acdd/v4`](../../profiles/contextunity-acdd/v4.yaml).

1. Use `task_read` to bind one live task and its current execution entry.
2. At G0, collect bounded source, documentation, structural, and Planner evidence.
3. Record task evidence through `task_write`; Planner remains authoritative.
4. Follow focused red-green-refactor for the approved vertical slice.
5. Run exact runtime, parity, security, release, review, and handoff gates in
   profile order.
6. Use `independent_review` only for the profile-required independent result.
7. Re-run affected gates after a changed input invalidates their evidence.

The profile names required capabilities, never host tools. A host adapter maps a
capability to Codex, Pi, or another agent surface.

During migration, detailed ContextUnity references move here one at a time. Do
not duplicate them from their current owner.
