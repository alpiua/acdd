---
name: tdd
description: "Use for Red-Green-Refactor while writing or changing tests and production code, including fixes for accepted review findings."
---

# TDD

**Leading word:** Red-Green-Refactor. **Honest green** only for what the suite proved.

## Architecture note

A green unit test alone is not a finished product feature. Prefer tests that
exercise the real call path for the behavior under change. Product definition of
done, if any, stays in the owning project — not here.

Isolated helper coverage is characterization only. Done requires a
production-path regression through the real composition root and every stage the
invariant crosses. Before Red, fill
`plan/contract invariant → canonical owner → production consumer → persisted
evidence → boundary regression`. Reject or rewrite tests that lock in
plan-forbidden or contract-forbidden behavior.

## Loop

### 1. Red

1. Name the post-fix invariant and forbidden effects.
2. Name one plausible production mutation that would violate the invariant and
   that the regression must kill.
3. For a review finding, reproduce its reachable failure at the owning boundary.
   If production was already changed, temporarily apply the named mutation and
   observe the regression fail for the intended reason before restoring Green.
4. Assert the externally observable contract and forbidden effects. Do not use a
   tautology, source-text assertion, private call count, mock-only wiring check,
   timing poll, or broad output substring as the sole proof of behavior.
5. Match the fixture to the claim: use a real composition root for wiring, real
   persistence for transaction/durability, deterministic synchronization for
   concurrency/lifecycle, and exact below/at/over cases for bounds.
6. Add cases for each affected path, backend, authority mode, or compatibility
   surface that could violate the same invariant; mark absent dimensions `N/A`.
7. For multi-stage invariants, add one seam case through
   `command or entry → persisted or compiled state → downstream consumer →
   restart when durability is claimed`. Helper-only gate or repairer tests do not
   replace that seam.
8. For check-then-mutate races, interleave the conflicting mutation between the
   real check and the real mutate.
9. Run the smallest failing set and confirm each intended failure.

### 2. Green

1. Implement the smallest change at the canonical owner that satisfies the
   invariant across the declared dimensions.
2. Keep unrelated refactors out of the green step.
3. Do not leave a second error boundary unset while fixing only the local
   symptom; selection and invocation, parse and consume, write and read must
   share one restored invariant when the contract spans them.

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
- Named mutation is killed by the regression
- Traceability row is complete for the changed invariant
- Production-path or seam evidence exists when the invariant crosses stages
- The test would still fail if the implementation merely returned or called the
  expected shape without restoring the owning invariant
- No accepted test expects plan-forbidden or contract-forbidden behavior
- Fail-closed paths covered when the behavior has a gate/deny path
- Claims match the suite that actually ran

## Domain extension

Load the selected ContextUnity adapter's `skillExtensions.tdd` entry before choosing a
test lane or command. It may add required paths, fixtures, or evidence fields;
it cannot replace red-green-refactor or waive an observed red proof,
production-path seam, or traceability row.
