# ACDD v2

ACDD v2 is a small Markdown workflow for proving a repository change. It keeps
one task document, one profile, physical evidence artifacts, and a validator.
It is not a scheduler, review runtime, or agent orchestrator.

## 5 gates: enforced order

1. **`design/v1` — task owner**: state intent, architecture boundary, and a
   bounded plan before implementation.
2. **`contract/v1` — task owner**: prove the decomposition, impact matrix, and
   pre-change executable regression contract.
3. **`build/v1` — implementation owner**: run one integrated
   `runtime-and-integration` proof on the settled tree.
4. **`review/v1` — review owner**: independently examine parity, security, and
   the completed review scope.
5. **`handoff/v1` — task owner**: complete the repository-specific closure only
   after earlier gates are terminal.

A gate may finalize or validate as terminal only when every earlier profile
gate is already `pass` or `inapplicable`.

## 8 checks (task profile): what every gate proves

| Gate | Required checks |
| --- | --- |
| `design/v1` | `design-basis`, `plan-shape` |
| `contract/v1` | `decomposition`, `matrix`, `executable-proof` |
| `build/v1` | `runtime-and-integration` |
| `review/v1` | `independent-review` |
| `handoff/v1` | `repository-handoff` |

`review/v1` is one review check whose profile declares the `reviewDimensions`
it must cover (e.g. `[parity, security]`). Parallel reviewer sessions append
records to one JSONL transcript; the terminal record must be
`review_terminal` with `verdict: pass`, matching author/reviewer session UUIDs,
and `performedChecks` listing every dimension. Repos extend the dimension list
without changing the core. Other profiles define their own checks.

The build check is deliberately composite: splitting it into `runtime` and
`integration` would make nine checks, not eight.

## 11 invariants: what the validator refuses

1. **Shape** — rows are exactly the profile gates, ordered, with coherent pending values; a declared `planning_profile` must match the profile; terminal rows require every earlier gate terminal. A sixth `note` cell is allowed only on `partial`/`blocked` rows.
2. **Evidence is real** — artifacts are local, checksummed, unique, single-record, and pass their declared outcome; basis evidence covers its scope; review terminals carry `verdict: pass`.
3. **Receipt binds evidence** — receipt, bundle, and check fingerprints agree.
4. **Receipt binds state** — fingerprint covers the gate's profile definition, adapter bindings, plan/subtasks digest, and declared `invalidatesOn` input bytes; unrelated input-type edits outside that scope do not stale a receipt, but any plan change does.
5. **Authority** — the bundle/check issuer is the gate owner, and the adapter binds exactly that gate's checks.
6. **Sub-task bounded** — IDs, paths, acceptance, dependencies, and write/read conflicts are valid and explicit; conflicting subtasks must be serialized by a (possibly transitive) dependency.
7. **Review independent** — review evidence has a pass verdict and distinct valid author/reviewer UUIDs that match the transcript terminal.
8. **Inapplicable reasoned** — a gate-level inapplicable receipt uses an allowed reason code and includes no check evidence.
9. **Execution honest** — outcome matches declared `commandOutcome`; timeouts, execution errors, and reserved exits `124`/`127` never pass; basis evidence is held to the same honesty.
10. **Discovery authentic** — exactly one adapter per role per workspace, confined below the workspace root, and its gates all belong to the active profile.
11. **Review complete** — review transcript declares a non-empty scope and `performedChecks` covering the profile's `reviewDimensions`.

## Prompts and agent routing

[AGENTS.md](AGENTS.md) routes one active gate to one skill under `skills/`.
Each gate skill is split into the gate’s check sections; load only the section
for the current check. Its text is the canonical base prompt.

An adapter may add repository context with `promptAppend` on a check binding:

```yaml
gates:
  build/v1:
    checks:
      runtime-and-integration:
        cwd: .
        argv: [uv, run, pytest, -q]
        timeoutSeconds: 900
        promptAppend: prompts/build-runtime.md
```

The fragment path is relative to the adapter (conventionally
`.acdd2/prompts/<gate>-<check>.md`), must stay below its directory, and its
SHA-256 enters the gate fingerprint. `cwd` must resolve below the workspace
root, and `timeoutSeconds` (default 300) bounds the command; a timeout never
passes. The fragment appends context after the base skill section; it cannot
replace ownership, check requirements, evidence kind, terminal policy, or an
invariant.

Evidence artifacts land in `<adapter dir>/artifacts/` (`.acdd2/artifacts/` in a
consuming repository). Successful evidence artifacts are immutable, gitignored
runtime artifacts, required across sessions while the task is active, and
prunable after the handoff gate closes — the committed document keeps every
evidence block with its SHA-256 as provenance. A failed `record` may leave an
orphan JSONL; retrying the same `--id` overwrites it when that id is not yet in
the document. `record` also rejects a second success for the same gate/check at
the current fingerprint.

## Commands

Adapters are discovered automatically: every `*.yaml` file directly inside a
`**/.acdd2/` directory below the workspace root with `apiVersion: acdd/adapter/v1`
is loaded and indexed by role (duplicates rejected). Symlinked adapter files
are ignored. `--adapter role=path` overrides a discovered entry and must also
resolve below the workspace root.

```bash
uv run acdd validate task.md profiles/task/v1.yaml --adapter task=task.yaml

uv run acdd fingerprint task.md profiles/task/v1.yaml --adapter implementation=impl.yaml \
  --gate build/v1

uv run acdd record task.md profiles/task/v1.yaml --adapter implementation=impl.yaml \
  --gate build/v1 --check runtime-and-integration --id build.runtime

uv run acdd finalize task.md profiles/task/v1.yaml --adapter implementation=impl.yaml \
  --gate build/v1 --id build.bundle
```

`acdd review` registers one adapter-bound review JSONL transcript relative to
`--workspace-root`. The core never launches a reviewer: for `review` checks the
bound `argv` is an agent launcher template (placeholders `{document}`,
`{evidenceId}`, `{reviewerSessionUuid}`, `{prompt}`). Run it for each parallel
session; append all records to one transcript file. The last record must be a
`review_terminal` whose UUIDs match the CLI flags and whose `performedChecks`
covers every profile dimension. `acdd review` does not substitute launcher
placeholders. See [DESIGN.md](DESIGN.md) for the data contract.
