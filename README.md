# ACDD

ACDD means **Architecture Contract-Driven Development**. It turns an intended
change into a bounded architecture contract, checks that contract against the
live system, implements only the approved scope, and closes with current
executable evidence. It connects existing tests, release processes, issue
trackers, and review tools through profiles and repository adapters.

ACDD provides a task-delivery profile and a smaller planning profile. This
guide focuses task delivery: one Markdown task document, one profile, physical
evidence artifacts, and a validator. It is not a scheduler, review runtime, or
agent orchestrator.

## Task delivery: 5 gates, 8 checks

Gates run in order. A gate may finalize or validate as terminal only when every
earlier gate is already pass or inapplicable.

The gates form one evidence chain: decide what is safe to change, freeze the
required behavior and proof obligations, implement with TDD, challenge the
settled change independently, then close it with current evidence.

### 1. Design

Define the intended outcome, architecture boundary, and a bounded plan before
implementation begins.

- **design-basis** — explains what will change, why it matters, which systems
  and callers are affected, and which effects must never occur.
- **plan-shape** — turns that decision into small, ordered subtasks with
  explicit reads, writes, acceptance criteria, and dependencies.

### 2. Contract

Turn the approved design and its subtasks into a stable behavior and proof
contract. Finalizing this gate creates one append-only source-contract bundle.
Each current subtask has a checksummed part and matching binding, so changing a
part and recomputing only its self-hash is rejected during Build.

- **decomposition** — shows that every required change belongs to one bounded
  subtask and that dependent work has a clear order.
- **matrix** — maps the affected producers, consumers, data flow, authorities,
  backends, reads, and writes so no relevant path is implicit.
- **executable-proof** — establishes a focused pre-change proof of the
  unresolved behavior, plus the post-fix invariant, affected dimensions, and
  forbidden effects. Its expected failure fixes the acceptance boundary and
  supplies the scope for Build's TDD test; it is not the TDD cycle itself.

### Subtasks: the unit of implementation

A subtask is one bounded change slice, not a to-do item. Its writes and reads
name either a declared Input or a path inside a declared directory Input. That
lets several subtasks share `src` without repeating it, while each still names
the files it changes. Its acceptance describes an observable result, and
dependsOn makes execution order explicit. IDs are unique, dependencies are
acyclic, and conflicting reads/writes must be serialized.

At the end of Contract, every existing subtask receives an immutable part and a
matching binding in one source-contract bundle. A part captures its scope,
acceptance, dependencies, replacement link, and its own hash; its binding
repeats that hash under the part ID. Changing a part and recomputing only its
self-hash is still rejected because its existing binding no longer matches. A
later subtask is always new work, never an edit to an old part:

- **Addition** narrows or extends the work with its own paths and a dependsOn
  link to the original. Finish the original subtask's TDD Red → Green before
  starting the addition's Red test.
- **Replacement** uses supersedes. The original contract remains in the record,
  but its state is now derived as superseded by that one successor. A subtask
  has at most one direct replacement.

Register either form with `acdd contract-subtask` before it joins Build. The
command appends a separately hashed part and its binding to the same
source-contract bundle; it never edits an earlier part, Contract evidence, or
receipt. Source contracts are verification records, not subtask gates or
subtask receipts. A Plan-only addition or replacement does not stale a global
Build, Review, or Handoff receipt; changing that receipt's actual inputs still
does.

### 3. Build

Build carries the frozen Contract into source code. Every approved subtask has a
small TDD loop around the behavior it changes. A focused automated test comes
from that subtask's acceptance and forbidden effects, and runs before its
production change. **Red** means that the real functional outcome is absent or
wrong—not that setup, imports, mocks, or an unrelated assertion failed. The
smallest change then makes that same test **Green**. A passing test for one
subtask never proves another subtask's acceptance.

- **runtime-and-integration** — runs the repository's integrated command after
  the focused tests are green. It demonstrates the intended runtime behavior
  and the relevant integration or quality guarantees on the settled tree.

### 4. Review

Challenge the settled change across the task profile's parity, security, and
code dimensions. The planning profile instead checks its settled set for
completeness and consistency.

- **independent-review** — registers an external transcript. The review host
  selects the independent read-only sessions; it retains each response as raw
  JSONL, even when it has no schema. A confirmation reviewer reads the settled
  input and all raw output, then issues the final pass terminal. The collector
  records that declaration; it does not decide pass itself.

### 5. Handoff

Close the repository-specific work only after all prior evidence is current and
terminal.

- **repository-handoff** — confirms required closure actions, changed derived
  artifacts, and the absence of unresolved blockers. Finalize also writes a
  process report onto the handoff bundle for provenance.

## Planning profile

The planning profile creates or improves a bounded planning set. It never
implements source changes.

| Gate | Checks | Purpose |
| --- | --- | --- |
| Design | design-basis, plan-shape | Freeze the planning outcome, boundaries, Inputs, and bounded Plan. May be inapplicable only as plan.no-artifact. |
| Decompose | decomposition, matrix | Make the planning set coherent and bounded. |
| Review | independent-review | Challenge the settled set for completeness and consistency. |

Use the Plan and Review adapters described below. See the
[plan example](acdd/share/examples/plan-example.md).

## 11 invariants: what the validator refuses

1. **Shape** — receipt rows are exactly the profile gates, ordered, with
   coherent pending values; a declared planning profile must match; terminal
   rows require every earlier gate terminal. A sixth note cell is allowed only
   on partial or blocked rows.
2. **Evidence is real** — artifacts are local, checksummed, unique,
   single-record, and pass their declared outcome; basis evidence covers its
   scope; review terminals carry verdict pass; a passed handoff bundle carries
   a process report. Every Contract source part must have one matching binding
   in the same bundle.
3. **Receipt binds evidence** — receipt, bundle, and check fingerprints agree.
4. **Receipt binds state** — a receipt binds the gate's profile definition,
   adapter bindings, prompt fragment, and relevant inputs. It does not bind the
   Plan: adding or replacing a subtask alone leaves global receipts current. A
   stale receipt is renewed only by current evidence for that same gate; any
   other stale or invalid state still blocks finalization.
5. **Authority** — the bundle/check issuer is the gate owner, and the adapter
   binds exactly that gate's checks.
6. **Sub-task bounded** — IDs, paths inside declared Inputs, acceptance,
   dependencies, replacements, and write/read conflicts are valid and explicit.
   Every subtask after Contract has one separately hashed part and matching
   binding in the Contract source bundle; it cannot change silently, and exactly
   one successor may supersede it.
7. **Review attested** — review evidence has a pass verdict and distinct valid
   author/reviewer UUIDs that match the transcript terminal; independent
   execution and reviewer identity are outside the core boundary.
8. **Inapplicable reasoned** — a gate-level inapplicable receipt uses an allowed
   reason code and includes no check evidence.
9. **Execution honest** — outcome matches the declared command outcome;
   timeouts, execution errors, and reserved exits 124/127 never pass; basis
   evidence is held to the same honesty.
10. **Discovery authentic** — discovered adapters stay below the workspace root;
    duplicate roles and unknown active-gate bindings fail. A terminal gate also
    needs its one owner adapter with exact check bindings. Adapters with no gate
    in the active profile are ignored.
11. **Review complete** — the review transcript preserves every raw reviewer
    response. Its confirmation reviewer, also a raw session, issues the final
    pass terminal; it acknowledges exactly all raw sessions, declares a
    non-empty scope, and covers the profile's review dimensions.

## Prompts and agent routing

[AGENTS.md](AGENTS.md) routes one active gate to one gate skill under `acdd/share/skills/`.
Load only that check section. Build additionally loads the shared
[TDD procedure](acdd/share/skills/tdd/SKILL.md); [Diagnose](acdd/share/skills/diagnose/SKILL.md) is a
pre-gate helper for a defect or accepted finding, then work returns to its gate.

An adapter may add repository context with promptAppend on a check binding:

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

The fragment path is relative to the adapter (conventionally under
`.acdd/prompts/`), must stay below its directory, and its SHA-256 enters the
gate fingerprint. For command and basis checks, cwd stays below the workspace
root and timeoutSeconds (default 300) bounds the command. A review host instead
combines the base review skill and fragment, then expands its launch template.
The core does not compose prompts, choose models, or replace ownership, check
requirements, evidence kind, terminal policy, or an invariant.

Evidence artifacts land in the adapter's artifacts directory (`.acdd/artifacts/`
in a consuming repository). Successful check artifacts are immutable, gitignored
runtime artifacts, required across sessions while the task is active, and
prunable after the handoff gate closes — the committed document keeps every
evidence block with its SHA-256 as provenance. The Contract source bundle is
append-only instead: later subtasks add a hashed part and its binding without
rewriting earlier rows, Contract evidence, or the Contract receipt. A failed
record may leave an orphan JSONL; retrying the same `--id` overwrites it when
that id is not yet in the document.

## Install

```bash
pip install acdd
# or from this repository:
pip install .
```

Bundled profiles ship inside the package. After install you can pass an alias
(`task`, `plan`, `acdd/task/v1`, `acdd/plan/v1`) instead of a file path.

## Commands

Adapters load from the discovery scope below (not a recursive walk of every
`.acdd/` under the workspace). Every adapter YAML with
`apiVersion: acdd/adapter/v1` directly inside a selected `.acdd/` root is
considered. An adapter with no gate in the active profile is ignored; one that
declares an active gate is indexed by role and checked strictly, including
unknown bindings. Symlinked adapter files are ignored. `--adapter role=path`
overrides a discovered entry and must also resolve below the workspace root.

```bash
# Single-repo: put adapters under .acdd/ at the workspace root.
# Profile may be a path or a bundled alias (task / plan).
uv run acdd validate task.md task

uv run acdd fingerprint task.md task --gate build/v1

uv run acdd record task.md task \
  --gate build/v1 --check runtime-and-integration --id build.runtime

# Basis evidence needs classified coverage for every input selected by its gate.
uv run acdd record task.md task \
  --gate design/v1 --check design-basis --id design.basis \
  --classified-ref docs/design.md=task

uv run acdd finalize task.md task --gate build/v1 --id build.bundle

uv run acdd contract-subtask task.md task --workspace-root . \
  --subtask newly-discovered-slice --id contract.newly-discovered-slice

uv run acdd review task.md task \
  --gate review/v1 --check independent-review --id review.independent \
  --transcript .acdd/artifacts/review.jsonl \
  --author-uuid <AUTHOR_UUID> --reviewer-uuid <REVIEWER_UUID>

# Only where the selected profile permits it.
uv run acdd finalize task.md task --gate build/v1 \
  --id build.inapplicable --status inapplicable \
  --reason-code build.no-runnable-source
```

`acdd review` registers an existing adapter-bound transcript relative to
`--workspace-root`. It validates raw-response preservation, confirmation
acknowledgement, scope, required dimensions, pass terminal, and UUID values. It
does not launch reviewers, choose models, or authenticate identity; the
consuming workflow owns those guarantees. See [DESIGN.md](DESIGN.md) for the
host contract and review-host boundary.

## Install adapters

Adapters are YAML files under `.acdd/` with `apiVersion: acdd/adapter/v1`.

**Discovery scope** (from the document path under `--workspace-root`):

1. **Single-repo (default)** — load `.acdd/` at the workspace root.
2. **Project opt-in** — a document under `projects/<name>/` with a local
   `.acdd/` uses only that project.
3. **Unused project** — a document under `projects/<name>/` without `.acdd/`
   means ACDD is not used for that document.
4. **Multi-package workspace** — when sibling packages already own `.acdd/`,
   discovery may load those package roots instead of walking the tree. Details
   are in [DESIGN.md](DESIGN.md#adapters-and-prompt-context).

Task delivery needs roles task, implementation, and review. Planning needs plan
and review. A Review binding is a host launch template; register the finished
transcript with `acdd review`. Handoff records repository-handoff; finalize
writes the process report onto that gate's bundle.
