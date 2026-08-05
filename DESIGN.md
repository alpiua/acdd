# ACDD workflow design

[README.md](README.md) is the human guide. This document defines the complete
workflow that the validator, profiles, adapters, and gate skills implement.

## Scope

ACDD turns one bounded task or planning change into current, executable
evidence. It does not schedule work, run a review service, or replace a
repository's tests and release process.

The core objects are:

| Object | Purpose |
| --- | --- |
| Document | Markdown record with frontmatter, Plan, Inputs, Evidence, and Receipts. |
| Profile | Ordered gates, checks, evidence kinds, input types, and terminal policy. |
| Subtask | One bounded change slice with scope, acceptance, and dependencies. |
| Adapter | Repository binding for a role's checks, commands, artifacts, and prompt context. |
| Evidence | Checksummed JSONL artifact for one check. |
| Receipt | Current terminal state for one profile gate. |

## Profiles

The task-delivery profile has five global gates and eight checks:

| Gate | Checks | Purpose |
| --- | --- | --- |
| `design/v1` | `design-basis`, `plan-shape` | Freeze intent, boundaries, Inputs, and a bounded Plan. |
| `contract/v1` | `decomposition`, `executable-proof` (includes matrix), `contract-verify` | Freeze subtask scope, matrix+RED proof, then LLM verify before finalize. |
| `build/v1` | `runtime-and-integration` | Implement the scope through TDD and prove the settled tree. |
| `review/v1` | `independent-review` | Code review of completed work across declared review dimensions. |
| `handoff/v1` | `repository-handoff` | Close repository-specific work with current evidence. |

`contract-verify` is owned by the `contract-verify` adapter role (check-level
owner). Task contract-verify dimensions are `completeness`, `chain-coverage`,
`proof-strength`, and `parallel-safety`. The task Code review (`review/v1`)
dimensions remain `parity`, `security`, and `code`.

The planning profile is separate: `design/v1`, `decompose/v1` (with
`decomposition`, `matrix`, and `contract-verify`), and `review/v1` create or
improve a bounded planning set. Plan decompose-verify dimensions are
`completeness`, `chain-coverage`, and `parallel-safety`. Plan Code review
dimensions are `completeness` and `consistency`. It does not implement source
changes.

A receipt table contains exactly the current profile's gate rows in order. A
terminal row requires every earlier gate to be `pass` or `inapplicable`;
`finalize` enforces the same rule.

## Task document and subtasks

The frontmatter selects `planning_profile`. The document then contains:

1. **Plan** — YAML `subtasks`.
2. **Inputs** — declared paths and their types.
3. **Evidence** — checksummed evidence and bundle blocks.
4. **Receipts** — one state row per profile gate.

A subtask is the unit of implementation scope, not a free-form to-do. It has:

| Field | Requirement |
| --- | --- |
| `id` | Unique, non-empty identifier. |
| `writes`, `reads` | A declared Input or a path inside a declared directory Input. |
| `acceptance` | Observable expected result. |
| `dependsOn` | Existing subtask IDs; no self-reference or cycle. |
| `supersedes` | Optional existing subtask ID; a direct, unique replacement link. |

Subtasks whose writes or read/write scopes overlap must be ordered by a direct
or transitive dependency, or by a replacement link. The Plan therefore specifies
which functional behavior each implementation slice may change and how slices
compose without copying a broad Input into every slice.

When Contract passes, the Task adapter creates exactly one source-contract bundle
at `<artifactDir>/<contract-bundle-id>.subtasks.jsonl`; Contract evidence stores
only its relative path. For every current subtask the JSONL has two adjacent,
immutable records: a part and its binding. The part holds the canonical source
digest of its `id`, scope, acceptance, dependencies, replacement link, Contract
fingerprint, and `partSha256`. Its binding names that part and repeats its hash.
The validator recomputes every part hash and requires one matching binding for
exactly one part per current subtask. Thus changing a frozen field makes
validation fail: a subtask cannot quietly become different work during Build.

The JSONL bundle deliberately has no whole-file checksum: legitimate later work
appends a part-and-binding pair. Earlier rows, Contract evidence, and the
Contract receipt are never rewritten. Recomputing a part hash alone does not
authorize a rewritten part because its existing binding still contains the old
hash. Each part must bind the passed Contract receipt.

Later work has two explicit forms. An **addition** is a new subtask with its own
narrow paths and `dependsOn` reference to the work it extends. Its predecessor
must finish its TDD Red → Green before the addition starts; the dependency is the
record of that order. A **replacement** is a new subtask with
`supersedes: predecessor`. The predecessor contract remains immutable and its
superseded state is derived from the successor; nothing is edited or deleted.
Each predecessor has at most one direct successor, and replacement links cannot
cycle.

Until Contract is finalized, Plan subtasks remain editable. Apply
`contract-verify` findings by changing the **same** subtask id in place, then
re-verify. If the change surface looks too large for one subtask, propose an
additional slice and wait for an explicit decision — do not invent parallel
`*-r2` / repair twins or full write-union clones unilaterally.

After finalize, parts are append-only as below. `acdd validate` and a successful
`acdd finalize` of `contract/v1` print a non-fatal **ACDD FREEZE** banner while
that gate remains `pass` (agent soft policy on top of digests/JSONL). Editing
adapter `promptAppend` files after a terminal receipt still stales the gate
fingerprint (`promptDigest`).

Both forms use `acdd contract-subtask` to append their own part-and-binding pair
to the same bundle. The command rejects a duplicate part ID or subtask, and
validation rejects malformed parts or bindings, changed hashes, changed source
fields, missing bindings, or a replacement whose predecessor is not contracted.
Replacement appends that would drop prior active writes fail unless
`--allow-scope-reduction` is set after an explicit product decision. When
`contract/v1` has a review check (`contract-verify`), the Plan's **contract
authority digest** must gain a matching review evidence row before validation
stays green — silent narrowing under a stale verify is rejected. Do not reopen
or rewrite the Contract receipt after freeze.

`acdd record` on `build/v1` always checks the changed write-set: pass
`--changed PATH` and/or run inside a git worktree (dirty porcelain paths). Paths
outside the union of active subtask writes are rejected.

Until `contract/v1` is pass, recording or finalizing evidence fails if product
Inputs (`source`, `configuration`, `generated`, `dependency`, `proto`,
`migration`) are dirty in git. Test Inputs stay allowed for RED proof.

Earlier parts and a still-valid Contract receipt are never rewritten by an
addition or replacement. These are verification records, not subtask gates or
receipts; an addition or replacement does not itself stale Build/Review/Handoff.

## Task-delivery workflow

### 1. Design

`design-basis` describes the intended outcome, reachable scenario, canonical
owner, boundaries, affected callers, non-goals, and forbidden effects.
`plan-shape` validates the Plan and Inputs before implementation begins.

### 2. Contract

`decomposition` assigns every required change to a bounded subtask.
`executable-proof` continues per subtask: matrix content (producers, consumers,
authorities, data flow, backends, reads, writes) plus the pre-change failing
proof, post-fix invariant, forbidden effects, and affected dimensions.
`contract-verify` is an LLM substance check (check owner `contract-verify`) that
must pass with no open corrections before finalize. Failed verify before
finalize is not a freeze: edit the current subtask, re-run verify; propose
splits — do not invent replacement clones alone. Its pass terminal includes a
**Delivery command**: parallel waves and a directive to launch one subagent per
subtask in each ready wave. Tests derived afterward must cover the frozen
contract, not trivia.

The expected failure of `executable-proof` establishes the functional
acceptance boundary. Declare it as a frontmatter **entrypoint** to a real test
path under an Input of type `test` (plus a short `expected_failure` marker).
Do not embed `python -c`, heredocs, or full test listings in the task document.
Contract does not run a TDD iteration itself: Build derives a focused TDD test
from each subtask's frozen scope and acceptance. Prefer catching false premises
(wrong owner/path/backend) during Contract — decisive Build errors usually start
early and stay hidden until recovery is expensive.

### 3. Build

Build carries the frozen Contract into the repository. Prefer one subagent per
subtask following the verify Delivery command waves. Each approved subtask is
a distinct unit of behavior: its acceptance, invariant, and forbidden effects
give its focused functional test a clear subject.

TDD keeps that link honest. Before the production change, the test is **Red**
because the intended behavior is missing or wrong. After the smallest fitting
change, that same test is **Green**. A broken import, fixture, configuration,
or mock-only assertion is not a useful Red, because it says nothing about the
behavior in the Contract. Similarly, a Green result for one subtask does not
prove another subtask's acceptance.

For an additive subtask, complete the predecessor's Red → Green first, then
start the addition's focused Red test. `dependsOn` makes that order reviewable;
it is not a second subtask receipt. When individual behavior tests are green,
`runtime-and-integration` looks at the settled tree as a whole and provides the
repository-level evidence that the completed subtasks still work together.

### 4. Code review

Review (`review/v1`) is external to the core and distinct from `contract-verify`.
The review host selects reviewer sessions, models, and the read-only boundary;
ACDD receives only its JSONL transcript. For `acdd/task/v1`, reviewers receive
the settled Build tree and Contract. For `acdd/plan/v1`, they receive the
settled planning set after Decompose.

Independent reviewers may work in parallel, but one collector writes each
completed response before interpreting it. Every preterminal record is
`review_raw`: only `type`, `reviewerSessionUuid`, and the complete verbatim
`raw` response. Raw may be unstructured and remains available because it can
still contain a finding.

The collector gives the settled input, required dimensions, and all raw records
to a confirmation reviewer. It performs a full review, not a mechanical merge.
The confirmation reviewer is one of the raw sessions and, for pass, issues the
last `review_terminal` record. The collector appends that declaration unchanged;
it must not turn an ordinary response into a pass.

A pass terminal carries its evidence ID, gate, check, `verdict: pass`, author
and reviewer UUIDs, a non-empty `scope`, `performedChecks`, and
`reviewedSessionUuids`. Its reviewer differs from the author.
`reviewedSessionUuids` contains every raw session exactly once, including the
confirmation session, and `performedChecks` covers every profile dimension.
This proves that the confirmation reviewer had to account for the full parallel
set; it does not make the validator a review recommender.

If confirmation finds an issue or cannot cover the scope, retain the raw
transcript and record its relative path and blocker in the Review row as
`partial` or `blocked`. That note is not pass evidence. Diagnose reads raw text
before classifying claims; no schema does not mean no finding.

A host may bridge Pi Review Agents v2 in review-only or full-cycle mode. In a
task profile, a full-cycle fix that changes a Build input must return through
Build before final independent recheck. In a planning profile, repair the
affected Design or Decompose work and recheck the resulting planning set. The
core validates transcript structure and checksum; the consuming workflow
enforces reviewer identity and independent read-only execution.

### 5. Handoff

`repository-handoff` runs the repository's closing proof (command kind).
Finalizing a passed handoff synthesizes `acdd/process-report/1` and attaches it
to the handoff bundle as `processReportRef`. Process metadata is provenance on
the bundle, not a ninth profile check.

## Planning-profile workflow

`acdd/plan/v1` uses the same document shape and evidence lifecycle, but its
scope is a planning set rather than a source change. The Plan adapter performs
Design and Decompose basis/command checks; the contract-verify adapter performs
decompose verify; the Review adapter performs Code review.

1. **Design** records `design-basis` and validates `plan-shape`: the planning
   outcome, boundaries, Inputs, and bounded subtasks. It may be inapplicable
   only with `plan.no-artifact` and no check evidence.
2. **Decompose** records `decomposition`, `matrix`, and `contract-verify`: every
   planning change has a bounded subtask, its documents/owners/dependencies are
   explicit, and an LLM verify pass grants permission to finalize with no open
   corrections.
3. **Code review** (`review/v1`) supplies the independent transcript for
   `completeness` and `consistency` across the settled planning set.

The planning profile has no Contract source bundle, TDD, Build, or Handoff.
A resulting implementation candidate starts a separate task-delivery document.

## Evidence lifecycle

Evidence records the work; it does not replace it. `acdd validate` explains
whether the current document, profile, workspace, and adapters form a valid
state. A completed basis or command check becomes a single JSONL artifact
through `acdd record`; `acdd review` registers the independent transcript
already produced by the consuming workflow and never launches a reviewer.

Finalization gathers the required current check artifacts through the gate's
adapter, validates their joint state, and writes the gate receipt. A subsequent
validation shows whether the complete chain remains current before the next
gate is considered.

Command and basis artifacts contain one terminal record. Command success means
exit code zero; `expected-failure` means a genuine non-zero exit. Timeouts,
execution errors, and exits `124`/`127` never pass. A failed `record` can leave
an orphan artifact but cannot create a receipt.

Artifacts reside in `<adapter dir>/artifacts/`. They remain required while the
task is active. After terminal handoff they may be pruned; the Markdown evidence
block retains the SHA-256 provenance, but the closed document no longer fully
re-validates without those artifacts.

## Adapters and prompt context

An adapter is the repository context in which a role’s checks run and its
artifacts are kept. Its role does not identify a person or team. It binds
`role → gate → check → {cwd, argv, timeoutSeconds?, promptAppend?}`; every
required check for that role has exactly one binding. A check may declare an
`owner` different from the gate owner (check-level owner); fingerprinting and
`record`/`review` resolve the owning adapter per check. Optional
`contractSections` on a gate binding hash named Markdown `#`/`##` section bodies
into the gate fingerprint.

For command and basis checks, `acdd record` runs `argv` without a shell. For
review-kind evidence (`review/v1` or `contract-verify`), the binding is a host
launch template: `acdd review` only validates a supplied transcript.
All cwd, adapter, artifact, and prompt paths stay below the workspace root.

Adapters live under `.acdd/` directories. Discovery is **scoped by document path**
(not a recursive workspace walk):

| Scope | Roots | When |
| --- | --- | --- |
| Single-repo | workspace `.acdd/` | Default: no multi-package `.acdd` roots present |
| Multi-package | sibling packages that already own `.acdd/` | Optional workspace layout; document is not under an opt-in project |
| Project | `projects/<name>/.acdd` | Document under that project **and** `.acdd` present |
| Unused | — | Document under `projects/<name>/` without `.acdd` |

| Adapter type | Typical file | Binds |
| --- | --- | --- |
| **Task** | `.acdd/task.yaml` | Design, Contract (decomposition + executable-proof), Handoff. |
| **Contract-verify** | `.acdd/contract-verify.yaml` | `contract/v1.contract-verify` and/or `decompose/v1.contract-verify`. |
| **Implementation** | `.acdd/implementation.yaml` | Build. |
| **Review** | `.acdd/review.yaml` | Code review (`review/v1`) launch template; transcript via `acdd review`. |
| **Plan** | `.acdd/plan.yaml` | Design and Decompose basis/command checks in the planning profile. |

Create the relevant file with `apiVersion: acdd/adapter/v1`, a stable `id`, its
`role`, and bindings for the listed gates and their exact checks. Its default
artifact directory is `.acdd/artifacts/`. A host builds an agent prompt from the
selected gate skill followed by `promptAppend`; the core fingerprints that
fragment but does not assemble prompts or choose models. For Review, the host
expands its launcher template, creates session UUIDs, collects raw output, and
passes the resulting transcript to `acdd review`. It cannot alter a check or an
invariant.

ACDD discovers `*.yaml` inside `.acdd/` automatically. Nested `.acdd/`
directories remain available for a genuinely nested workspace. During an
invocation, a discovered adapter with no gate in the active profile is ignored;
an adapter that includes an active gate is checked strictly, so an unknown extra
binding still fails validation. `--adapter role=path` is an explicit,
exceptional binding for a single invocation; it also remains confined to the
workspace root.

## Freshness and status

A gate fingerprint binds the profile definition, adapter binding, prompt fragment,
and the inputs selected by that gate's `invalidatesOn`. It deliberately does not
bind the Plan. Source contracts bind subtask fields separately. Separately, the
**contract authority digest** hashes every current (non-superseded) Plan
subtask; when Contract includes a review check, a matching
`authorityDigest` on review evidence is required while `contract/v1` is pass.

Therefore: an addition or replacement may append a part without staling Build
or rewriting the Contract receipt, but must refresh contract-verify against the
new authority digest. Replacement appends that shrink the active write union
fail unless `--allow-scope-reduction` is set. `acdd reopen` is forbidden after
freeze.
A changed source, test,
configuration, generated artifact, dependency, or adapter binding selected by a
gate makes that gate's receipt stale.

While `contract/v1` is `pass`, successful `acdd validate` (and `finalize` of
that gate) emit the **ACDD FREEZE** warning. Exit codes are unchanged; the
banner is agent-facing guidance only.

A stale receipt is invalid state, not another status. Record current evidence and
finalize that same gate to point its receipt at a new bundle. All other validation
must still pass: a stale or invalid later gate is never silently bypassed.

Receipt statuses are `pending`, `partial`, `blocked`, `pass`, and
`inapplicable`; only the last two are terminal, and `inapplicable` needs an
allowed reason with no check evidence.

The validator rejects malformed document shape, missing or duplicate evidence,
stale fingerprints, wrong roles, invalid subtask scope or ordering, dishonest
command outcomes, incomplete review, missing authority verify, and invalid
adapter discovery. These are the invariant groups summarized in [README.md](README.md).

## Boundaries

The core has no extra statuses, gate extensions, scheduler, review runtime, or
per-subtask receipt model. Subtasks have no `status` / `verified` fields yet
(gate Receipts remain the only workflow statuses). The source-contract bundle and its hashed parts are
verification evidence only: they do not give a subtask an independent lifecycle.
Repository-specific commands and execution environments belong to adapters; the
global profile receipts remain the durable workflow state.




