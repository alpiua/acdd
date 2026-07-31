---
name: diagnose
description: "Use for bugs, tracebacks, test failures, regressions, or accepted review findings: reproduce, cluster symptoms, isolate root cause, and fix without guessing."
---

# Diagnose

**Leading word:** root cause.

Stop implementation guessing. Gather evidence, one hypothesis per root cause, and the smallest sufficient fix.

## 1. Evidence

1. Read the full traceback or failure output.
2. Open the raising file:line and its direct callers.
3. Note boundary crossed (API, config, storage, auth, parse).
4. Structural inventory with ast-grep/search for the failing symbol if impact is unclear.

## 2. Hypothesis and reproduction

1. Cluster review findings that share a first violated invariant and owner.
2. For each independent cluster, state one root-cause hypothesis, post-fix
   invariant, forbidden effects, and affected dimensions.
3. Add or run a minimal reproduction for each cluster.
4. Confirm the expected failure before editing production code.

## 3. Fix and verify

1. Fix each root cause at its owning boundary.
2. Re-run every cluster reproduction until green.
3. Verify affected callers, paths, backends, authority modes, and compatibility
   surfaces; scan for obsolete behavior.
4. Run lint/type checks when touched, then the nearest owning suite.
5. If three fix attempts fail, stop with evidence, attempts, and the current
   hypothesis.

## Done

- Root cause fixed and verified by reproduction
- No known regression in the widened checks
- Handoff states cause, change, and verification

## Domain extension

Load the selected ContextUnity adapter's `skillExtensions.diagnose` entry for local
commands, symptom tables, and evidence sources. It may add diagnosis evidence;
it cannot replace root-cause reproduction or weaken the widened check.
