# ACDD Workflow

ACDD (**Architecture Contract-Driven Development**) is a methodology for
turning an intended change into an explicit architecture contract, proving that
contract against the real system, and only then implementing and releasing it.
This repository packages that methodology as host-neutral profiles, contracts,
adapters, validators, skills, and runnable examples.

ACDD is designed for work where “the tests pass” is not enough. A change must
also have a known owner, production caller, authority boundary, failure
behavior, propagation path, and current evidence. The workflow makes those
claims explicit and invalidates them when their inputs change.

## The methodology

ACDD follows five principles:

1. **Architecture before mutation.** Before implementation, identify the real
   owner, caller, contract, data/configuration path, alternate paths, security
   boundary, and downstream impact.
2. **One bounded contract.** The task describes the exact behavior to add or
   change, its permitted scope, and the proof that will demonstrate it. Review
   cannot silently enlarge that scope.
3. **Evidence, not assertions.** Each transition is backed by typed evidence:
   source discovery, an expected failing proof, runtime execution, negative
   paths, security checks, repository gates, or independent review.
4. **Evidence expires.** Receipts carry SHA-256 fingerprints of the inputs that
   made them true. A relevant source, test, configuration, dependency,
   environment, generated artifact, or accepted finding change makes the
   receipt stale and invalidates dependent stages.
5. **Independent challenge.** Architecture and closure reviews run outside the
   authoring path. Read-only inspectors collect bounded evidence; one
   coordinator owns the verdict. A reviewer can find a contradiction but cannot
   grant implementation authority.

The methodology has two workflows:

| Workflow | Purpose | Profile |
|---|---|---|
| **Task delivery** | Deliver one already-bound implementation task | [`acdd/task/v1`](profiles/task/v1.yaml) |
| **Planning** | Create or improve one primary plan and its bounded planning set | [`acdd/plan/v1`](profiles/plan/v1.yaml) |

Planning preserves `roadmap → phase → milestone → task`. A plan is a separate
artifact bound to one of those owners and may span phases. Planning creates
inactive task candidates; a later task workflow activates and delivers one of
them.

## Task stages: G0–G3

G0–G3 are the human-facing stages of ACDD task delivery. Internally they are
implemented by nine ordered receipt gates. A stage is complete only when every
receipt in that stage is current for the same contract.

### G0 — architecture and execution contract

**Internal gates:** `matrix/v1`, `architecture/v1`.

G0 answers “what exactly are we allowed to build?” before implementation code
changes. It records:

- affected domains, owners, propagation, mitigation, authorization, and proofs;
- the production trigger and caller;
- the canonical contract and implementation owner;
- data, storage, configuration, and generated-artifact paths;
- authority, identity, tenant, lifecycle, and external-effect boundaries;
- direct and alternate callers;
- expected success and fail-closed behavior;
- decision IDs and proof IDs;
- explicit out-of-scope boundaries and blockers.

An independent architecture verification then checks the contract against live
source and dependencies. G0 passes only when all required read-only inspection
partitions are complete, contradictions are resolved, every impact axis is
mapped, and the coordinator returns `PASS` for the current fingerprint.

A failed review is not a reason to “continue carefully.” Update the task
contract or evidence, produce a new fingerprint, and rerun only after a real
change. Re-running an unchanged failed fingerprint is forbidden. Before each architecture launch, run `scripts/check_architecture_admission.py` (clean/candidate baseline, unchanged-FAIL ban, material attempt cap). After accepted changes, use `scripts/compute_invalidation.py` for the targeted dependent-gate rerun set; unknown classes fail closed.

### G1 — RED, runtime, and parity

**Internal gates:** `red/v1`, `runtime/v1`, `parity/v1`.

G1 proves that the bounded contract is implemented:

1. preserve the smallest expected failing proof of the declared gap;
2. implement only the G0-approved contract;
3. run the real production caller and applicable failure path;
4. prove parity across every applicable dimension: behavior, failures,
   authorization, lifecycle, owner path, configuration, storage/backend, and
   generated/public surfaces.

A unit test of a helper is not a production-path proof. A compatibility shim is
not parity unless the contract explicitly authorizes it.

### G2 — final security

**Internal gate:** `security/v1`.

G2 checks the final implementation rather than the intended design. It covers
all applicable security contours: authorization, identity and tenant isolation,
untrusted input, path and secret handling, payload exposure, lifecycle and
audit behavior, external effects, and fail-closed denial. Inapplicable contours
must have an explicit rationale; they are not silently skipped.

### G3 — release, independent review, and handoff

**Internal gates:** `release/v1`, `review/v1`, `handoff/v1`.

G3 runs the exact repository-owned release gate after implementation settles,
then independently reviews the current source, tests, configuration, and
release evidence. Accepted findings change the input fingerprint and require
rerunning every affected earlier gate before another closure review.

The handoff records changed artifacts, current receipts, residual risk, and
blockers. The task closes only when every required receipt is terminal and
current, the final review passes, and blockers are empty.

## Strict transitions, fingerprints, and subagents

ACDD is fail-closed:

- gates execute in profile queue order;
- no later receipt compensates for a missing or stale earlier receipt;
- each non-pending receipt references typed inline evidence;
- each receipt carries `sha256:<64 hex characters>` and a UTC timestamp;
- changing an input listed by the gate policy invalidates that gate and every
  dependent successor;
- unavailable infrastructure is recorded as blocked, never converted to pass;
- review findings do not authorize scope expansion.

Architecture verification can use up to four parallel **read-only inspectors**.
Inspectors share one fingerprint, cannot write the task, cannot issue receipts,
and cannot return the authoritative verdict. They cover the adapter-supplied
partitions (for example contract, authority, callers, and persistence) using
exact-text, structural, and dependency-impact discovery. One isolated
coordinator reconciles all findings and persisted-contract mappings and alone
returns `PASS` or `FAIL`.

Terminal implementation or plan review is a separate subagent operation chosen
by the owner adapter. It runs after the relevant evidence stabilizes. The
runtime name is provenance; the adapter must bind an actual command or tool
launcher and a strict tool envelope.

## Install and connect the plugin

### 1. Put the plugin in the workspace

Use one shared checkout for all owner repositories:

```text
workspace/
├── planner/                   # optional task/plan owner
├── product/                   # implementation owner
├── audit/                     # optional report publisher
└── plugins/
    └── acdd-workflow/         # this repository
```

```bash
cd workspace
git clone <acdd-workflow-url> plugins/acdd-workflow
cd plugins/acdd-workflow
python3 -m pip install --upgrade PyYAML pytest
python3 -m pytest tests -q
python3 scripts/check_markdown_links.py --root .
```

There is no daemon or global `acdd` executable. Run
`scripts/validate_acdd.py` from the plugin checkout with explicit owner paths.

### 2. Create `.acdd/` in each owner repository

Keep owner-specific paths, commands, tools, and policy beside their owner:

```text
planner/.acdd/
├── task-adapter.yaml
└── plan-adapter.yaml

product/.acdd/
└── implementation-adapter.yaml

audit/.acdd/
└── audit-adapter.yaml
```

Copy the nearest example and replace every example authority, path, command,
and tool with a real owner-owned value:

| Need | Starting point |
|---|---|
| Planner task and plan ownership | [`examples/planner/.acdd/`](examples/planner/.acdd/) |
| Code/test/configuration ownership | [`examples/codebase/.acdd/`](examples/codebase/.acdd/) |
| Self-contained milestone plan | [`examples/simple-plan/`](examples/simple-plan/) |
| Linear projection | [`examples/linear/.acdd/`](examples/linear/.acdd/) |
| Jira projection | [`examples/jira/.acdd/`](examples/jira/.acdd/) |
| Review launchers and impact discovery | [`examples/reviewers/.acdd/`](examples/reviewers/.acdd/) |
| Optional report publication | [`examples/audit/.acdd/`](examples/audit/.acdd/) |
| Bound task Markdown | [`examples/task/TASK.md`](examples/task/TASK.md) |

### 3. Add a workspace route to `AGENTS.md`

Place routing at the nearest workspace or repository owner. Adjust paths to the
actual layout:

```md
## ACDD workflow

- Use `plugins/acdd-workflow/profiles/task/v1.yaml` for one bound
  implementation task and `profiles/plan/v1.yaml` for one bounded planning set.
- Load the owner adapters from each repository's `.acdd/` directory before
  executing a gate. Resolve adapter-relative procedures and resources from the
  adapter file, not from the session CWD.
- Run `plugins/acdd-workflow/scripts/validate_acdd.py` with explicit
  `--workspace-root`, `--document`, and `--adapter role=path` arguments.
- Complete G0 before implementation; preserve RED evidence in G1; run final
  security in G2; close only through release, independent review, and handoff
  in G3.
- Keep typed inputs, evidence, fingerprints, receipts, and blockers inline in
  the bound task or primary plan. Never manufacture a receipt.
```

Use [`Install.md`](Install.md) when creating, installing, validating, or running
owner adapters. [`AGENTS.md`](AGENTS.md) remains a short repository map.

### 4. Validate the composition

Task delivery needs `task` and `implementation` adapters:

```bash
cd workspace/plugins/acdd-workflow
python3 scripts/validate_acdd.py \
  --profile profiles/task/v1.yaml \
  --workspace-root ../.. \
  --document planner/roadmap/phase-05/tasks/example.md \
  --adapter task=planner/.acdd/task-adapter.yaml \
  --adapter implementation=product/.acdd/implementation-adapter.yaml
```

Planning needs one `plan` adapter:

```bash
python3 scripts/validate_acdd.py \
  --profile profiles/plan/v1.yaml \
  --workspace-root ../.. \
  --document planner/plans/active/example.md \
  --adapter plan=planner/.acdd/plan-adapter.yaml
```

Use `--settings workspace-settings.json` when you also want validation to prove
that each gate's named skill resolves exactly once. The settings shape is:

```json
{"skills": ["plugins/acdd-workflow/skills", "planner/.agents/skills"]}
```

## Adapter levels and composition

Adapters are owner boundaries, not generic configuration fragments. Four roles
exist:

| Role | Level | Responsibilities |
|---|---|---|
| `task` | Task/backlog owner | Read and update one task, classify impact, own G0 coordination and final handoff |
| `implementation` | Repository/runtime owner | Map source/docs/structure, run RED/runtime/security/release gates, own terminal code review |
| `plan` | Planning-set owner | Reconcile evidence, model architecture/impact, validate hierarchy and decomposition, publish and review plans |
| `audit` | Optional publication owner | Publish an explicitly selected terminal report; never own a workflow gate |

A task flow composes `task + implementation` (and optionally `audit`). A plan
flow uses `plan` (and optionally `audit`). Each route names exactly one
`executorAdapter`; other routed adapters contribute authority and capabilities
but do not execute or issue that gate's receipt.

External systems do not redefine ACDD. An adapter maps canonical owner kinds to
its platform, for example Linear `Initiative → Project → Project Milestone →
Issue` or Jira `Initiative → Epic → Version/Release → Story/Task`.

## Plugin mechanics

### Profiles

[`profiles/task/v1.yaml`](profiles/task/v1.yaml) and
[`profiles/plan/v1.yaml`](profiles/plan/v1.yaml) define:

- profile identity and kind;
- capability, adapter, receipt, and routing contracts;
- ordered gates (`id`, `queue`, `name`, `purpose`);
- required capabilities for each gate;
- guidance skill and prompt;
- closure-required gates.

Adapters may strengthen a gate but cannot remove or reorder profile gates.

### Capability contracts

[`contracts/task/v1.yaml`](contracts/task/v1.yaml) and
[`contracts/plan/v1.yaml`](contracts/plan/v1.yaml) define every capability and
which adapter role must provide it. Validation fails when selected adapters do
not cover the exact capabilities required by a routed gate.

### Routing

[`routing/task/v1.yaml`](routing/task/v1.yaml) and
[`routing/plan/v1.yaml`](routing/plan/v1.yaml) bind each gate to:

- participating adapter roles;
- one `executorAdapter`;
- the semantic receipt expected from the gate.

Routing separates “contributes context” from “may execute and issue evidence.”

### Adapter contract and parameters

Every adapter follows [`contracts/adapter/v1.yaml`](contracts/adapter/v1.yaml).
Required fields:

| Field | Meaning |
|---|---|
| `apiVersion`, `kind` | `acdd/adapter/v1`, `adapter` |
| `id` | Stable owner-specific adapter identifier |
| `role` | `task`, `implementation`, `plan`, or `audit` |
| `provides` | Exact implemented capabilities for that role |
| `procedure` | Inline steps or adapter-relative procedure path(s) |
| `authority` | Owner paths, commands, evidence sources, mappings, and impact axes |
| `constraints` | Fail-closed local invariants |

Optional fields:

| Field | Meaning |
|---|---|
| `availability` | Runtime prerequisites and availability conditions |
| `gateProcedures` | Gate-specific operation, launcher, discovery, review, and tool policy |
| `resources` / `scripts` | Adapter-relative contracts, templates, or executables |
| `externalMappings` | Projection to Linear, Jira, or another owner system |
| `inputAuthorities` | Allowed glob patterns for each typed input class |
| `writePolicy` | Additional allow/deny rules and explicit protected-write exceptions |
| `receipts` | Owner-specific receipt storage/closure details |
| `skillExtensions` | Additional owner procedures layered onto profile guidance |

All procedure, resource, and script paths resolve relative to the adapter file
and must remain inside the allowed workspace authority.

### Gate procedures and launchers

An independently executed gate binds a concrete launcher:

```yaml
gateProcedures:
  architecture/v1:
    operation: architecture-verify
    runtime: pi                    # provenance only
    launcher:
      kind: command                # command or tool
      target: pi                   # actual executable/tool
      arguments: [--print, "{prompt}"]
      promptTransport: final-argument
    toolEnvelope:
      admit: [read, grep, find]
      deny: [bash, edit, write]
```

`runtime` is never treated as a command or tool. `launcher.target` is the actual
thing invoked. A command launcher uses the host command executor; a tool
launcher invokes the exact bound tool. The envelope may list only tools truly
available inside that launched session.

Task architecture adapters also bind concrete discovery methods for
`exactText`, `structural`, and `dependency`, plus any concrete verification
contract, command CWD, model, scope, and session-count restriction.

### Input authority and write policy

Bound documents declare typed workspace-relative inputs:

- `source`
- `test`
- `configuration`
- `generated`
- `dependency`
- `environment`
- `accepted-review-findings`

Each path must match at least one supplied adapter's `inputAuthorities` pattern.
The default write policy permits ordinary paths but protects `.agents/**` and
all `AGENTS.md` files. A protected write requires both a narrowly scoped
`protectedAllow` rule and an explicit user request. Deny rules always win.

### Evidence, receipts, and invalidation

The bound task or primary plan stores:

- `## ACDD inputs` — typed paths;
- `## ACDD gate evidence` — bounded `basis`, `command`, `proof-bundle`, `review`, `handoff`, or
  `rationale` evidence;
- an ordered receipt table;
- explicit blockers.

Receipt contracts define terminal statuses, evidence mode (`basis`, `snapshot`,
or `live`), invalidating input classes, fingerprint format, and timestamp
format. The validator computes the canonical snapshot and semantic fingerprint
in memory; it does not write input manifests or raw review transcripts.

### Architecture verification

[`contracts/architecture-verification/v1.yaml`](contracts/architecture-verification/v1.yaml)
requires isolation, read-only execution, a shared input fingerprint, complete
partition coverage, finding reconciliation, persisted-contract reconciliation,
and exactly one authoritative coordinator session. Inspector output cannot
contain a receipt or verdict.

### Skills

[`skills/acdd-task/`](skills/acdd-task/) and
[`skills/acdd-plan/`](skills/acdd-plan/) contain the canonical agent procedures.
A profile references a skill by name; an owner adapter can add local details but
cannot weaken profile gates. `--settings` can verify that skill resolution is
unambiguous.

### Validators

- `scripts/validate_acdd.py` validates profile composition, adapters,
  capabilities, routing, input authority, the bound document, evidence,
  fingerprints, and receipts.
- `scripts/check_simple_plan.py` validates the optional
  [`acdd/plan/simple/v1`](contracts/plan/simple/v1.yaml) shape.
- `scripts/check_markdown_links.py` validates repository-local documentation
  links.
- `scripts/architecture_verification.py`, `acdd_document.py`,
  `acdd_fingerprint.py`, and `value_domains.py` implement the verification,
  parsing, hashing, and domain-propagation primitives used by the validator.

### Examples

[`examples/README.md`](examples/README.md) indexes every copyable owner adapter
and document. Examples are executable contracts tested by this repository, not
illustrative pseudocode.

## Verify this plugin

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
