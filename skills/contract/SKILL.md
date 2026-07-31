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

For every reachable defect, record the canonical owner, post-fix invariant,
forbidden effects, affected dimensions, and a focused regression that fails on
the pre-change tree. Its bound command must have the profile’s expected outcome.

## Evidence

Record both basis checks and the proof command, then finalize the owner receipt.
