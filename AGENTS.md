# ACDD router

Planned core work (sidecars, subtask `status`/`verified`): [ROADMAP.md](ROADMAP.md).

| When | Load |
| --- | --- |
| Create or prove design | [design gate skill](skills/design/SKILL.md) |
| Decompose a planning set | [decompose gate skill](skills/decompose/SKILL.md) |
| Freeze executable task contract | [contract gate skill](skills/contract/SKILL.md) |
| Run integrated verification | [build gate skill](skills/build/SKILL.md) |
| Perform independent Code review | [review gate skill](skills/review/SKILL.md) |
| Close repository handoff | [handoff gate skill](skills/handoff/SKILL.md) |
| Diagnose a defect or accepted finding | [Diagnose](skills/diagnose/SKILL.md), then return to its gate |

Load one gate skill only. Build additionally loads [TDD](skills/tdd/SKILL.md).
Inside a gate skill, load only the current check section. Resolve `promptAppend`
from the owner adapter after the base section. It may add repository context; it
must not replace gate ownership, required checks, evidence kind, terminal policy,
or the eleven invariants.

**Do not edit adapter `promptAppend` files** (for example
`.acdd/prompts/contract-verify-task.md`, design/review prompts, or any path
named by `promptAppend` in an adapter). Read them; do not rewrite them to
“fix” a gate, unblock verify, or harden policy mid-task. Those files are
hashed into gate fingerprints (`promptDigest`). Changing them after a terminal
receipt stales the gate. Prompt-policy changes require an explicit user
decision outside the delivery loop — never a silent agent patch.

**Verify ↔ edit order:** until `contract/v1` finalize — (1) edit the same
subtask `S` after verify findings, (2) re-verify the package, (3) repeat until
PASS, (4) then finalize. Failed verify is not a freeze. Propose splits; do not
invent `*-r2` clones. Do not change `promptAppend` to teach this (stales
hashes). See Contract skill.

**Contract freeze:** while `contract/v1` is `pass`, `acdd validate` prints
**ACDD FREEZE**. Do not edit frozen Plan parts, the Task execution contract
section, or `promptAppend` files. Do not `acdd reopen`. New scope only via
`acdd contract-subtask` then re-run `contract-verify` for a matching
`authorityDigest`.

Run `uv run acdd validate <document> <profile>` before and after a terminal
gate. Use `record`, `review`, `contract-subtask`, and `finalize` only through
the owner adapter.

`contract-verify` checks contract substance (including `chain-coverage` =
explicit matrix paths that resolve in the live tree). Give the verifier read
access to the task document and cited code roots. `review/v1` checks the
settled implementation tree in its owning git repo. Do not merge those into one
Pi dirty-tree workspace across separate git roots.
