---
name: acdd-v2-decompose
description: Prepare the decompose/v1 ACDD planning gate.
---

# decompose/v1

## Load

Read the planning document, `acdd/plan/v1` profile, and Plan adapter. Load only
the current check section, then append its `promptAppend` fragment if present.

## decomposition

Prove every planning change belongs to one bounded subtask and each dependency
is explicit. Do not assign overlapping planning work without ordering.

## matrix

Classify planning artifacts, owners, consumers, reads, writes, dependencies, and
affected paths. Record basis references covering the declared scope.

## Evidence

Record both basis checks and finalize only when both are current.
