# ContextUnity ACDD Workflow

One host-neutral coordination plugin for ContextUnity delivery.

It owns the ACDD process, delivery profiles, capability contracts, and validation
rules. It does not own a second task database, a code runtime, or a Pi-specific
state machine.

## Authority

- Planner owns task state, evidence journal, blockers, and task files.
- ContextUnity code, contracts, and tests own runtime truth.
- This plugin resolves the required workflow and validates that evidence is
  current; it never bypasses either owner.

## Capability ports

| Capability | Adapter responsibility |
|---|---|
| `task_read` | Read the selected Planner task and current execution entry. |
| `task_write` | Patch only the selected task and its owned Planner execution record. |
| `source_map` | Produce bounded code-owner and caller evidence. |
| `docs_search` | Retrieve ContextUnity documentation evidence. |
| `structural_search` | Verify imports, callers, handlers, and control-flow claims. |
| `run_gate` | Run one exact scoped test, check, or release command. |
| `independent_review` | Obtain and record an independent review result. |

Capabilities are ports, not authority. In particular, `task_read` and
`task_write` operate through the Planner adapter; the plugin does not
independently “control Planner”.

## Canonical profile

[`profiles/contextunity-acdd/v4.yaml`](profiles/contextunity-acdd/v4.yaml)
is the ContextUnity delivery profile. It extends
[`contracts/acdd/v1.yaml`](contracts/acdd/v1.yaml), which defines the
host-neutral capability contract.

## Migration

The existing ContextUnity and Planner procedures are migration sources. Move one
canonical skill or reference at a time, then leave a compatibility router at the
old path. Do not copy procedures or create a second set of gates.
