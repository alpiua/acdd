# Task receipt lifecycle

Keep task inputs, ordinary gate evidence, fingerprints, receipts, and blockers in
the bound task Markdown. G1 amendment runtime attempts and launcher telemetry are
the sole exception: store them in adapter-owned external artifacts referenced by
the amendment.

1. Declare typed workspace-relative paths under `## ACDD inputs` with
   `apiVersion: acdd/inputs/v1`.
2. Record each evidence object under `## ACDD gate evidence` with
   `apiVersion: acdd/gate-evidence/v1` and one of `basis`, `command`,
   `proof-bundle`, `review`, `handoff`, or `rationale`.
3. Reference one evidence object from a nonpending receipt as `evidence=<id>`.
4. Use the gate fingerprint returned by strict validation; do not persist an
   input manifest, spec, component document, or transcript.
5. Return a stale receipt and every successor to `pending`.

Command evidence records the exact command, UTC time, exit code, bounded
redacted output, result, and current fingerprint. A RED command records its
proof-definition fingerprint. When no Git revision is available, it also locks
only the declared source/test/configuration/dependency files used by that proof
as `{path, sha256}`.

Component locks and the recomputed input basis are compared against the working
tree only while the task is in delivery (`status: in_progress|active`). That
comparison answers "must this gate be rerun before closure", so applying it to a
terminal receipt would invalidate landed proofs whenever an unrelated task edits a
shared input. Evidence-to-receipt fingerprint agreement is always enforced.

Receipts have no wall-clock expiry. `recordedAt` records provenance, not a TTL.
The fingerprint, contract revision, and declared inputs determine freshness.
An owner adapter may require a fresh run for volatile external evidence.

The status vocabulary is fixed. `pending` carries no evidence. `blocked` and
`partial` are evidence-bearing non-terminal statuses: a `partial` row records
complete inline evidence for a proven sub-scope, that evidence stays valid
under ordinary successor invalidation, and closure remains blocked until every
gate reaches a terminal status. Unreviewed G1 amendments do not invalidate a
partial receipt.

`review/v1` is never invalidated by `accepted-review-findings`: accepting
findings must not invalidate the review that produced them. A repeat review is
driven by upstream gate reruns through `successorInvalidation` — remediation
edits source or tests, those inputs invalidate the affected proof gates, and
the review reruns as their successor.

Evidence is validated against the contract revision it was issued under, declared
as `contractRevision`. It defaults to the current revision, and a task in delivery
must use the current revision, so a tightened contract cannot be dodged by
declaring an older one. A terminal receipt keeps the revision it was verified
against; back-filling fields a past verifier never emitted would fabricate
evidence, and only a fresh gate run produces current-revision evidence. Revision 1
predates `discoveryComplete`, `persistedContractChange`, and
`persistedContractMappings` on review evidence.

A `proof-bundle` may satisfy multiple live receipts (`runtime/v1`, `parity/v1`,
`security/v1`, `release/v1`) when:

- `claims` lists every covered gate and includes the anchor `gate` field
- the bundle fingerprint is computed over the union of all claimed gate scopes
- each receipt row references the same `evidence=<id>` and current fingerprint
- `commands[]` carries the same fields as command evidence (redacted output)

Ordinary `command` evidence still cannot satisfy more than one receipt.

For `parity/v1` and `security/v1`, terminal `inapplicable` requires command
evidence with `applicability` containing an approved engine, evidence reference,
all adapter impact axes checked, and a closed reason code. The validator rejects
inapplicable when impact includes `security-compliance` or multi-backend storage,
and rejects applicability metadata on a passing receipt.

Gate policies may declare `invalidationClasses`. A tagged input contributes to
that gate only when classes intersect; an untagged input or unknown class is
fail-closed and contributes to every gate selected by its input type. The
`successorInvalidation` graph then expands directly impacted gates to their
ordered downstream dependents. Use `scripts/compute_invalidation.py` to preview
the targeted rerun set; fingerprints remain the final authority.

Prefer `scripts/record_proof.py` to compute the fingerprint, run or capture the
command, redact secrets, and write the evidence plus receipt rows. Single
`--claim` emits `kind: command`; multiple claims emit `kind: proof-bundle`.

Review evidence records the adapter, independent session UUID, author session
UUID, reviewer, terminal verdict, authority sources, production paths,
direct/alternate callers, contradictions, every adapter impact axis,
matrix/proof mappings, and bounded findings. New architecture runner evidence
also records adapter-normalized per-launch and aggregate usage when emitted by
the launcher. Usage transport is adapter-specific; Pi `message_end.message.usage`
is only one supported shape. G1 stores one bounded, secret-redacted JSONL
transcript outside the task and binds its digest from the external amendment
receipt. Temporary partition files are not copied.

`architecture/v1: pass` requires complete inventory and decisions, complete
caller coverage, no unresolved contradiction, all impact axes and matrix/proof
IDs mapped, and valid independent-session provenance.

An active task records `acdd/semantic-fingerprint/v1` over its objective,
execution contract, matrices, decision/proof IDs, RED definition, caller/runtime
and config paths, execution gates, out-of-scope, and blockers. Status, timing,
profile metadata, receipts, evidence, and checkbox state are excluded.

Record profile-only and authorized semantic changes as an inline
`acdd/contract-change/v1` chain. A profile migration preserves the semantic
fingerprint and IDs. A semantic change names rationale, authorization,
before/after fingerprints, and removed IDs, then returns `matrix/v1`,
`architecture/v1`, and every successor to nonterminal state.

For new tasks, `## G0 architecture baseline` is the explicit semantic boundary
and replaces the legacy scattered-section selection. Its fingerprint remains
the G0 receipt authority throughout implementation.

Post-G0 architectural decisions are append-only
`acdd/architecture-amendments/v2` items under
`## G1 redesign amendments`. Each item binds its own authority to the frozen G0
fingerprint and carries terminal status, artifact paths and SHA-256 values,
reviewed amendment fingerprint, and timestamp. The adapter-owned receipt binds
task, amendment, G0, and amendment fingerprints; it holds attempts, verdict,
findings, usage, verification, and the SHA-256 of one paired bounded redacted
JSONL transcript. Editing an amendment
invalidates only that amendment review. Pending amendments block terminal G1+
receipts; they never invalidate the original matrix or architecture receipts.
