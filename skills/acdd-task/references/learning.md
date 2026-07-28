# Workflow learning

Run after the terminal review report is complete. This analysis improves later
work; it does not change the reviewed verdict or invalidate earlier receipts.

1. Cluster confirmed findings by missed invariant, not by edited file.
2. Trace how each cluster escaped task authoring, architecture review, RED,
   runtime/parity/security gates, and final review.
3. Propose the smallest prevention improvement at its canonical owner:
   task-only proof, project guidance, canonical ACDD guidance, validator, or
   executable gate.
4. Classify each proposal as `advisory`, `candidate-required`, or `rejected`.
   Prefer guidance until repeated evidence justifies a blocking rule.
5. Record the task guidance snapshot. Mark later recommendations
   `not-in-task-snapshot`; apply them prospectively or through an authorized G1
   amendment.

Publish bounded `workflowLearning` with the audit report:

```yaml
workflowLearning:
  apiVersion: acdd/workflow-learning/v1
  kind: workflow-learning
  status: analyzed
  guidanceSnapshot: acdd/architecture-guidance/v1 | historical:no-snapshot
  candidates:
    - id: stable-id
      sourceFindings: [F-EXAMPLE]
      missedInvariant: bounded statement
      prevention: bounded workflow improvement
      scope: task | project | canonical
      disposition: advisory | candidate-required | rejected
```

An empty finding set still records `status: analyzed` and `candidates: []`.
`candidate-required` opens a governance change; it does not retroactively block
the reviewed task.
