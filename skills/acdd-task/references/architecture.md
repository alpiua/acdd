# Architecture gate

Load only for `architecture/v1`.

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

An architecture receipt may pass only when every partition reviews the complete task-scoped code map under the adapter-authorized implementation roots, not only the diff or one named file, and the proposed slice identifies:

1. the canonical owner and desired end state;
2. the production trigger → caller → contract → owner → consumer path across every package and service;
3. contract, identity/authority, lifecycle, failure, rollback, and cleanup seams;
4. direct and alternate producers, writers, schemas/migrations, readers, public types, migration/compatibility paths, and their removal owner;
5. exact persisted acceptance, meaning, shape, and default parity at producer → writer → schema/migration → reader → public type;
6. impact against every adapter-required domain axis: `no` with domains and proof, or `yes` with domains, owner, change, propagation, mitigation, authorization provenance, and approved/blocked status;
7. one named negative or cross-boundary proof for every changed invariant;
8. every unresolved contradiction as a blocker.

Before PASS, each reviewer must produce receipts for three capabilities: bounded exact-text search, structural search, and reverse dependency traversal. The executor adapter binds those capabilities to host tools; `grep`/`ctx_search`, `ast-grep`/`ast_grep_search`, and `code_map_query(operation=impact)` are ContextUnity bindings, not universal tool names. One tool may satisfy the dependency capability by itself; adapters must not require a second traversal tool when the bound operation already returns reverse impact. Use `operation=path` for a bounded dependency chain when the review question requires one. Assigned paths are entry points, not read boundaries. Missing capability, rejected call, unresolved selector, truncation without a widened follow-up query, or unreconciled discovery makes the partition incomplete and forbids PASS. Every partition result must carry typed `discovery.repositoryRoot` and `discovery.methods.{exactText,structural,dependency}` receipts with the canonical capability, actual tools, non-empty queries, and `complete: true`.

The implementation fingerprint is one snapshot of declared files whose resolved paths are under the allowed `services/`, `packages/`, `core/`, or `extensions/` roots. Task semantic sections are combined with that code fingerprint to form the architecture candidate. Admission history, receipts, adapters, runner source, documentation, `.pi*` artifacts, and other workflow state do not change the candidate. A semantic task-authority edit therefore creates a new candidate without requiring a product-code edit.

The runner executes this state machine:

```text
fingerprint → preflight → admission → one code snapshot
→ four concurrent inspectors → validate all outputs
→ one tool-free coordinator → recheck inputs
→ terminal PASS/FAIL/BLOCKED → bounded attempt/evidence
```

Inspectors receive read-only task and code access. Code is a feasibility, ownership, caller, and persistence baseline; unfinished legacy implementation is not a G0 defect. A partition `FAIL` is valid only when its finding is a typed `missing-requirement`, `contradiction`, `infeasible-boundary`, `incomplete-propagation`, or `unprovable-acceptance` defect in the frozen task candidate, with task evidence, code evidence, and a required task-authority change. The coordinator compares every source finding with frozen semantic task authority: findings already specified by the task or caused only by unfinished implementation go to `resolvedFindings`; genuine defects become one bounded architectural recommendation batch. Coordinator formatting retries do not rerun inspectors. A schema/transport failure is `BLOCKED`, preserves all completed partition outputs, and does not consume the material FAIL cap.

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
The Planner adapter currently constrains `architecture/v1` to Pi command
launchers; this is adapter policy, not a universal ACDD runtime assumption.

For each persisted contract, use the task's `Persisted contract propagation` matrix. The contract and persistence partitions must independently map every contract ID, and the coordinator must reconcile contract definitions and file dispositions. Any restriction, reinterpretation, or removal of previously persisted acceptance or meaning forbids PASS without an explicit backfill, compatibility bridge, or fail-closed preflight and executable proof. Tests through helper, mock, parity-only, or legacy APIs do not prove the canonical production reader.

Classify the solution:

- **canonical** — implements the desired owner and removes invalid states;
- **migration-compatible** — temporarily bridges to the canonical owner, with a linked removal condition and a failure it must not hide;
- **blocked** — the canonical owner or safe migration cannot yet be determined.

A schema, helper, compatibility alias, test-only caller, or reviewer-authored prose is not a production path. A review finding may expose impact but cannot authorize expanding the task into another impact domain; authorization must come from the bound task/plan owner or an explicit user decision. Deployment rollout and rollback are required only when the selected adapter declares deployment as an affected axis. The reviewer must be independent of the task author and must return PASS or FAIL with exact evidence.
