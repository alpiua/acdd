# ACDD v2 router

| When | Load |
| --- | --- |
| Create or prove design | [design gate skill](skills/design/SKILL.md) |
| Freeze executable task contract | [contract gate skill](skills/contract/SKILL.md) |
| Run integrated verification | [build gate skill](skills/build/SKILL.md) |
| Perform independent code review | [review gate skill](skills/review/SKILL.md) |
| Close repository handoff | [handoff gate skill](skills/handoff/SKILL.md) |

Load one gate skill only. Inside it, load the section for the current check.
Resolve `promptAppend` from the owner adapter after the base section. It may add
repository context; it must not replace gate ownership, required checks,
evidence kind, terminal policy, or the eleven invariants.

Run `uv run acdd validate <document> <profile>` before and after a terminal
gate. Use `record`, `review`, and `finalize` only through the owner adapter.
