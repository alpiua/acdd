---
name: acdd-decompose
description: Prepare the decompose/v1 ACDD planning gate.
---

# decompose/v1

## Load

Read the planning document, `acdd/plan/v1` profile, Plan adapter, and
`contract-verify` adapter. Load only the current check section, then append its
`promptAppend` fragment if present.

## decomposition

Prove every planning change belongs to one bounded subtask and each dependency
is explicit. Do not assign overlapping planning work without ordering.

## matrix

Classify planning artifacts, owners, consumers, reads, writes, dependencies, and
affected paths. Record basis references covering the declared scope.

## contract-verify

Run through the `contract-verify` adapter (check owner). Substance-check
decomposition and matrix; require parallel-safety. Use the required
nonconformance form. Do **not** grant permission while any `requiredFix` is
open. Register the verify transcript with `acdd review` only after permission.

## Evidence

Record decomposition, matrix, and contract-verify, then finalize only when all
are current.
