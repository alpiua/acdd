---
name: acdd-v2
description: Validate a lean ACDD task document and record owner-bound physical evidence.
---

# acdd-v2

Use this for task documents that need the ACDD v2 five-gate contract. Start at
`AGENTS.md`, load one gate skill, then load only its current check section.

1. Write `Plan`, `Inputs`, one pending receipt row per profile gate.
2. Run `acdd validate`.
3. Use `acdd record --gate --check --id` for each bound command/basis check.
4. Run independent review sessions with the bound launcher; append every
   session to one JSONL transcript whose terminal is `review_terminal` with
   `verdict: pass`, matching author/reviewer UUIDs, and `performedChecks`
   covering all profile `reviewDimensions`; register it once with `acdd review`.
5. Only the gate owner runs `acdd finalize` after every earlier gate is
   terminal; re-run `acdd validate`.

Use an adapter `promptAppend` only to add repository context after the selected
base check prompt. Do not use `--run`, shell commands, manual receipt edits,
synthetic review transcripts, additional statuses, or declarative extra checks.
The core has 5 task gates, 8 checks, and 11 invariants.
