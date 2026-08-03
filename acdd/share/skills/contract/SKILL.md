---
name: acdd-v2-contract
description: Prepare the contract/v1 ACDD gate.
---

# contract/v1

## Load

Read the frozen Plan, Inputs, profile, and task adapter. Load only the current
check section. Then append the bound `promptAppend` fragment, if present.

## decomposition

Prove every required change belongs to one bounded subtask and each dependency
is explicit. Do not assign overlapping work without ordering.

## matrix

Classify producers, consumers, owners, reads, writes, backends, and authorities
in the affected scope. Record basis references covering the declared scope.

## executable-proof

For every reachable defect, record its reachable scenario, canonical owner,
post-fix invariant, forbidden effects, affected dimensions, and a focused
regression that fails on the pre-change tree. Its bound command must have the
profile’s expected outcome.

## Evidence

Record both basis checks and the proof command, then finalize the owner receipt.
Finalization creates one append-only source-contract bundle with a separately
hashed part and matching binding for every current subtask. Do not edit those
subtasks during Build.
For newly discovered work, add a new subtask: use `dependsOn` to extend
completed work with narrower paths under a shared Input, or use `supersedes` to
replace one existing subtask. Preserve the old subtask in both cases and use
`acdd contract-subtask` through the Task adapter to append its part-and-binding
pair before it joins Build.
