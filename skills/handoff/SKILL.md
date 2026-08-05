---
name: acdd-handoff
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

Finalizing this gate synthesizes `acdd/process-report/1` onto the handoff
bundle (`processReportRef`). Do not record process-report as a separate check.

## Evidence

Record the `repository-handoff` artifact, then finalize only after the entire
document validates.
