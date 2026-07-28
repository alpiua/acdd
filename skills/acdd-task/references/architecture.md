# Architecture gate

Load only for `architecture/v1`.

Guidance snapshot: `acdd/architecture-guidance/v1`.

## G0 admission governor

Before launching architecture verification, and before an `architecture/v1`
PASS receipt is accepted, admission must hold:

1. **Baseline:** every dirty Git path that is a declared implementation input
   (`source` / `test` / `configuration` / `generated`) is either clean, or listed
   in `## ACDD architecture admission` `candidateSet` with a current sha256 lock.
   Unrelated dirty paths outside those inputs are ignored. Candidate bytes are
   pre-existing candidate-only surfaces — never verified implementation admission.
2. **Unchanged FAIL ban:** do not relaunch when the last architecture attempt is
   `FAIL` and the fingerprint is unchanged (`cannot rerun an unchanged FAIL
   fingerprint`).
3. **Material attempt cap:** default `maxMaterialAttempts: 3` distinct FAIL
   fingerprints. Further new fingerprints are blocked; record `blocked` and stop
   thrash instead of infinite coordinator relaunch.

Check before launch:

```bash
python3 scripts/check_architecture_admission.py \
  --document <task.md> \
  --workspace-root <workspace> \
  --profile profiles/task/v1.yaml \
  --receipt-contract contracts/receipt/task/v1.yaml \
  --adapter task=<task-adapter.yaml> \
  --adapter implementation=<implementation-adapter.yaml>
```

Optional admission section:

```yaml
apiVersion: acdd/architecture-admission/v1
kind: architecture-admission
maxMaterialAttempts: 3
candidateSet:
  - path: path/to/candidate.py
    sha256: sha256:...
attempts:
  - inputFingerprint: sha256:...
    verdict: FAIL
    recordedAt: "2026-07-24T12:00:00Z"
```

An architecture receipt may pass only when every partition reviews the complete
task-scoped code map under the adapter-authorized implementation roots, not only
the diff or one named file. Review the applicable guidance axes below:

1. **`canonical-owner`** — canonical owner and desired end state.
2. **`production-path`** — trigger → caller → contract → owner → consumer across
   every package and service.
3. **`contract-propagation`** — producer, public type, serializer, transport,
   validator, storage/export, reader, and projection.
4. **`authority-identity`** — typed identity, authority owner, required scope,
   and fail-before-I/O behavior.
5. **`lifecycle-failure-rollback-cleanup`** — creation, mutation, terminal state,
   failure, rollback/compensation, cleanup, and concurrent linearization. Name each
   serialization key, winner/loser outcome, reread-after-wait rule, and residue-free
   rollback condition.
6. **`alternate-path-compatibility`** — direct and alternate producers, writers,
   imports, caches, retries, fallbacks, migrations, legacy readers, and removal
   owner.
7. **`persisted-contract-parity`** — acceptance, meaning, shape, and defaults at
   producer → writer → schema/migration → reader → public type across backends.
8. **`impact-scope`** — every adapter-required domain axis is `no` with proof or
   `yes` with owner, propagation, mitigation, authorization, and approved/blocked
   status.
9. **`negative-cross-boundary-proof`** — one named negative or compositional
   proof for every changed invariant. Each proof maps to executable test nodes,
   applicable backends, execution mode (`sequential` or `concurrent`), and exact
   terminal outcomes; a proof ID without that mapping is incomplete.
10. **`contradiction-blockers`** — every unresolved contradiction is a blocker.
11. **`canonical-normalization`** — raw ingress and persisted null/empty/legacy
   values enter one canonical normalizer and either produce a bounded domain
   value or reject before downstream work. Assign wire-shape parsing, domain and
   intra-batch validation, and cross-transaction arbitration to explicit owners;
   boundary-model construction must preserve domain conflicts for typed outcomes.
12. **`authorization-before-selection`** — authorization/scope filtering precedes
   ranking and limiting; selection has a stable tie-break and applicable backend
   parity proof. Test nearer unauthorized candidates against a farther
   authorized result.
13. **`terminal-outcome-truth`** — requested/attempted intent is distinct from the
   terminal effective/applied outcome, including degraded and gate-off paths. A
   batch assigns exactly one terminal outcome to every input position, classifies
   every offender, marks unaffected siblings consistently, and is order-invariant.
14. **`terminal-projection-truth`** — API, telemetry, audit, and evidence
   projections read the terminal effective/applied source of truth rather than
   request or attempt state.

When concurrency, idempotency, revision control, or atomic batches apply, the
proof mapping covers same key with same and different bytes, competing logical
identity, competing expected revision, multiple invalid items plus valid siblings,
input-order permutations, exactly-one mutation, loser reread, and rollback residue.
Use a real concurrent production backend for cross-transaction claims; sequential
replay and an in-process substitute do not prove that behavior.

Add one compact task section:

```md
## Proof obligation mapping

| Proof ID | Boundary | Required scenarios | Execution evidence |
|---|---|---|---|
| `proof.example` | owner boundary | adversarial scenario and exact outcome | test node; backend; mode; observed outcome, or `pending` |
```

Use one row per named proof; group IDs only when boundary, scenarios, and evidence
are identical. `pending` is valid before execution. A terminal `review/v1` or
`handoff/v1` requires every row to contain executable evidence. The validator
checks the table shape, non-empty cells, unique proof IDs, and terminal pending
ban. The implementation reviewer verifies that test nodes exist and that backend,
mode, scenario cardinality, outcomes, and forbidden effects match the claim.

Record the guidance snapshot in the task before G0. Guidance present in that
snapshot shapes its architecture review. Later guidance is an advisory learning
input: record it as `not-in-task-snapshot`, apply it through an authorized G1
amendment when materially relevant, and never invalidate an existing receipt
solely because the workflow learned a new recommendation. An axis may conclude
`N/A` with a task-specific reason and evidence that the boundary is absent.

Before PASS, each reviewer must produce receipts for three capabilities: bounded exact-text search, structural search, and reverse dependency traversal. The executor adapter binds those capabilities to host tools; generic ACDD never names a project tool. One tool may satisfy the dependency capability by itself; adapters must not require a second traversal tool when the bound operation already returns reverse impact. Use the adapter-bound path operation for a bounded dependency chain when the review question requires one. Assigned paths are entry points, not read boundaries. Missing capability, rejected call, unresolved selector, truncation without a widened follow-up query, or unreconciled discovery makes the partition incomplete and forbids PASS. Every partition result must carry typed `discovery.repositoryRoot` and `discovery.methods.{exactText,structural,dependency}` receipts with the canonical capability, actual tools, non-empty queries, and `complete: true`.

The implementation fingerprint is one snapshot of declared files whose resolved
paths are under the allowed `services/`, `packages/`, `core/`, or `extensions/`
roots. For a new task, `## G0 architecture baseline` is the only semantic G0
authority combined with that snapshot. Admission history, receipts, adapters,
runner source, documentation, `.pi*` artifacts, G1 redesign amendments, and
other workflow state do not change the G0 candidate.

After G0 PASS, an implementation-discovered architectural decision is appended
under `## G1 redesign amendments`. Its candidate fingerprint binds only the
amendment authority to the frozen G0 fingerprint. The runner snapshots current
declared allowed-root code selected by that amendment's `implementationPaths`
as review provenance and rechecks it before recording the result. G0 and every
G1 amendment have different coverage manifests and snapshot fingerprints; no
admission inherits another admission's file set. Later implementation edits do
not invalidate a passed amendment.
Run the same four partitions and coordinator with `verify <task> --amendment
<id>`. They review only the amendment and its coherence with G0. A pending
amendment blocks terminal runtime and later receipts; it never resets the G0
matrix or architecture receipt.

```yaml
apiVersion: acdd/architecture-amendments/v2
kind: architecture-amendments
items:
  - id: g1-redesign.example
    baseG0Fingerprint: sha256:...
    rationale: Implementation discovery exposed a missing architectural decision.
    decisions: [Architecturally complete decision actually implemented.]
    coherence: [Preserves named G0 invariants and explains every intentional change.]
    propagation: [caller -> transport -> canonical owner -> storage -> reader -> cleanup]
    implementationPaths: [services/example/path.py]
    proofIds: [proof.example-redesign]
    review:
      status: pending
      receipt: <adapter-owned-receipt-path>
      receiptSha256: pending
      transcript: <adapter-owned-transcript-path>
      transcriptSha256: pending
      inputFingerprint: pending
      recordedAt: pending
```

The task carries amendment authority plus terminal status, artifact paths,
artifact SHA-256 values, the reviewed amendment fingerprint, and timestamp.
The adapter owns one YAML receipt and one paired JSONL transcript per amendment.
Its `architectureArtifacts` backend defines concrete storage, retention, and
redaction. The generic runner only emits typed `prepare`, `launch`, `terminal`,
and `validate` events.

The runner executes this state machine:

```text
fingerprint → preflight → admission → one code snapshot
→ four concurrent inspectors → validate all outputs
→ one tool-free coordinator → recheck inputs
→ terminal PASS/FAIL/BLOCKED → external receipt + transcript digest
```

An owner adapter may build one derived review-context manifest after each
candidate freeze. Bind its G0 or G1 scope ID, selectors, exact covered file
paths, per-file SHA-256 values, and aggregate snapshot fingerprint. Include the
exact declared-input list and bounded live task, phase,
milestone, and linked-plan paths with SHA-256 values. Pass the manifest
explicitly to all inspectors and the coordinator and bind it from runtime
evidence. Graph/vector retrieval may add discovery hints, but retrieved text is
an index result until verified against a listed live authority file.

Inspectors receive read-only task and code access. Code is a feasibility, ownership, caller, and persistence baseline; unfinished legacy implementation is not a G0 defect. A partition `FAIL` is valid only when its finding is a typed `missing-requirement`, `contradiction`, `infeasible-boundary`, `incomplete-propagation`, or `unprovable-acceptance` defect in the frozen task candidate, with task evidence, code evidence, and a required task-authority change. The coordinator compares every source finding with frozen semantic task authority: findings already specified by the task or caused only by unfinished implementation go to `resolvedFindings`; genuine defects become one bounded architectural recommendation batch. Coordinator formatting retries do not rerun inspectors. A schema/transport failure is `BLOCKED`, preserves all completed partition outputs, and does not consume the material FAIL cap.

When a genuine contradiction or gap has multiple materially different valid
interpretations, the coordinator must not choose silently. It marks the
recommendation `userDecisionRequired: true` and supplies both an `update-task:`
option and a `create-linked-plan:` option. The author stops before remediation,
asks the user, and creates/links a plan only when that option is selected.

Launch independent sessions from the executor adapter's `launchers.inspector` and `launchers.coordinator`, never from its `runtime` value. `runtime` records provenance only. The legacy singular `launcher` remains compatible, but a procedure must declare either `launcher` or `launchers`, never both. For a command launcher, verify the concrete target through the host command executor, substitute declared placeholders in its arguments, append the verifier prompt when `promptTransport: final-argument`, and run it from the resolved `commandCwd`.
For a tool launcher in a gate that supports tool transport, invoke the exact
`launcher.target` tool with typed parameters. The host-neutral architecture
runner currently executes command/final-argument launchers; adapters using a
different transport need an executor-specific runner. The coordinator starts
only after all four inspectors terminate with validated outputs and must not
search or call tools. A schema/transport failure is `BLOCKED`; preserve all
completed partitions and bounded redacted raw response content, including plain-text
`FAIL`, without consuming the material FAIL cap. A runtime label in
`toolEnvelope` is a contract error.
The concrete executor, transport, concurrency limit, and model selection are
adapter policy; none is a universal ACDD runtime assumption.
`discovery.repositoryRoot` identifies the root visible to the launcher process.
When `commandCwd: implementation-repository` is selected, it is the
implementation repository root; the adapter `pathContract` binds that root to
workspace and repository-relative coverage paths.

For each persisted contract, use the task's `Persisted contract propagation` matrix. The contract and persistence partitions must independently map every contract ID, and the coordinator must reconcile contract definitions and file dispositions. Any restriction, reinterpretation, or removal of previously persisted acceptance or meaning forbids PASS without an explicit backfill, compatibility bridge, or fail-closed preflight and executable proof. Tests through helper, mock, parity-only, or legacy APIs do not prove the canonical production reader.

Classify the solution:

- **canonical** — implements the desired owner and removes invalid states;
- **migration-compatible** — temporarily bridges to the canonical owner, with a linked removal condition and a failure it must not hide;
- **blocked** — the canonical owner or safe migration cannot yet be determined.

A schema, helper, compatibility alias, test-only caller, or reviewer-authored prose is not a production path. A review finding may expose impact but cannot authorize expanding the task into another impact domain; authorization must come from the bound task/plan owner or an explicit user decision. Deployment rollout and rollback are required only when the selected adapter declares deployment as an affected axis. The reviewer must be independent of the task author and must return PASS or FAIL with exact evidence.
