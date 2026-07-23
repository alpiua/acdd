# ACDD Workflow

Portable, host-neutral Agentic Contract-Driven Development workflow. The plugin
defines the methodology, gate order, capability contract, receipt rules, and
generic execution skills. Task systems, codebases, and review hosts implement
their own adapters outside the plugin.

## Methodology

ACDD turns one bound task into an ordered chain of falsifiable claims:

1. **Bind** — select one task, authority, scope, owners, proof IDs, commands,
   and blockers.
2. **Matrix** — map the contract across runtime owners, callers, alternate paths,
   authorization, failure behavior, lifecycle, and cleanup.
3. **Architecture (G0)** — independently verify that the contract identifies one
   coherent production path and leaves no implementation decision to guesswork.
   Implementation remains prohibited while G0 is unresolved.
4. **Red** — run the smallest expected failing proof for the approved slice.
5. **Runtime** — implement through the real caller and prove the focused success
   and failure paths.
6. **Parity** — prove applicable behavior, failure, authorization, owner-path,
   and lifecycle parity.
7. **Security** — prove applicable identity, tenant, payload, path, event, and
   external-effect contours.
8. **Release** — run the exact bounded repository gate.
9. **Review** — obtain an independent terminal finding set and resolve accepted
   findings.
10. **Handoff** — record current receipts and blockers; close only when every
    required receipt passes and blockers are empty.

A changed source, test, configuration, generated input, dependency, environment,
or accepted review finding invalidates every affected receipt. Those gates must
run again before closure.

## Canonical files

- [`profiles/acdd/v1.yaml`](profiles/acdd/v1.yaml) — gate order, capability
  requirements, generic skill, and gate prompt.
- [`routing/acdd/v1.yaml`](routing/acdd/v1.yaml) — gate → adapter roles and
  receipt; it does not duplicate skill selection.
- [`contracts/acdd/v1.yaml`](contracts/acdd/v1.yaml) — capability ports.
- [`contracts/adapter/v1.yaml`](contracts/adapter/v1.yaml) — adapter shape.
- [`contracts/receipt/v1.yaml`](contracts/receipt/v1.yaml) — ordered receipt statuses, fingerprints and invalidation inputs.
- [`scripts/build_input_set.py`](scripts/build_input_set.py) and [`scripts/fingerprint_inputs.py`](scripts/fingerprint_inputs.py) — build auditable component locks and verify the canonical input-set fingerprint.
- [`skills/acdd-workflow`](skills/acdd-workflow/SKILL.md) — lifecycle dispatcher.
- [`skills/tdd`](skills/tdd/SKILL.md) and
  [`skills/diagnose`](skills/diagnose/SKILL.md) — generic implementation skills.

## Adapter contract

Each owner stores one `adapter.yaml` in its own `.agents/acdd/` directory.
`adapter.yaml` describes only that owner's contribution; it does not repeat the
ACDD gates.

```yaml
apiVersion: acdd/adapter/v1
kind: adapter
id: planner/v1
role: task
provides: [task_read, task_write]
procedure: ../workflows/start-planner-task.md
authority:
  taskState: ../../roadmap/phase-*/tasks/*.md
resources:
  taskTemplate: templates/task.md
  definitionOfDone: ../../roadmap/TASK_DEFINITION_OF_DONE.md
scripts:
  taskShape: scripts/check_task_shape.py
constraints:
  - Write only the bound task and its execution entry.
receipts:
  format: task-owned evidence and blockers
```

Required elements:

- `id` — stable adapter identity.
- `role` — `task`, `implementation`, or `review`.
- `provides` — capability ports actually implemented by this owner.
- `procedure` — entry procedure, resolved relative to the adapter.
- `authority` — surfaces whose truth the adapter may claim.
- `constraints` — fail-closed limits.

Optional `resources`, `scripts`, and `receipts` are also owner-local and
resolve relative to `adapter.yaml`. The task adapter persists receipts.

## Workspace binding

The nearest owner-supplied `.agents/acdd/binding.yaml` selects concrete task,
implementation, and review adapters. The plugin bundles no project, host, or
review implementation. Binding paths resolve relative to the binding file:

```yaml
apiVersion: acdd/binding/v1
kind: binding
profile: <relative path to profiles/acdd/v1.yaml>
adapters:
  task: <task adapter>
  implementation: <implementation adapter>
  review:
    default: <isolated review adapter>
    hosts: {<host>: <authorized host review adapter>}
rules: [<selection and fail-closed rules>]
```

## Agent execution

1. Load the ACDD profile and the nearest workspace binding.
2. Select the next gate by `queue`; its `guidance.skill` and
   `guidance.prompt` are the only generic skill/prompt source.
3. Use routing to resolve adapter roles and receipt type. Union the selected
   adapters' `provides`; stop if a required capability is missing.
4. Resolve and load each adapter's base `procedure`, matching
   `gateProcedures.<gate>`, and `skillExtensions.<skill>`. Resolve referenced
   resources and scripts relative to that adapter file.
5. Execute the owner-local proof and persist the routed receipt through the task
   adapter. Continue only when it passes and blockers are empty.

For example, `matrix/v1` requires task and source-discovery capabilities, so its
route selects task plus implementation roles. `architecture/v1` and `review/v1`
also require an independent review role. A host-specific reviewer is selectable
only when the binding names it, the capability is live, and any required
external authorization exists; installation alone never satisfies
`independent_review`.
