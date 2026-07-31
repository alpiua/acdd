# ACDD v2 design

ACDD v2 is a small, self-contained Markdown evidence validator. It has one
document, one profile, repository adapters, physical artifacts, and one
validator. It is not a scheduler, Pi plugin, review runtime, or state ledger.

## Task profile: 5 gates, 8 checks

| Gate | Owner | Checks |
| --- | --- | --- |
| `design/v1` | `task` | `design-basis`, `plan-shape` |
| `contract/v1` | `task` | `decomposition`, `matrix`, `executable-proof` |
| `build/v1` | `implementation` | `runtime-and-integration` |
| `review/v1` | `review` | `independent-review` |
| `handoff/v1` | `task` | `repository-handoff` |

Gates are sequential: a receipt may be terminal only when every earlier profile
gate is already `pass` or `inapplicable`. `finalize` enforces the same rule.

The number of checks per gate is profile-defined (the planning profile has its
own shape). `review/v1` declares its `reviewDimensions` in the profile (e.g.
`[parity, security]`); the adapter supplies the launcher template and the
transcript must declare `performedChecks` covering them. Repos extend the
dimension list without changing the core.

`runtime-and-integration` is deliberately one composite check. Splitting it into
`runtime` and `integration` would add one check (nine total for the task
profile) and is outside this contract.

The task/contract evidence must capture the code-review essentials: reachable
scenario, canonical owner, post-fix invariant, forbidden effects, affected
dimensions, and a focused regression that fails before the implementation.
The review artifact records its scope, performed checks, terminal verdict, and
independent sessions. Core does not launch any reviewer.

## Profile and adapters

The profile is the source of truth for gate order, owner, check IDs, evidence
kind, expected command outcome, input types, and allowed terminal statuses.
Every core check has one of `command`, `basis`, or `review` evidence kinds.
`expected-failure` is a command outcome, never a receipt status.

An adapter is only `role → gate → check → {cwd, argv, timeoutSeconds?,
promptAppend?}`. Its role must own the gate. `argv` is an array executed
without a shell; `cwd` must resolve below the workspace root; `timeoutSeconds`
(default 300) bounds execution and a timeout never passes. Every core check
must have exactly one binding; missing or extra bindings invalidate a terminal
gate. Adapter, artifact, and adapter-file paths must remain below the
workspace root. `expected-failure` requires a genuine non-zero exit: a timeout,
an execution error, or reserved exits `124`/`127` never count as the expected
failure — even when the process returns those codes without the timeout or
execution-error flags.

Adapters are discovered, not declared: `acdd` loads every `*.yaml` file directly
inside a `**/.acdd2/` directory with `apiVersion: acdd/adapter/v1` below the
workspace root and indexes them by role. Symlinked adapter files are ignored. A
consuming repository keeps its adapters in its own `.acdd2/` directory;
duplicate roles are rejected. `--adapter role=path` overrides a discovered
entry (same workspace confinement).

For `review` evidence the core never executes `argv`: it is the unconditional
launcher template for the agent, with placeholders `{document}`,
`{evidenceId}`, `{reviewerSessionUuid}`, and `{prompt}` (the base skill section
plus the bound `promptAppend`). The agent runs it once per launch — repeated
with different payloads for parallel reviewer sessions — and the produced
transcript is the proof. Every other evidence kind is executed by the core.

## Prompts and skills

`AGENTS.md` routes an active gate to one `skills/<gate>/SKILL.md` file. Each
skill contains one section per core check; that section is the base prompt for
the current stage. The core validator does not execute prompts.

An adapter check may set `promptAppend: prompts/<gate>-<check>.md`. The
fragment resolves below the adapter directory (conventionally `.acdd2/prompts/`),
is appended after the selected base section, and its SHA-256 enters the adapter
portion of the gate fingerprint. It adds repository context only: it cannot
replace a core skill, owner, required check, evidence kind, terminal status, or
invariant.

## Evidence and receipts

Artifacts live in `<adapter dir>/artifacts/` — for a consuming repository that
is `.acdd2/artifacts/`. They are immutable once committed as evidence,
required across sessions for as long as the task document is active (validation
reads and checksums them), repositories gitignore them as runtime artifacts,
and they may be pruned once the document's handoff gate is terminal: the
committed document keeps every evidence block with its SHA-256 as provenance,
and a pruned artifact simply means the closed document no longer re-validates.
A failed `record` may leave a JSONL diagnostic on disk; retrying the same
evidence id overwrites that orphan when the id is not yet in the document.

`acdd record` executes one non-review check, writes one immutable single-record
JSONL artifact, and appends its evidence block. It rejects a second successful
evidence block for the same gate/check at the current fingerprint. A command
passes only for exit code zero; `expected-failure` passes only for a genuine
non-zero, non-reserved result. Basis evidence carries the same executed record
plus classified references whose scope must equal the gate's declared input
scope.

`acdd review` registers an existing review JSONL transcript produced by
running the bound launcher template. The terminal record must be
`type: review_terminal` with `verdict: pass`, `performedChecks` covering the
profile dimensions, and `authorSessionUuid` / `reviewerSessionUuid` that match
the CLI flags and are distinct valid UUIDs.

`acdd finalize` is owner-only and requires every earlier gate to be terminal.
For `pass` it creates one bundle referencing exactly one current evidence block
for every required check, then writes the gate receipt. For `inapplicable` it
requires an allowed gate-level reason code and an empty `checkEvidence` list —
inapplicability is a gate decision, not a partial check set.

## Eleven invariants

1. **Shape** — exact gate rows in profile order; known statuses; non-terminal rows are fully pending and may carry a sixth `note` cell only when `partial`/`blocked`; a declared `planning_profile` matches the profile; a terminal row requires every earlier gate to already be terminal.
2. **Evidence is real** — artifact is workspace-confined, present, checksummed, unique, holds exactly one terminal record (review transcripts end with one), and is a valid evidence kind; basis scope equals the gate's declared input scope and is fully classified; review terminals carry `verdict: pass`.
3. **Receipt binds evidence** — receipt, bundle, and check fingerprints match.
4. **Receipt binds state** — fingerprint covers the gate's profile definition, adapter bindings, canonical plan/subtasks digest, and declared `invalidatesOn` input bytes; edits to inputs outside that type set do not stale a receipt, but any plan/subtask change does.
5. **Authority** — the bundle/check issuer is the gate owner, the adapter binds exactly that gate's checks, and IDs agree.
6. **Sub-task bounded** — IDs, paths, acceptance, dependencies, and write/read conflicts are valid and explicit; conflicting subtasks must be serialized by a (possibly transitive) dependency.
7. **Review independent** — review evidence has a pass verdict and distinct valid author/reviewer UUIDs that match the transcript terminal.
8. **Inapplicable reasoned** — a gate-level inapplicable receipt uses an allowed reason code and carries no check evidence.
9. **Execution honest** — command outcome matches the profile's declared `commandOutcome`; timeouts, execution errors, and reserved exits `124`/`127` never pass; basis evidence is held to the same honesty.
10. **Discovery authentic** — exactly one adapter per role per workspace, confined below the workspace root, and its declared gates all belong to the active profile.
11. **Review complete** — review transcript declares a non-empty scope and `performedChecks` that covers the profile's `reviewDimensions`.

These eleven groups absorb the former row/order/status, artifact, checksum,
duplicate, freshness, owner, scope, review, and inapplicability rules without
separate legacy validators.

## Boundaries and Phase 3

The core accepts no `gateExtensions`; it rejects unknown adapter fields rather
than silently ignoring them. Repository-specific work belongs in the bound
commands. Declarative namespaced adapter checks with parents and check-level
applicability are optional Phase 3 work after this core has stable use.
