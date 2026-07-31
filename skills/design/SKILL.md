---
name: acdd-v2-design
description: Prepare the design/v1 ACDD gate.
---

# design/v1

## Load

Read the task document, task profile, and task adapter. Load only the current
check section. Then append the bound `promptAppend` fragment, if present.

## design-basis

State the outcome, affected users or systems, non-goals, acceptance result, the
reachable scenario, canonical owner, trust or persistence boundary, affected
callers, and forbidden effects. Stop for a user decision on public, persisted,
security, concurrency, migration, or compatibility changes. Record classified
references covering the declared input scope.

## plan-shape

Declare Inputs and bounded subtasks before implementation. Every subtask needs
explicit writes, reads, acceptance, and dependencies.

## Evidence

Record the basis check with classified references and the plan-shape check
with its bound command. Finalize only after both are current.
