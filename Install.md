# Install and Configure ACDD Adapters

Use this guide only when installing the plugin or creating, adapting, validating,
or running repository-specific ACDD adapters. Do not put product paths, commands, issue state, or tool assumptions
in core profiles or contracts.

## Methodology contract

- Treat ACDD as **Architecture Contract-Driven Development**: establish one
  bounded architecture contract, verify it independently, implement only that
  contract, and close through current evidence.
- Complete task stages in order:
  - **G0:** `matrix/v1` + `architecture/v1` — coverage, owner/caller/authority
    contract, impact, independent read-only architecture PASS.
  - **G1:** `red/v1` + `runtime/v1` + `parity/v1` — expected failure, real
    production path, applicable parity.
  - **G2:** `security/v1` — final authorization, isolation, payload, lifecycle,
    and external-effect contour.
  - **G3:** `release/v1` + `review/v1` + `handoff/v1` — owner release gate,
    independent closure review, current receipts, empty blockers.
- Never execute implementation before G0 passes for the current semantic
  fingerprint.
- Never rerun an unchanged architecture `FAIL`. Run `scripts/check_architecture_admission.py` before each launch. Change the bound contract or
  evidence, recompute the fingerprint, and launch a fresh verification.
- Never manufacture, infer, or backfill a passing receipt. Unavailable evidence
  is `blocked`.
- Never let a review finding expand scope without explicit task authorization
  and a new contract fingerprint.

## Choose the workflow

| Trigger | Profile | Required adapters |
|---|---|---|
| Deliver one active bound task | [`profiles/task/v1.yaml`](profiles/task/v1.yaml) | `task`, `implementation`; optional `audit` |
| Create or improve one bounded planning set | [`profiles/plan/v1.yaml`](profiles/plan/v1.yaml) | `plan`; optional `audit` |
| Validate a self-contained milestone plan | [`contracts/plan/simple/v1.yaml`](contracts/plan/simple/v1.yaml) | `plan` plus `check_simple_plan.py` |

Planning creates inactive candidates. Do not activate or implement a task inside
`acdd/plan/v1`; hand it to a later `acdd/task/v1` session.

## Repository integration procedure

When asked to add ACDD to a workspace or repository:

1. Read the workspace and target repository `AGENTS.md` files.
2. Confirm the shared plugin path and real Git roots.
3. Create `.acdd/` in each owner repository, not in the workspace root by
   default.
4. Copy the nearest adapter from [`examples/`](examples/README.md).
5. Replace every example path, command, model, tool, authority, mapping, and
   constraint with a live owner value.
6. Add a short route to the nearest owner `AGENTS.md`; link here for adapter
   details instead of duplicating this file.
7. Validate the composed profile with explicit `--workspace-root`,
   `--document`, and `--adapter role=path` arguments.
8. Run the target repository's own tests and instruction/link checks.
9. Run this package's tests and `git diff --check` when changing plugin core or
   examples.

Recommended owner layout:

```text
workspace/
├── plugins/acdd-workflow/
├── planner/.acdd/
│   ├── task-adapter.yaml
│   └── plan-adapter.yaml
├── product/.acdd/
│   └── implementation-adapter.yaml
└── audit/.acdd/
    └── audit-adapter.yaml
```

## Adapter roles

### `task`

Use in the repository that owns task state and execution bookkeeping.

Must provide exactly the role capabilities declared by
[`contracts/task/v1.yaml`](contracts/task/v1.yaml): task reading/writing and
impact classification. Own:

- bound task and current-execution authority;
- required impact axes and variants;
- task lifecycle and receipt writes;
- G0 architecture coordinator launcher and discovery bindings;
- final handoff.

Do not grant source mutation or terminal code-review authority through this
role.

Start from
[`examples/planner/.acdd/task-adapter.yaml`](examples/planner/.acdd/task-adapter.yaml).

### `implementation`

Use in the repository that owns runtime source, tests, configuration, generated
artifacts, and release commands.

Must provide source/docs/structural discovery, gate execution, independent
review, and review execution. Own:

- source, caller, backend, configuration, test, and generated authority;
- exact RED, runtime, parity, security, and release procedures;
- terminal `review/v1` launcher;
- preservation of unrelated worktree changes.

It contributes architecture evidence but does not execute task
`architecture/v1`; routing assigns that to the `task` adapter.

Start from
[`examples/codebase/.acdd/implementation-adapter.yaml`](examples/codebase/.acdd/implementation-adapter.yaml).

### `plan`

Use in the repository that owns the primary plan and declared planning set.

Must provide plan read/write, evidence and architecture mapping, impact,
plan/roadmap/milestone/decomposition validation, publication, and independent
review. Own:

- primary-plan and planning-set authority;
- hierarchy projection and backlinks;
- cross-phase span and impact propagation;
- architecture and terminal planning review launchers;
- publication, drift/index refresh, and planning handoff.

Start from
[`examples/planner/.acdd/plan-adapter.yaml`](examples/planner/.acdd/plan-adapter.yaml)
or [`examples/simple-plan/.acdd/`](examples/simple-plan/.acdd/).

### `audit`

Use only for publication of an explicitly selected terminal report. It provides
`audit_publish`, does not own a gate, does not replace inline receipts, and does
not become a general review role.

Start from
[`examples/audit/.acdd/audit-adapter.yaml`](examples/audit/.acdd/audit-adapter.yaml).

## Create or edit an adapter

Every adapter follows [`contracts/adapter/v1.yaml`](contracts/adapter/v1.yaml).
Use this minimum shape:

```yaml
apiVersion: acdd/adapter/v1
kind: adapter
id: owner-purpose/v1
role: task | implementation | plan | audit
provides: [exact, role, capabilities]
procedure:
  - Ordered owner-specific instruction.
authority:
  source: owner/path/**
  commands: owner commands only
  impact:
    domains: [owner-required-axis]
inputAuthorities:
  source: [owner/path/**]
constraints:
  - Fail-closed owner invariant.
```

### Required fields

- `id`: stable owner-specific ID; version it when compatibility changes.
- `role`: one supported role only.
- `provides`: declare only capabilities this owner implements. Do not add a
  capability to satisfy validation unless its procedure and authority exist.
- `procedure`: inline steps or path/list of paths resolved relative to this
  adapter file.
- `authority`: concrete owner paths, commands, evidence, impact axes, and
  mappings. Do not use aspirational paths.
- `constraints`: fail-closed invariants and forbidden behavior.

### Optional fields

- `availability`: prerequisites that can block execution.
- `gateProcedures`: gate-specific operation and launcher details.
- `resources`: adapter-relative contracts/templates.
- `scripts`: adapter-relative executables.
- `externalMappings`: canonical ACDD → Linear/Jira/other projection.
- `inputAuthorities`: glob allowlists for typed document inputs.
- `writePolicy`: ordinary allow/deny and narrow protected-write exceptions.
- `receipts`: owner-specific storage and closure rules.
- `skillExtensions`: local procedures that strengthen profile guidance.

Resolve every procedure/resource/script path from the adapter directory,
canonicalize it, ensure it exists, and ensure it remains under the allowed
workspace root. Never reinterpret an adapter-relative path from the session CWD.
A grep/glob miss is not proof that the declared resource does not exist.

## Capabilities and routing

Load capabilities from the selected profile's capability contract; do not copy
lists from memory:

- task: [`contracts/task/v1.yaml`](contracts/task/v1.yaml)
- plan: [`contracts/plan/v1.yaml`](contracts/plan/v1.yaml)

Load executor ownership from routing:

- task: [`routing/task/v1.yaml`](routing/task/v1.yaml)
- plan: [`routing/plan/v1.yaml`](routing/plan/v1.yaml)

For each gate:

1. collect capabilities and authority from every routed adapter;
2. execute only through `executorAdapter`;
3. load that adapter's gate procedure;
4. issue evidence only through the executor owner;
5. update only the bound document/owner state permitted by adapter authority.

Do not create a detached reviewer adapter. Task closure review belongs to the
`implementation` adapter; plan review belongs to the `plan` adapter. `audit` is
publication only.

## Gate launchers and subagents

An independent gate procedure must bind a real launcher:

```yaml
scripts:
  architectureArtifacts: scripts/architecture_artifacts.py
gateProcedures:
  architecture/v1:
    operation: architecture-verify
    runtime: pi
    launchers:
      inspector:
        kind: command
        target: pi
        arguments: [--print, --session-id, "{sessionUuid}"]
        promptTransport: final-argument
      coordinator:
        kind: command
        target: pi
        arguments: [--print, --session-id, "{sessionUuid}", --no-tools]
        promptTransport: final-argument
    toolEnvelope:
      admit: [read, grep, find, ls]
      deny: [bash, edit, write]
```

`architectureArtifacts` is an adapter-owned executable backend with
`context`, `prepare`, `launch`, `terminal`, and `validate` operations. The plugin supplies
typed lifecycle events; the adapter chooses storage paths, retention, redaction,
serialization, and Git-ignore policy.

Rules:

- Treat `runtime` as provenance only. Never search for or invoke it as a tool.
- Invoke `launcher.target` according to `launcher.kind`:
  - `command`: use the host command executor;
  - `tool`: call the exact registered tool.
- Substitute only declared placeholders.
- Deliver prompts via `promptTransport`.
- Verify the target exists before launch.
- Admit only tools actually available inside the launched session.
- Deny writes for architecture inspectors and terminal reviewers unless a
  future profile explicitly authorizes them.
- Use `launchers.inspector` for the four concurrent partition processes and
  `launchers.coordinator` only after all four outputs validate. The coordinator
  must be tool-free and receives only the frozen task authority plus validated
  partition outputs.
- A procedure may declare the legacy singular `launcher` or split `launchers`,
  never both. Paths resolve from the owning adapter.
- A task adapter that permits G1 amendments must declare both artifact roots.
  Keep exactly one YAML receipt and one paired JSONL transcript per amendment.
  The transcript is secret-redacted and capped at 32 KiB per stream and 2 MiB
  total; the receipt stores its path and SHA-256. Never serialize raw launcher
  output into Markdown or YAML.

For task `architecture/v1`, bind:

- a concrete four-partition verification contract;
- exact-text, structural, and dependency discovery methods to real tools;
- one authoritative coordinator session;
- read-only, non-writing inspector envelopes;
- review root and command CWD;
- bounded scope and model/runtime configuration.

Follow
[`contracts/architecture-verification/v1.yaml`](contracts/architecture-verification/v1.yaml):
inspectors share the input fingerprint, may not write, issue receipts, or return
a verdict; one coordinator reconciles every partition and returns the verdict.
Inspectors have read-only access to the task and implementation code. Code is a
feasibility/impact baseline, not an implementation-completion gate. A `FAIL`
must be a typed task-candidate defect with task evidence, code evidence, and a
required task-authority change. Legacy or unimplemented code alone is not a
finding. Runtime/transport/schema failures are `BLOCKED` and preserve completed
partition results plus bounded redacted raw response content, including plain-text
`FAIL` output.

For terminal `review/v1`, launch only after source, tests, configuration, and
release evidence settle. Classify findings in the primary session, apply only
accepted authorized fixes, invalidate affected receipts, rerun affected gates,
and review the new fingerprint.

## Inputs, evidence, fingerprints, and receipts

The bound Markdown document must keep all workflow state inline.

### Inputs

Under `## ACDD inputs`, declare workspace-relative paths with
`apiVersion: acdd/inputs/v1`. Supported types are `source`, `test`,
`configuration`, `generated`, `dependency`, `environment`, and
`accepted-review-findings`.

Every path must match an `inputAuthorities` pattern in at least one supplied
adapter. Keep patterns narrow enough to identify the real owner; do not default
to `**` in production adapters without a documented reason.

### Evidence

Under `## ACDD gate evidence`, record bounded discriminated evidence with
`apiVersion: acdd/gate-evidence/v1`. Use the appropriate type: `basis`,
`command`, `review`, `handoff`, or `rationale`.

Command evidence includes exact command, UTC time, exit code, bounded redacted
output, result, and current fingerprint. RED evidence additionally freezes the
proof-definition fingerprint and, when Git identity is unavailable, hashes only
its declared proof inputs.

Review evidence includes adapter, isolated session UUIDs, reviewer/coordinator,
terminal verdict, authority sources, production and alternate paths,
contradictions, impact axes, proof mappings, and bounded findings. Never paste
raw subagent transcripts. Architecture runner evidence may additionally include
normalized bounded usage per launcher and aggregate usage; the usage transport
is adapter-specific, not inherently Pi-specific.

### Fingerprints and invalidation

Use the gate fingerprint produced by strict validation. Never invent a checksum.
A nonpending receipt requires `sha256:<64 lowercase hex>` and a UTC timestamp.

Read invalidation policy from:

- [`contracts/receipt/task/v1.yaml`](contracts/receipt/task/v1.yaml)
- [`contracts/receipt/plan/v1.yaml`](contracts/receipt/plan/v1.yaml)

When a gate input changes, return that receipt and every dependent successor to
`pending`. Preserve stale evidence for auditability but do not treat it as
current. Record authorized semantic contract changes through the inline
contract-change chain described in
[`skills/acdd-task/references/receipts.md`](skills/acdd-task/references/receipts.md).

## Write policy

Core protected paths are `.agents/**`, nested `.agents/**`, root `AGENTS.md`,
and nested `AGENTS.md`.

- Do not write a protected path during an ACDD cycle unless the user explicitly
  requested that instruction change.
- Add `writePolicy.protectedAllow` only for the narrow requested subtree and set
  `authorization: explicit-user-request`.
- Never use a repository-wide protected allow.
- Apply `deny` before `allow` and protected authorization.
- Treat all pre-existing worktree changes as intentional; never reset, restore,
  or absorb them without authorization.

## External mappings

Preserve canonical hierarchy semantics. Use `externalMappings` to project,
never redefine:

- Linear: roadmap → Initiative, phase → Project, milestone → Project Milestone,
  task → Issue;
- Jira: roadmap → Initiative, phase → Epic, milestone → Version/Release, task →
  Story/Task;
- filesystem Planner: roadmap file → phase file → milestone file → task file.

Plans remain separately bound artifacts and are not an extra hierarchy level.
See [`examples/linear/.acdd/`](examples/linear/.acdd/) and
[`examples/jira/.acdd/`](examples/jira/.acdd/).

## Owner `AGENTS.md` route

Add only a concise route at the owner boundary. Recommended text:

```md
## ACDD

- Task delivery → `../plugins/acdd-workflow/profiles/task/v1.yaml` with this
  repository's `.acdd/<role>-adapter.yaml`.
- Planning → `../plugins/acdd-workflow/profiles/plan/v1.yaml` with
  `.acdd/plan-adapter.yaml`.
- Complete G0 before implementation, G1 runtime/parity, G2 final security, and
  G3 release/review/handoff. Keep ordinary evidence and receipts inline; keep
  G1 amendment attempts in the adapter-owned receipt and redacted transcript.
- Adapter creation, validation, and subagent rules:
  `../plugins/acdd-workflow/Install.md`.
```

Adjust relative paths and include only the workflows implemented by that owner.

## Validation commands

From this plugin repository:

```bash
python3 -m pytest tests -q
python3 scripts/validate_acdd.py \
  --profile profiles/task/v1.yaml \
  --workspace-root . \
  --document examples/task/TASK.md \
  --adapter task=examples/planner/.acdd/task-adapter.yaml \
  --adapter implementation=examples/codebase/.acdd/implementation-adapter.yaml
python3 scripts/validate_acdd.py \
  --profile profiles/plan/v1.yaml \
  --workspace-root . \
  --document examples/simple-plan/PLAN.md \
  --adapter plan=examples/simple-plan/.acdd/plan-adapter.yaml
python3 scripts/check_simple_plan.py \
  --plan examples/simple-plan/PLAN.md --strict
python3 scripts/check_markdown_links.py --root .
git diff --check
```

When validating a real workspace, replace only workspace root, document, and
adapter paths. Add `--settings <json>` when skill uniqueness must also be
validated.

## Core change rules

- Keep supported profile IDs at `acdd/task/v1` and `acdd/plan/v1` unless the
  user explicitly requests a versioned contract change.
- Keep profiles/contracts host-neutral.
- Put owner policy in owner adapters and reusable execution procedure in skills.
- Update examples and tests with every adapter-contract, routing, receipt,
  launcher, or document-shape change.
- Keep the runnable self-contained plan only under
  [`examples/simple-plan/`](examples/simple-plan/); this package has no active
  repository-owned plan.
- Keep the human methodology and subsystem overview in [`README.md`](README.md).
- Keep adapter installation and execution details in this document.
