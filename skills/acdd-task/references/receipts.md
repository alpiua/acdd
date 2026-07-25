# Task receipt lifecycle

Keep task inputs, gate evidence, fingerprints, receipts, and blockers in the
bound task Markdown.

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

A `proof-bundle` may satisfy multiple live receipts (`runtime/v1`, `parity/v1`,
`security/v1`, `release/v1`) when:

- `claims` lists every covered gate and includes the anchor `gate` field
- every claimed gate shares identical `invalidationInputs`
- each receipt row references the same `evidence=<id>` and current fingerprint
- `commands[]` carries the same fields as command evidence (redacted output)

Ordinary `command` evidence still cannot satisfy more than one receipt.

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
matrix/proof mappings, and bounded findings. Pi transcripts are not copied.

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
