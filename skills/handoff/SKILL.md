---
name: acdd-v2-handoff
description: Complete the repository-handoff ACDD gate.
---

# handoff/v1

## Load

Read the terminal review result, profile, and task adapter. Load
`repository-handoff`, then append its `promptAppend` fragment if present.

## repository-handoff

Run the repository-specific closure command. It must report completed required
actions, changed derived artifacts, and blockers. Do not finalize with blockers
or stale review inputs.

## Evidence

Record the command artifact and issue the final owner receipt only after the
entire document validates.
