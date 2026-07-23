---
name: acdd-workflow
description: Use for an evidence-bound delivery task resolved through workspace task, implementation, and review adapters.
---

# ACDD Workflow

Use [`acdd/v1`](../../profiles/acdd/v1.yaml) for exactly one bound task.

1. Read the nearest `.agents/acdd/binding.yaml`; resolve one task adapter, one
   implementation adapter, and one available authorized review adapter.
2. Run `scripts/validate_acdd.py` from the plugin with that binding and the host
   skill settings. A missing path, skill, capability, or adapter blocks the task.
3. Select the next gate by profile `queue`. Load its `guidance.skill`, preserve
   its `guidance.prompt`, and resolve the gate route from the profile's `routing`.
4. Load each routed adapter's base `procedure`, matching
   `gateProcedures.<gate>`, and matching `skillExtensions.<guidance.skill>`.
   Resolve owner paths relative to the declaring adapter.
5. Execute the gate and persist one current receipt through `task_write` using
   the fields and terminal status in
   [`contracts/receipt/v1.yaml`](../../contracts/receipt/v1.yaml). Follow
   [receipt invalidation](references/receipts.md).
6. For `architecture/v1`, apply the generic
   [architecture gate](references/architecture.md) plus the implementation
   adapter's domain procedure. Only an independent PASS may authorize G0.
7. `red/v1` must observe the expected failure before `runtime/v1`. Use
   `inapplicable` only with a task-owned rationale.
8. Re-run every receipt invalidated by changed task, source, test, config,
   generated input, dependency, environment, or accepted finding.
9. Close only after every profile gate has a terminal current receipt and
   blockers are empty.

Adapters may strengthen a gate but never remove/reorder it, replace the profile
prompt, alter task authority, or treat a grouped checkbox as a gate receipt.
