---
name: acdd-review
description: Run the independent Code review gate (review/v1).
---

# review/v1 — Code review

## Load

Read the profile, review adapter, and the settled review input. For
`acdd/task/v1`, that is the Build tree and Contract. For `acdd/plan/v1`, it is
the planning set after Decompose. Load only this check section, then append the
bound `promptAppend` fragment.

This gate is **Code review**, not `contract-verify`.

## independent-review

The review adapter binding is a **launch template** for the external review
host. Expand its placeholders, run the host, and preserve every raw response in
JSONL. ACDD does not select models or remediate findings; when the host is done,
register the transcript with `acdd review`.

Give independent reviewers the settled input and the profile's dimensions. They
may work in parallel. One collector writes each completed response before
interpreting it. Give the settled input, required dimensions, and all raw
responses to one confirmation reviewer for the final pass terminal.

## Transcript

Every preterminal line is exactly:

    {"type":"review_raw","reviewerSessionUuid":"UUID","raw":"verbatim response"}

The confirmation reviewer returns the final `review_terminal` declaration. A
pass terminal has `verdict: pass`, distinct author/reviewer UUIDs, non-empty
`scope`, `performedChecks` covering every profile dimension, and
`reviewedSessionUuids` listing every raw session exactly once.

## Findings and recheck

If confirmation finds an issue, keep the transcript and mark Review
`partial`/`blocked`. Remediation belongs to the review host / diagnose loop —
not to ACDD core. After fixes that change Build inputs, return through Build,
then recheck with a new transcript id.

## Evidence

Register the finished transcript with `acdd review`. Finalize only when current.
