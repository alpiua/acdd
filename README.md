> **DEPRECATED / ARCHIVED** — Do not use for new work. Successor: [`alpiua/acdd`](https://github.com/alpiua/acdd) (ACDD — design / contract / build / review / handoff). This tree is the last archived G0–G3 plugin line.

# ACDD Workflow

ACDD means **Architecture Contract-Driven Development**.

It is a delivery method
for turning an intended change into a bounded architecture contract, checking
that contract against the live system, implementing only the approved scope,
and closing the work with current executable evidence. ACDD does not replace a
project's tests, release process, issue tracker, or review tools. It connects
them through host-neutral profiles and repository-owned adapters so that every
PASS says what was checked, by whom, against which inputs, and with which result.

The short version is:

```text
Intent
  → G0: contract and architecture
  → G1: RED, implementation, runtime, and parity
  → G2: security
  → G3: release, review, and handoff
```

Receipts carry input fingerprints. When relevant source, tests, configuration,
dependencies, environment, or accepted findings change, affected receipts become
stale and the dependent gates run again. Missing infrastructure is `blocked`, not
PASS, and a reviewer may expose missing scope but cannot authorize it.

ACDD provides two workflows:

| Workflow | Use it for | Profile |
|---|---|---|
| Task delivery | Deliver one already-bound implementation task | [`acdd/task/v1`](profiles/task/v1.yaml) |
| Planning | Create or improve one bounded planning set and inactive task candidates | [`acdd/plan/v1`](profiles/plan/v1.yaml) |

Examples: [`bound task`](examples/task/TASK.md) and
[`self-contained planning set`](examples/simple-plan/).

These are workflow profiles, not hierarchy levels. `roadmap`, `phase`,
`milestone`, and `task` are planning artifacts inside `acdd/plan/v1`:
`roadmap-shape/v1` validates roadmap and phase structure,
`milestone-shape/v1` validates milestones and their task membership, and
`decomposition/v1` produces inactive task candidates. A selected task later
moves to the separate `acdd/task/v1` delivery workflow.

## Task delivery: G0–G3

Task delivery has four human-facing stages implemented by nine ordered gates.
Every gate reads the same bound task, uses the adapters selected for that owner,
records typed evidence, and issues a receipt for the current fingerprint. A later
gate never compensates for a missing, blocked, failed, or stale predecessor.

### G0 — decide what may be built

G0 completes before implementation. It identifies the production caller, the
canonical owner, public and persisted contracts, authority and identity,
lifecycle and failure behavior, alternate paths, affected domains, proof IDs,
and explicit non-goals.

| Gate | What it checks | Adapters and execution |
|---|---|---|
| `matrix/v1` | Every affected domain has an owner, propagation path, mitigation, authorization, proof, or explicit blocker. | Reads `task + implementation`; the `task` adapter executes and updates the task. |
| `architecture/v1` | The proposed contract is coherent with live source, callers, dependencies, authority, lifecycle, storage, compatibility paths, and proof obligations. | Reads `task + implementation`; the `task` adapter launches four read-only inspectors and one coordinator. |

Examples: [`task adapter`](examples/planner/.acdd-legacy/task-adapter.yaml) and
[`architecture-review adapter`](examples/reviewers/.acdd-legacy/task-adapter.yaml).

New tasks freeze G0 authority under `## G0 architecture baseline`. Existing active
tasks keep the semantic baseline they were approved with; copying it into a new
heading would create a different candidate. If implementation later exposes a
missing architectural decision, add a bounded `## G1 redesign amendments` item
and review that amendment instead of rewriting G0.

#### How architecture verification works

The architecture runner freezes one candidate fingerprint and one declared code
snapshot, then launches exactly four independent partitions:

| Partition | Primary question |
|---|---|
| `contract` | Is there one canonical owner, type, serializer, transport, normalization path, and persisted-contract meaning? |
| `authority` | Are identity, authorization, tenant/scope boundaries, validation order, and negative proofs explicit and fail-closed? |
| `callers` | Are the production caller, direct and alternate entry points, retries, caches, projections, and downstream impact covered? |
| `persistence` | Are lifecycle, failure, rollback, cleanup, backend parity, revisions, migrations, and terminal outcomes coherent? |

All four inspectors receive the same fingerprint, remain read-only, and return
bounded evidence and typed candidate-design findings. They cannot write the task,
issue a receipt, or decide the final verdict. Only after all four outputs validate
does a tool-free coordinator reconcile the findings and return `PASS` or `FAIL`.
A transport or schema failure is `BLOCKED` and preserves completed outputs.

The canonical architecture contract requires the union of the partitions to
cover all guidance axes: owner, production path, contract propagation,
authority, lifecycle/failure/cleanup, alternate paths, persisted parity, impact,
negative proof, contradictions, normalization, authorization before selection,
terminal outcome truth, and terminal projection truth. Full definitions live in
[`architecture.md`](skills/acdd-task/references/architecture.md); the executable
shape is [`contracts/architecture-verification/v1.yaml`](contracts/architecture-verification/v1.yaml).

Each named proof belongs in one compact `Proof obligation mapping` table:

| Proof ID | Boundary | Required scenarios | Execution evidence |
|---|---|---|---|
| `proof.concurrent-write` | persistence owner | one winner, typed loser, no residue | `pending` |

For each proof, declare the applicable operations, live/replay/import paths,
implementations, authority transitions, sequential/concurrent mode, terminal
outcomes, and forbidden effects. Each declared combination is one evidence
obligation; executing one representative combination does not cover its
siblings. Use a bounded `N/A` only when that dimension is absent.

`pending` is valid while implementation is underway. Terminal `review/v1` and
`handoff/v1` require executable evidence. The reviewer verifies that the named
test actually covers the declared boundary, backend, sequential/concurrent mode,
cardinality, terminal outcomes, and forbidden effects. A test name or Code Map
relationship alone is not proof.

Before each architecture launch, run
[`check_architecture_admission.py`](scripts/check_architecture_admission.py).
It enforces the candidate baseline, rejects an unchanged previous FAIL, and caps
material retries. After a FAIL, rerun only after a real change produces a new
current fingerprint. The full runner is
[`run_architecture.py`](scripts/run_architecture.py); its concrete launcher,
working directory, model, tools, and artifact storage come from the task adapter.

### G1 — prove the implementation

G1 starts only after G0 passes for the current semantic candidate.

| Gate | What it checks | Adapters and execution |
|---|---|---|
| `red/v1` | The smallest expected failing proof demonstrates the approved gap before implementation. Structural/import failures do not count as product RED evidence. | Reads `task + implementation`; the `implementation` adapter runs the proof. |
| `runtime/v1` | The real production caller and applicable failure path produce the required terminal behavior. | The `implementation` adapter runs the owner command in the implementation repository. |
| `parity/v1` | Behavior, faults, authorization, lifecycle, configuration, owner path, storage/backend, generated surfaces, and alternate paths agree wherever applicable. | The `implementation` adapter selects real parity commands and records applicability. |

Example: [`implementation adapter`](examples/codebase/.acdd-legacy/implementation-adapter.yaml).

Evidence must exercise the behavior, execution conditions, and affected
implementations named by the claim. When a parity dimension does not apply,
record the bounded inapplicability rationale required by the profile.

### G2 — check the final security boundary

| Gate | What it checks | Adapters and execution |
|---|---|---|
| `security/v1` | Final authorization, identity and tenant isolation, untrusted input, paths and secrets, payload exposure, lifecycle/audit behavior, external effects, and fail-closed denial. | Reads `task + implementation`; the `implementation` adapter runs the repository's security proofs and structural checks. |

Example: [`implementation adapter`](examples/codebase/.acdd-legacy/implementation-adapter.yaml).

G2 reviews the implemented system, not the intended design. Every applicable
security contour needs positive and negative evidence; an inapplicable contour
needs an explicit reason.

### G3 — release, challenge, and hand off

| Gate | What it checks | Adapters and execution |
|---|---|---|
| `release/v1` | The exact repository-owned quality gate succeeds on the settled implementation. | The `implementation` adapter runs the real release command. |
| `review/v1` | An independent reviewer checks current source, tests, configuration, runtime evidence, proof mappings, security, compatibility, and residual risk against the approved contract. | The `implementation` adapter owns the terminal review launcher. |
| `handoff/v1` | All required receipts are current, accepted findings have been propagated, blockers are empty, and changed artifacts are recorded. | The `task` adapter writes the final checkpoint. |

Examples: [`implementation adapter`](examples/codebase/.acdd-legacy/implementation-adapter.yaml),
[`terminal-review adapter`](examples/reviewers/.acdd-legacy/implementation-adapter.yaml), and
[`task handoff adapter`](examples/planner/.acdd-legacy/task-adapter.yaml).

Accepted review findings change the evidence set. Apply authorized fixes, compute
the affected rerun set with
[`compute_invalidation.py`](scripts/compute_invalidation.py), rerun those gates,
and review the new fingerprint. After the terminal report, the workflow-learning
record may propose future guidance improvements; it does not rewrite the reviewed
verdict or invalidate older snapshots by itself.

## Planning workflow

Planning uses one `plan` adapter. It creates or improves a primary plan and a
bounded set of roadmap, phase, milestone, and inactive task artifacts; it does
not implement those tasks.

| Gate | What it checks |
|---|---|
| `intent/v1` | Outcome, owner binding, scope, non-goals, planning set, and lifecycle status. |
| `evidence/v1` | Live code, documentation, prior decisions, current planning state, and contradictions. |
| `architecture/v1` | Owners, production paths, authority, lifecycle, dependencies, security, impact, and caller burden across the planning set, followed by independent plan verification. |
| `plan-shape/v1` | Primary-plan metadata, phase span, decisions, dependencies, impact, promotion rules, and blockers. |
| `roadmap-shape/v1` | Roadmap/phase membership, ordering, dependencies, impact propagation, backlinks, and execution claims. |
| `milestone-shape/v1` | Milestone architecture slices, task membership, gates, backlinks, impact, and evidence-bound closure. |
| `decomposition/v1` | Executable, inactive, milestone-bound task drafts with owners, prerequisites, decisions, and expected evidence. |
| `review/v1` | Independent challenge of the complete planning set against live evidence. |
| `publish/v1` | Links, metadata, shape, drift, and adapter-owned derived-state refresh. |
| `handoff/v1` | Current receipts, blockers, changed artifacts, and task-flow candidates. |

Start from [`examples/planner/.acdd-legacy/plan-adapter.yaml`](examples/planner/.acdd-legacy/plan-adapter.yaml),
[`examples/simple-plan/`](examples/simple-plan/), or an external projection such
as [`examples/linear/.acdd-legacy/`](examples/linear/.acdd-legacy/) and
[`examples/jira/.acdd-legacy/`](examples/jira/.acdd-legacy/).

## How gates run

ACDD separates the universal method from repository-specific execution:

1. Select a profile and bound Markdown document.
2. Load every required owner adapter.
3. Run `validate_acdd.py` to validate profile, routing, capabilities, adapter
   authority, document shape, evidence, fingerprints, receipts, and gate order.
4. Resolve the current gate through the profile routing table.
5. Collect context from all routed adapters, but execute only through that
   gate's `executorAdapter`.
6. Run the adapter's procedure or launcher from its declared owner directory.
7. Record bounded typed evidence and a receipt for the computed fingerprint.
8. Validate again before advancing.

`validate_acdd.py` validates state; it does not invent evidence or run every
project command automatically. Runtime, security, release, and review commands
belong to the repository adapters. Architecture is the exception with a generic
orchestrator: `run_architecture.py` executes the launcher bindings supplied by
the task adapter.

Launchers are explicit. `runtime` is provenance, while `launcher.target` is the
actual command or registered tool. Architecture uses separate inspector and
coordinator launchers. Terminal review uses the launcher selected by the
implementation or plan adapter. See
[`examples/reviewers/`](examples/reviewers/) for complete bindings.

## Adapter system

An adapter translates one repository owner's real paths, commands, tools, and
policies into canonical ACDD capabilities. It may strengthen a gate, but it
cannot remove, reorder, or weaken profile requirements.

| Role | Place it in | Responsibility |
|---|---|---|
| `task` | Task/backlog repository: `.acdd-legacy/task-adapter.yaml` | Task state, impact axes, G0 execution, receipts, and handoff. |
| `implementation` | Source/runtime repository: `.acdd-legacy/implementation-adapter.yaml` | Source discovery, RED/runtime/parity/security/release commands, and terminal code review. |
| `plan` | Planning repository: `.acdd-legacy/plan-adapter.yaml` | Planning authority, hierarchy validation, architecture review, publication, and planning handoff. |
| `audit` | Report repository: `.acdd-legacy/audit-adapter.yaml` | Optional publication of one selected terminal report; it owns no workflow gate. |

A task workflow composes `task + implementation` and may add `audit`. A planning
workflow uses `plan` and may add `audit`. Each route has exactly one executor;
other adapters contribute authority and evidence without issuing that gate's
receipt.

Create an adapter by copying the closest bundle from
[`examples/README.md`](examples/README.md), then replace every example path,
command, launcher, model, tool, authority, impact axis, and external mapping with
a live owner value. Keep the adapter beside its owner, resolve relative
procedures/resources/scripts from the adapter directory, and keep every resolved
path inside the allowed workspace root.

The minimum shape is:

```yaml
apiVersion: acdd/adapter/v1
kind: adapter
id: owner-purpose/v1
role: implementation
provides: [source_map, structural_search, run_gate, independent_review, review_execution]
procedure:
  - Run the repository-owned procedure.
authority:
  source: "src/**"
  commands: [./scripts/quality-gate]
inputAuthorities:
  source: ["src/**"]
  test: ["tests/**"]
constraints:
  - Fail closed when required infrastructure is unavailable.
```

Capability names and exact required fields come from
[`contracts/adapter/v1.yaml`](contracts/adapter/v1.yaml),
[`contracts/task/v1.yaml`](contracts/task/v1.yaml), and
[`contracts/plan/v1.yaml`](contracts/plan/v1.yaml). Detailed launcher, artifact,
write-policy, receipt, and external-mapping configuration belongs in
[`INSTALL.md`](INSTALL.md).

## How the workflow package is organized

The package has declarative contracts at the top and small executable layers
under `scripts/`:

```text
profiles/   ordered task and planning gates
contracts/  capabilities, adapters, receipts, architecture, learning, plan shapes
routing/    participating adapters and one executor per gate
skills/     canonical agent procedures and detailed gate guidance
examples/   runnable owner adapters and bound documents
scripts/    validation, fingerprints, orchestration, evidence, and diagnostics
```

The most important scripts are:

| Script | Purpose |
|---|---|
| [`validate_acdd.py`](scripts/validate_acdd.py) | Validate one profile, its adapters, the bound document, evidence, receipts, routing, and closure state. |
| [`run_architecture.py`](scripts/run_architecture.py) | Freeze and execute the four-partition architecture review through adapter launchers. |
| [`check_architecture_admission.py`](scripts/check_architecture_admission.py) | Decide whether a G0 or amendment architecture launch is admitted. |
| [`record_fingerprint.py`](scripts/record_fingerprint.py) | Generate the canonical semantic fingerprint block. |
| [`record_proof.py`](scripts/record_proof.py) | Run or record command/proof-bundle evidence with redaction and the current fingerprint. |
| [`compute_invalidation.py`](scripts/compute_invalidation.py) | Compute the smallest ordered gate rerun set after typed input changes. |
| [`check_gate_tool.py`](scripts/check_gate_tool.py) | Reject a tool call outside the current gate's adapter envelope. |
| [`check_structural_invariants.py`](scripts/check_structural_invariants.py) | Run adapter-supplied AST structural rules. |
| [`check_simple_plan.py`](scripts/check_simple_plan.py) | Validate the optional self-contained plan shape. |
| [`acdd_metrics.py`](scripts/acdd_metrics.py) | Summarize receipt status from selected Markdown documents. |
| [`check_markdown_links.py`](scripts/check_markdown_links.py) | Validate repository-local Markdown links. |

Modules such as `acdd_document.py`, `acdd_fingerprint.py`,
`architecture_verification.py`, `architecture_governor.py`, `invalidation.py`,
`value_domains.py`, and `workflow_learning.py` implement shared validation logic;
they are imported by the command-line scripts rather than used as the normal
human entry point.

## Install and run

Keep the plugin in a shared workspace with the repositories that own planning,
implementation, and optional audit publication:

```text
workspace/
├── plugins/acdd-workflow/
├── planner/.acdd-legacy/task-adapter.yaml
├── planner/.acdd-legacy/plan-adapter.yaml
├── product/.acdd-legacy/implementation-adapter.yaml
└── audit/.acdd-legacy/audit-adapter.yaml
```

Install the validator dependencies and verify the plugin:

```bash
cd workspace/plugins/acdd-workflow
python3 -m pip install --upgrade PyYAML pytest
python3 -m pytest tests -q
python3 scripts/check_markdown_links.py --root .
```

There is no daemon and no global `acdd` executable. Validate a task composition
from the plugin checkout:

```bash
python3 scripts/validate_acdd.py \
  --profile profiles/task/v1.yaml \
  --workspace-root ../.. \
  --document planner/roadmap/phase-05/tasks/example.md \
  --adapter task=planner/.acdd-legacy/task-adapter.yaml \
  --adapter implementation=product/.acdd-legacy/implementation-adapter.yaml
```

Validate a planning composition:

```bash
python3 scripts/validate_acdd.py \
  --profile profiles/plan/v1.yaml \
  --workspace-root ../.. \
  --document planner/plans/active/example.md \
  --adapter plan=planner/.acdd-legacy/plan-adapter.yaml
```

See [`INSTALL.md`](INSTALL.md) for adapter creation, launcher configuration,
architecture execution, evidence recording, validation recipes, and owner
`AGENTS.md` integration.

### Tell an agent to use ACDD

Put a short route in the workspace or owner `AGENTS.md`:

```md
## ACDD

- Task delivery → `plugins/acdd-workflow/skills/acdd-task/SKILL.md` with
  `plugins/acdd-workflow/profiles/task/v1.yaml`, the task owner's
  `.acdd-legacy/task-adapter.yaml`, and the source owner's
  `.acdd-legacy/implementation-adapter.yaml`.
- Planning → `plugins/acdd-workflow/skills/acdd-plan/SKILL.md` with
  `plugins/acdd-workflow/profiles/plan/v1.yaml` and the planning owner's
  `.acdd-legacy/plan-adapter.yaml`.
- Validate the composition before executing a gate. Follow profile order, use
  the routed executor adapter, keep evidence and receipts current, and stop on
  blocked or failed gates.
```

Then give the agent a concrete request:

```text
Start or continue the bound task at planner/path/to/task.md using acdd/task/v1.
Load planner/.acdd-legacy/task-adapter.yaml and product/.acdd-legacy/implementation-adapter.yaml.
Validate the composition, inspect the current receipts, and execute the next
eligible gate only. Record real evidence; do not manufacture or skip receipts.
```

For planning:

```text
Create or improve the planning set rooted at planner/plans/active/example.md
using acdd/plan/v1 and planner/.acdd-legacy/plan-adapter.yaml. Validate first, execute
gates in profile order, create inactive task candidates, and stop on blockers.
```

## Why `INSTALL.md` remains separate

README is the human-oriented explanation of the method, stages, gate execution,
adapters, package structure, and first run. [`INSTALL.md`](INSTALL.md) remains a
technical runbook for people integrating a real repository. It contains the
complete adapter field reference, capability and routing lookup, launcher and
artifact contracts, inputs/evidence/receipt rules, write policy, external-system
mappings, exact validation commands, and owner `AGENTS.md` template. Keeping
those details separate makes this README readable without weakening the
operational contract.

Further reading:

- [Getting started walkthrough](docs/getting-started.md)
- [Contract versioning policy](docs/versioning.md)
- [Examples index](examples/README.md)
- [Runner optimization notes](docs/optimization.md)

## Verify plugin changes

```bash
python3 -m pytest tests -q
python3 scripts/check_markdown_links.py --root .
git diff --check
```
