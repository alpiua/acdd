---
name: tdd
description: "Use for Red-Green-Refactor while writing or changing tests and production code."
---

# TDD

**Leading word:** Red-Green-Refactor. **Honest green** only for what the suite proved.

## Architecture note

A green unit test alone is not a finished product feature. Prefer tests that
exercise the real call path for the behavior under change. Product definition of
done, if any, stays in the owning project — not here.

## Loop

### 1. Red

1. Name the behavior and fail-closed cases that matter.
2. Write the smallest failing test.
3. Run it; confirm failure mode is the intended one.

### 2. Green

1. Implement the minimal production change that makes the test pass.
2. Avoid drive-by refactors in the green step.

### 3. Refactor

1. Clean structure only while tests stay green.
2. Behavior-preserving splits: move ownership/imports, do not rewrite bodies in
   the same commit as a structural move.
3. Any behavior change → new red cycle.

### 4. Widen

1. Re-run the focused file/area.
2. Run the project’s broader gate before handoff when the change is non-trivial.

## Done

- Red observed, green verified, refactor still green
- Fail-closed paths covered when the behavior has a gate/deny path
- Claims match the suite that actually ran

## Domain extension

Load the selected ContextUnity adapter's `skillExtensions.tdd` entry before choosing a
test lane or command. It may add required paths, fixtures, or evidence fields;
it cannot replace red-green-refactor or waive an observed red proof.
