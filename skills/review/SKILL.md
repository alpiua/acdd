---
name: acdd-v2-review
description: Run the independent review/v1 ACDD gate.
---

# review/v1

## Load

Read the settled tree, profile, and review adapter. Load only the current check
section, then append its `promptAppend` fragment if present.

## independent-review

Read the profile's `reviewDimensions` for this gate. Run the bound launcher
template (`argv` with `{document}`, `{evidenceId}`, `{reviewerSessionUuid}`,
`{prompt}` placeholders) for each independent read-only session. Append every
session's records to one JSONL transcript. Parallel reviewers may run in
parallel; the transcript's final record must be a terminal `review_terminal`
with a non-empty `scope`, a `performedChecks` list that includes every declared
dimension, `verdict: pass`, and distinct valid `authorSessionUuid` /
`reviewerSessionUuid` that match the `acdd review` CLI flags. Zero findings may
pass when the reviewed scope and checks are complete.

## Evidence

Register actual artifacts; do not fabricate a transcript. Finalize only after
the check artifact is current.
