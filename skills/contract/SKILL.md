---
name: acdd-contract
description: Prepare the contract/v1 ACDD gate.
---

# contract/v1

## Load

Read the frozen Plan, Inputs, profile, and adapters. Load only the current
check section. Then append the bound `promptAppend` fragment, if present.

## decomposition

Prove every required change belongs to one bounded subtask and each dependency
is explicit. Do not assign overlapping work without ordering.

Before freezing writes/owners, check critical premises against the live tree
(paths exist, owner matches, backend is real). A false premise early becomes an
unrecoverable Build trajectory; catch it here, not after three failed repairs.

## executable-proof

Continue from decomposition per subtask: include matrix content (producers,
consumers, owners, reads, writes, backends, authorities) and the focused RED
proof. Record reachable scenario, canonical owner, post-fix invariant,
forbidden effects, affected dimensions, and a regression that fails on the
pre-change tree. The bound command must have the profile’s expected-failure
outcome. Tests must cover the frozen contract, not trivia.

Declare `executable_proof` in frontmatter as an **entrypoint only**:
`argv` → existing or new test file under an Input of type `test` (e.g.
`pytest path/to/test_….py::test_name`), plus short `expected_failure` marker.
Put the RED test body in that file in the implementation repo. Do **not** embed
`python -c`, heredocs, or full test/source listings in the task frontmatter or
body. Contract does not run a TDD loop; Build derives focused Green work from
the same frozen acceptance.

## contract-verify

Substance-check the **contract package** (Plan, Inputs, matrix, RED claims)
against the **live paths those claims name**. You are not Code review
(`review/v1`).

`chain-coverage` means every subtask names explicit producers/consumers/
authorities/reads/writes/backends **and** those citations are readable in the
implementation tree. Give the verifier read access to both the task document
root and the cited code root(s). Separate git repos are normal.

The adapter argv is a **host launch template**. Create `{reviewerSessionUuid}`
first; ACDD does not invent sessions. Do **not** treat “no single Pi dirty-tree
spanning planner/ + contextunity/” as a contract blocker — mount/read both;
keep git review-workspace to one repo when using Pi code review tools.
Register the finished transcript with `acdd review` (gate `contract/v1`, check
`contract-verify`). Settled Build Code review stays `review/v1` later.

Resolve `promptAppend`. Use the required nonconformance form. Do **not** grant
permission while any `requiredFix` is open. On pass, the verifier's **Delivery
command** names parallel waves; after finalize, launch **one subagent per
subtask** in each ready wave (see Build skill).

## Evidence

### Finalize order (freeze)

1. Finish every document edit that belongs on the PASS snapshot: contract
   section, checklist rows, Gate state, blockers.
2. `acdd validate` green on that exact tree (adapters + `promptAppend` files
   included).
3. Record decomposition, executable-proof, and contract-verify, then
   **finalize**.
4. Stop editing the freeze surface. Finalize is a freeze, not a milestone badge
   before more hygiene patches.

**Freeze surface** includes the gate `contractSections` body, adapter check
bindings (`argv`, cwd, timeouts), and every bound `promptAppend` file
(`promptDigest`). **Do not edit those prompt files** during delivery — not to
harden verify, not to clear a finding, not as “hygiene.” A post-receipt edit to
`prompts/contract-verify-task.md` (or any other binding prompt) changes the
`contract/v1` fingerprint and stales the receipt even when the task markdown
is untouched. Status prose outside `contractSections` does not move the
fingerprint — still do not patch it after finalize; treat the whole task
snapshot as frozen.

Finalization creates one append-only source-contract bundle with a separately
hashed part and matching binding for every current subtask. Do not edit those
subtasks during Build. Do not rewrite earlier parts or the Contract receipt.

Do not dirty product Inputs (`source`, …) before `contract/v1` pass; tests
may change for RED proof.

### Verify ↔ edit order (before Contract finalize)

**Failed verify is not a freeze.** Freeze starts only after `contract/v1`
**finalize** (`pass` + source-contract parts). Do not edit hashed
`promptAppend` files to “teach” this — that stales fingerprints.

Ordered loop for the **current** open subtask `S`:

1. `S` is mutable (Contract not finalized).
2. Verify (or user) findings → **edit the same id `S`** in place
   (writes / reads / acceptance / matrix / dependsOn as needed).
3. Re-run `contract-verify` on the **whole** package.
4. Repeat 2–3 until verify PASS with no open `requiredFix`.
5. Only then: record checks → **finalize** Contract.
6. After finalize, `S` is frozen. New scope → **propose** addition or
   `supersedes` to the user; do not call `contract-subtask` without explicit
   approval. Never clone the full write-union into `S-r2` / `*-repair` to dodge
   an open verify or to “avoid shrink.”
7. If the surface looks too large for one subtask **before** finalize: stop,
   propose a split, wait for a decision — do not invent the split alone.

**One-line rule:** verify fail → edit `S` → verify again; finalize → then
append-only via approved `contract-subtask`.

### After freeze (Build and later)

`acdd validate` prints an **ACDD FREEZE** banner while `contract/v1` is
`pass`. Treat it as authoritative soft policy on top of hard digests/JSONL.

**FORBIDDEN**
- Edit frozen Plan subtask fields in place (writes/reads/acceptance/dependsOn/supersedes)
- Edit the Task execution contract / `contractSections` freeze surface
- Edit adapter `promptAppend` files (stales `promptDigest`)
- `acdd reopen` after Contract freeze
- Silent rewrite of source-contract parts, the Contract receipt, or hashed detail
- Unilateral `*-r2` / full write-union clones

**ONLY for new scope (after explicit user approval)**
- **Addition** (non-overlapping writes + `dependsOn`): `acdd contract-subtask`,
  then re-run `contract-verify` so authority digest matches
- **Replacement** (`supersedes`): `acdd contract-subtask` — append a new part;
  never edit a frozen part. Shrinking the active write union requires
  `--allow-scope-reduction` after an explicit product decision
- Then continue Build within the active write union
