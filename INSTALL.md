# Install and Configure ACDD

This is the technical integration runbook. Read [`README.md`](README.md) first
for the method, stages, gates, and execution model. Use this file to place the
plugin, create owner adapters, configure launchers and evidence, and validate a
real workspace.

## Install the plugin

Keep one plugin checkout beside the repositories that participate in the
workflow:

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

Install the Python dependencies and verify the checkout:

```bash
cd workspace/plugins/acdd-workflow
python3 -m pip install --upgrade PyYAML pytest
python3 -m pytest tests -q
python3 scripts/check_markdown_links.py --root .
```

There is no daemon and no global `acdd` executable. Run the scripts from this
checkout and pass the workspace, document, profile, and adapters explicitly.

## Choose and place adapters

| Workflow | Required owner adapters |
|---|---|
| Task delivery (`acdd/task/v1`) | `task` in the task repository and `implementation` in the source/runtime repository; optional `audit` |
| Planning (`acdd/plan/v1`) | `plan` in the planning repository; optional `audit` |

Place each adapter in its owner's `.acdd/` directory. Do not centralize product
commands, paths, or tool assumptions in the plugin's profiles or contracts.

Copy the nearest working example:

| Owner | Starting point |
|---|---|
| Filesystem task and planning owner | [`examples/planner/.acdd/`](examples/planner/.acdd/) |
| Source, tests, runtime, and release owner | [`examples/codebase/.acdd/`](examples/codebase/.acdd/) |
| Independent architecture and terminal review | [`examples/reviewers/`](examples/reviewers/) |
| Self-contained planning bundle | [`examples/simple-plan/`](examples/simple-plan/) |
| Linear projection | [`examples/linear/.acdd/`](examples/linear/.acdd/) |
| Jira projection | [`examples/jira/.acdd/`](examples/jira/.acdd/) |
| Optional audit publication | [`examples/audit/.acdd/`](examples/audit/.acdd/) |

Replace every example path, command, launcher, model, tool, authority, impact
axis, constraint, and external mapping with a live value owned by that
repository.

## Adapter contract

Every adapter follows [`contracts/adapter/v1.yaml`](contracts/adapter/v1.yaml).
Use the exact role capabilities from [`contracts/task/v1.yaml`](contracts/task/v1.yaml)
or [`contracts/plan/v1.yaml`](contracts/plan/v1.yaml); do not add capabilities
merely to satisfy validation.

Minimum shape:

```yaml
apiVersion: acdd/adapter/v1
kind: adapter
id: owner-task/v1
role: task
provides: [task_read, task_write, impact]
procedure:
  - Read and update one bound task through current evidence.
authority:
  tasks: "roadmap/**/tasks/*.md"
  impact:
    domains: [deployment, api-compatibility, operations]
inputAuthorities:
  bound-document: ["roadmap/**/tasks/*.md"]
constraints:
  - Bind exactly one active task and preserve gate order.
```

Required fields:

| Field | Meaning |
|---|---|
| `id` | Stable owner-specific identifier; version it when compatibility changes. |
| `role` | One of `task`, `implementation`, `plan`, or `audit`. |
| `provides` | Capabilities implemented by this owner. |
| `procedure` | Inline steps or adapter-relative procedure files. |
| `authority` | Concrete paths, commands, evidence sources, mappings, and impact axes. |
| `constraints` | Fail-closed owner invariants. |

Optional fields:

| Field | Meaning |
|---|---|
| `availability` | Runtime prerequisites that may block a gate. |
| `gateProcedures` | Gate-specific operations, commands, launchers, discovery, and tool policy. |
| `resources` / `scripts` | Adapter-relative contracts, templates, and executables. |
| `externalMappings` | Projection to Linear, Jira, or another owner system. |
| `inputAuthorities` | Allowed patterns for typed document inputs. |
| `writePolicy` | Additional allow/deny rules and narrow protected-write exceptions. |
| `receipts` | Owner-specific evidence storage and closure details. |
| `skillExtensions` | Owner guidance that strengthens the profile. |

Resolve `procedure`, `resource`, and `script` paths from the adapter directory,
canonicalize them, verify that they exist, and keep them inside the allowed
workspace root. The session working directory never changes their meaning.

## Capabilities, routing, and executor ownership

Profiles define ordered gates. Capability contracts define what each role must
provide. Routing defines which adapters contribute and which single adapter may
execute a gate:

- task capabilities: [`contracts/task/v1.yaml`](contracts/task/v1.yaml)
- plan capabilities: [`contracts/plan/v1.yaml`](contracts/plan/v1.yaml)
- task routing: [`routing/task/v1.yaml`](routing/task/v1.yaml)
- plan routing: [`routing/plan/v1.yaml`](routing/plan/v1.yaml)

For every gate:

1. load authority and capabilities from all routed adapters;
2. execute only through `executorAdapter`;
3. load that owner's gate procedure;
4. issue evidence and receipts only through the executor owner;
5. update only state permitted by adapter authority.

Task closure review belongs to `implementation`; planning review belongs to
`plan`; `audit` publishes one selected terminal report and owns no gate.

## Gate procedures and launchers

Repository commands belong in the adapter that owns them. A simple gate may use
an ordered procedure or exact command. An independent review gate binds a real
launcher.

Task architecture uses separate inspector and coordinator launchers:

```yaml
gateProcedures:
  architecture/v1:
    operation: architecture-verify
    contract: path/to/architecture-verification.yaml
    runtime: host-name
    launchers:
      inspector:
        kind: command
        target: reviewer-command
        arguments: [--session, "{sessionUuid}"]
        promptTransport: final-argument
      coordinator:
        kind: command
        target: reviewer-command
        arguments: [--session, "{sessionUuid}", --no-tools]
        promptTransport: final-argument
    authoritativeSessions: 1
    reviewRoot: workspace
    commandCwd: implementation-repository
    discoveryMethods:
      exactText: {capability: source_map, tools: [registered-text-search]}
      structural: {capability: structural_search, tools: [registered-ast-search]}
      dependency: {capability: impact, tools: [registered-impact-tool]}
    toolEnvelope:
      admit: [registered-read-only-tools]
      deny: [shell, edit, write]
```

Rules:

- `runtime` is provenance; `launcher.target` is the command or registered tool.
- Resolve launcher paths from the owning adapter.
- Substitute only declared placeholders and use the declared prompt transport.
- Verify the target before launching.
- Admit only tools actually available in the launched session.
- Keep inspectors read-only and non-writing.
- Launch four inspectors concurrently against one fingerprint.
- Validate all partition outputs before starting the tool-free coordinator.
- Treat schema, transport, or unavailable-runtime failures as `BLOCKED`.
- Preserve completed outputs and bounded redacted diagnostics.

Use the complete working bindings in
[`examples/planner/.acdd/task-adapter.yaml`](examples/planner/.acdd/task-adapter.yaml)
and [`examples/reviewers/`](examples/reviewers/).

### Architecture artifacts and amendments

A task adapter that supports G1 architecture amendments declares an
`architectureArtifacts` script. It receives typed `context`, `prepare`,
`launch`, `terminal`, and `validate` operations. The adapter chooses storage,
retention, redaction, serialization, and Git-ignore policy.

Keep one YAML receipt and one paired secret-redacted JSONL transcript per
amendment. The receipt binds the transcript path and SHA-256. Keep raw launcher
output out of task Markdown and YAML. The canonical lifecycle is described in
[`architecture.md`](skills/acdd-task/references/architecture.md).

## Inputs, proof mappings, evidence, and receipts

### Inputs

Under `## ACDD inputs`, use `apiVersion: acdd/inputs/v1` and workspace-relative
paths. Supported types are:

- `source`
- `test`
- `configuration`
- `generated`
- `dependency`
- `environment`
- `accepted-review-findings`

Every path must match an `inputAuthorities` pattern in at least one supplied
adapter.

### Proof obligation mapping

New task contracts map each named proof to its boundary, required scenarios, and
execution evidence:

```md
## Proof obligation mapping

| Proof ID | Boundary | Required scenarios | Execution evidence |
|---|---|---|---|
| `proof.example` | owner boundary | adversarial scenario and exact outcome | `pending` |
```

The validator checks table shape, unique IDs, and coverage of `## Named proof
IDs`. `pending` is allowed during implementation and rejected after terminal
`review/v1` or `handoff/v1`. The implementation reviewer verifies the actual
test node, backend, execution mode, cardinality, outcomes, and forbidden effects.
For every proof, declare applicable operations, live/replay/import paths,
implementations, authority transitions, execution modes, terminal outcomes, and
forbidden effects. Each declared combination needs its own evidence or a bounded
`N/A`; one representative combination does not close the others.

### Evidence

Under `## ACDD gate evidence`, record `apiVersion: acdd/gate-evidence/v1` with the
appropriate kind: `basis`, `command`, `proof-bundle`, `review`, `handoff`, or
`rationale`.

Command evidence records the exact command, UTC time, exit code, bounded redacted
output, result, and current fingerprint. RED evidence also freezes its proof
definition and component locks. Review evidence records independent session
provenance, verdict, authority sources, production/alternate paths,
contradictions, impact, proof mappings, and bounded findings. Store raw reviewer
transcripts outside Markdown.

### Fingerprints and invalidation

Generate semantic blocks with [`record_fingerprint.py`](scripts/record_fingerprint.py)
and record command evidence with [`record_proof.py`](scripts/record_proof.py).
Never invent or transcribe a digest by hand.

Receipt policy comes from:

- [`contracts/receipt/task/v1.yaml`](contracts/receipt/task/v1.yaml)
- [`contracts/receipt/plan/v1.yaml`](contracts/receipt/plan/v1.yaml)

When an input changes, use [`compute_invalidation.py`](scripts/compute_invalidation.py)
to find the smallest ordered rerun set. Preserve stale evidence for auditability,
but do not treat it as current.

## Write policy

Core protected paths are `.agents/**` and every root or nested `AGENTS.md`.
A protected write requires both an explicit user request and a narrow
`writePolicy.protectedAllow` rule with
`authorization: explicit-user-request`. Deny rules win. Preserve unrelated
worktree changes; never reset, restore, or absorb them without authorization.

## External mappings

Use `externalMappings` to project canonical hierarchy rather than redefine it:

- Linear: roadmap → Initiative, phase → Project, milestone → Project Milestone,
  task → Issue;
- Jira: roadmap → Initiative, phase → Epic, milestone → Version/Release, task →
  Story/Task;
- filesystem planning: roadmap → phase → milestone → task files.

Plans remain separately bound artifacts. See
[`examples/linear/.acdd/`](examples/linear/.acdd/) and
[`examples/jira/.acdd/`](examples/jira/.acdd/).

## Validate a real workspace

Task delivery:

```bash
cd workspace/plugins/acdd-workflow
python3 scripts/validate_acdd.py \
  --profile profiles/task/v1.yaml \
  --workspace-root ../.. \
  --document planner/roadmap/phase-05/tasks/example.md \
  --adapter task=planner/.acdd/task-adapter.yaml \
  --adapter implementation=product/.acdd/implementation-adapter.yaml
```

Planning:

```bash
python3 scripts/validate_acdd.py \
  --profile profiles/plan/v1.yaml \
  --workspace-root ../.. \
  --document planner/plans/active/example.md \
  --adapter plan=planner/.acdd/plan-adapter.yaml
```

Add `--settings <json>` when validation must also prove that every named skill
resolves exactly once:

```json
{"skills": ["plugins/acdd-workflow/skills", "planner/.agents/skills"]}
```

Validate a self-contained plan:

```bash
python3 scripts/check_simple_plan.py \
  --plan examples/simple-plan/PLAN.md --strict
```

## Add the agent route

Add only a short route at the workspace or owner boundary:

```md
## ACDD

- Task delivery → `plugins/acdd-workflow/skills/acdd-task/SKILL.md` with
  `plugins/acdd-workflow/profiles/task/v1.yaml`, the task owner's
  `.acdd/task-adapter.yaml`, and the implementation owner's
  `.acdd/implementation-adapter.yaml`.
- Planning → `plugins/acdd-workflow/skills/acdd-plan/SKILL.md` with
  `plugins/acdd-workflow/profiles/plan/v1.yaml` and `.acdd/plan-adapter.yaml`.
- Validate before executing a gate; follow profile order and stop on blocked,
  failed, or stale evidence.
```

Adjust paths and list only workflows actually supported by that owner.

## Verify integration changes

Run the target repository's own gates, then verify plugin changes from this
checkout:

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
python3 scripts/check_markdown_links.py --root .
git diff --check
```
