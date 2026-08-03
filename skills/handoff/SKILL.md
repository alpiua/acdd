---
name: acdd-v2-handoff
description: Complete the repository-handoff ACDD gate.
---

# handoff/v1

## Load

Read the terminal review result, profile, and task adapter. Load only the
current check section, then append its `promptAppend` fragment if present.

## repository-handoff

Run the repository-specific closure command. It must report completed required
actions, changed derived artifacts, and blockers. Do not finalize with blockers
or stale review inputs. Optional durable review reports may be filed under
`audit/reviews/` — storage only, not a separate ACDD gate.

## process-report

Record ACDD-synthesized process metadata (`acdd/process-report/1`) with
`acdd record --gate handoff/v1 --check process-report`. The core writes the
JSON from current receipts and evidence; do not hand-author the report body.

## Evidence

Record both check artifacts, then finalize only after the entire document
validates.
