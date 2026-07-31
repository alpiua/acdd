# Plan receipt lifecycle

Use the same inline receipt model as `acdd/task/v1`.

1. Declare typed workspace-relative source, test, configuration, generated,
   dependency, environment, and accepted-finding paths under `## ACDD inputs`.
2. Keep bounded `acdd/gate-evidence/v1` objects under
   `## ACDD gate evidence`.
3. Reference evidence only as `evidence=<id>` from the primary plan receipt
   table.
4. Let strict validation build the canonical snapshot in memory from the bound
   plan, selected profile, receipt contract, supplied adapters, and declared
   paths.
5. Persist no generated provenance files or reviewer transcript.

Missing, duplicate, escaping, undeclared, stale, or adapter-unauthorized inputs
fail closed. Basis gates use their configured validity inputs; live review,
publish, and handoff use every declared input type.

The status vocabulary is fixed. `pending` carries no evidence. `blocked` and
`partial` are evidence-bearing non-terminal statuses: a `partial` row records
complete inline evidence for a proven sub-scope, and closure remains blocked
until every gate reaches a terminal status.

For `roadmap-shape/v1` and `milestone-shape/v1`, terminal `inapplicable`
requires command evidence with `applicability` naming the `planning-set`
engine, a manifest evidence reference, every adapter impact axis checked, and
the closed reason code for that gate. Eligibility is derived from the bound
plan frontmatter `planning_set`: `roadmap-shape/v1` requires empty `roadmap`
and `phases`, and `milestone-shape/v1` requires empty `milestones` and
`task_drafts`. The validator rejects inapplicable when the planning set
declares artifacts of that kind; agent prose is never accepted. `rationale`
evidence remains available for passing shape receipts and cannot retire a
gate.

`review/v1` is never invalidated by `accepted-review-findings`: a repeat
review is driven by upstream gate reruns through `successorInvalidation`.
Publish and handoff cannot pass with blockers or a stale/nonterminal
predecessor.
