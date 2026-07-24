---
name: acdd-plan
description: Create or improve one bounded planning set through acdd/plan/v1 with an explicit plan adapter.
---

# ACDD Plan

Use [`acdd/plan/v1`](../../profiles/plan/v1.yaml) for one primary plan and its
declared planning set.

1. Supply one plan adapter to `scripts/validate_acdd.py`.
2. Before loading or running any adapter-declared procedure, resource, or
   script, resolve its relative path from the adapter file's directory, verify
   that the resolved target exists and remains inside the adapter authority
   root, and use that resolved target. Never reinterpret it from the session
   working directory or treat a search/glob miss as proof that it is absent.
3. For an independently executed gate, treat `runtime` as provenance only.
   Never search for or invoke it as a tool. Invoke the concrete
   `launcher.target` according to `launcher.kind`, substitute declared argument
   placeholders, deliver the prompt through `launcher.promptTransport`, and
   verify that the target is available before launch.
4. Bind mode, outcome, scope, non-goals, area, lifecycle, owner kind, owner
   reference, phase span, and every changed planning artifact.
5. Preserve `roadmap → phases → milestones → tasks`; bind the plan separately to
   one roadmap, phase, milestone, or task.
6. Reconcile Planner state, live contracts/code, documentation, decisions, and
   contradictions.
7. Record adapter-owned impact for every declared planning artifact.
8. Execute the profile gates in queue order and keep typed inputs, bounded
   evidence, fingerprints, and receipts inline in the primary plan.
9. Publish task drafts with planning status, milestone ownership,
   prerequisites, and expected evidence.
10. Run `review/v1` through the plan adapter over the complete planning set.
11. Apply accepted findings, rerun affected gates, and repeat final review.
12. Use the audit adapter for a selected material plan-review report.
13. Publish links, shape, drift, and derived state; hand task candidates to a
   later `acdd/task/v1` session.

Use the [planning-set contract](references/planning-set.md). For a self-contained
milestone plan, use [`acdd/plan/simple/v1`](../../contracts/plan/simple/v1.yaml).
Build and validate terminal evidence through the
[plan receipt lifecycle](references/receipts.md).
