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

## executable-proof

Continue from decomposition per subtask: include matrix content (producers,
consumers, owners, reads, writes, backends, authorities) and the focused RED
proof. Record reachable scenario, canonical owner, post-fix invariant,
forbidden effects, affected dimensions, and a regression that fails on the
pre-change tree. The bound command must have the profile’s expected-failure
outcome. Tests must cover the frozen contract, not trivia.

## contract-verify

Run through the `contract-verify` adapter (check owner). Resolve its
`promptAppend`. Substance-check decomposition, matrix+RED, and parallel-safety.
Use the required nonconformance form. Do **not** grant permission while any
`requiredFix` is open. Register the verify transcript with `acdd review` only
after permission with no open corrections. On pass, the verifier's **Delivery
command** names parallel waves; after finalize, launch **one subagent per
subtask** in each ready wave (see Build skill).

## Evidence

Record decomposition, executable-proof, and contract-verify, then finalize.
Finalization creates one append-only source-contract bundle with a separately
hashed part and matching binding for every current subtask. Do not edit those
subtasks during Build.
For newly discovered work, add a new subtask: use `dependsOn` to extend
completed work with narrower paths under a shared Input, or use `supersedes` to
replace one existing subtask. Preserve the old subtask in both cases and use
`acdd contract-subtask` through the Task adapter to append its part-and-binding
pair before it joins Build.
