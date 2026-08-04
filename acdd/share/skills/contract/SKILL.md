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

Record decomposition, executable-proof, and contract-verify, then finalize.
Finalization creates one append-only source-contract bundle with a separately
hashed part and matching binding for every current subtask. Do not edit those
subtasks during Build.

For newly discovered work:

- **Additive** (non-overlapping writes + `dependsOn`): `acdd contract-subtask`,
  then re-run `contract-verify` so authority digest matches.
- **Material** (`supersedes`, overlapping writes, or `*repair*`/`*fix*`/`*amend*`
  id): `acdd reopen --gate contract/v1`, amend Plan, re-record Contract checks,
  finalize. Do not shrink writes/acceptance only to green the validator;
  reopen finalize blocks dropped writes unless `--allow-scope-reduction`.
- Do not dirty product Inputs (`source`, …) before `contract/v1` pass; tests
  may change for RED proof.
