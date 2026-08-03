# ACDD router

| When | Load |
| --- | --- |
| Create or prove design | [design gate skill](skills/design/SKILL.md) |
| Decompose a planning set | [decompose gate skill](skills/decompose/SKILL.md) |
| Freeze executable task contract | [contract gate skill](skills/contract/SKILL.md) |
| Run integrated verification | [build gate skill](skills/build/SKILL.md) |
| Perform independent code review | [review gate skill](skills/review/SKILL.md) |
| Close repository handoff | [handoff gate skill](skills/handoff/SKILL.md) |
| Diagnose a defect or accepted finding | [Diagnose](skills/diagnose/SKILL.md), then return to its gate |

Load one gate skill only. Build additionally loads [TDD](skills/tdd/SKILL.md).
Inside a gate skill, load only the current check section. Resolve `promptAppend`
from the owner adapter after the base section. It may add repository context; it
must not replace gate ownership, required checks, evidence kind, terminal policy,
or the eleven invariants.

Run `uv run acdd validate <document> <profile>` before and after a terminal
gate. Use `record`, `review`, `contract-subtask`, and `finalize` only through
the owner adapter.
