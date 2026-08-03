---
name: acdd-design
description: Prepare the design/v1 ACDD gate.
---

# design/v1

## Load

Read the document, selected profile, and owner adapter. Load only the current
check section. Then append the bound `promptAppend` fragment, if present.

## design-basis

Write several short prose paragraphs (not only a table or bullet list) that
state **what** this change is, **why** it exists, **what it connects to**, and
**who** uses or owns it, plus how it sits in the repository's planning
authority when one exists (roadmap, phase, plan, or equivalent). Use finished
formulations only: no scratchpad thinking, rejected-proposal history, or
negatives except durable non-goals/decisions with a real owner or fact. Then
record the outcome, affected users or systems, non-goals, acceptance result,
the reachable scenario, canonical owner, trust or persistence boundary,
affected callers, and forbidden effects. Stop for a user decision on public,
persisted, security, concurrency, migration, or compatibility changes. Record
classified references covering the declared input scope.

Before filling the basis, survey the repo's current planning set and roadmap
(or equivalent authority docs) so the prose and boundaries match live context.
Repository-specific paths, depth, and house style belong in `promptAppend`.

## plan-shape

Declare Inputs and bounded subtasks before implementation. Every subtask needs
explicit writes, reads, acceptance, and dependencies.

## Evidence

Record the basis check with classified references and the plan-shape check
with its bound command. For acdd/plan/v1 with plan.no-artifact, record neither
check; finalize inapplicable with that reason code. Otherwise finalize only
after both are current.
