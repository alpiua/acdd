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
5. For a review transcript, read every raw reviewer response before interpreting
   a terminal. Unstructured raw output remains unresolved input, never an empty
   finding set.

## 2. Closure map and Red

1. Cluster review findings that share a first violated invariant and owner.
2. Classify each claim from source evidence: introduced-regression,
   pre-existing-missed, incomplete-remediation, duplicate, invalid, or
   plan-deferred.
3. For each independent cluster, state one root-cause hypothesis, post-fix
   invariant, forbidden effects, and affected dimensions.
4. Fill
   `plan/contract invariant → canonical owner → production consumer → persisted
   evidence → boundary regression` before editing.
5. Add or run a minimal reproduction for each cluster. Prefer a production-path
   seam over an isolated helper when the defect crosses stages.
6. Confirm the expected failure before editing production code. Reject tests that
   lock in plan-forbidden behavior or stay green while the invariant is false.

## 3. Fix and verify

1. Fix each root cause at its owning boundary. Restore every spanned error
   boundary; a local symptom patch is incomplete remediation.
2. Re-run every cluster reproduction until green.
3. Verify affected callers, paths, backends, authority modes, and compatibility
   surfaces; scan for obsolete behavior.
4. Run lint/type checks when touched, then the nearest owning suite.
5. If three fix attempts fail, stop with evidence, attempts, and the current
   hypothesis.

## Done

- Root cause fixed and verified by reproduction
- Traceability row and production-path evidence complete for each cluster
- No known regression in the widened checks
- Handoff states cause, change, and verification

## Domain extension

Load the selected ContextUnity adapter's `skillExtensions.diagnose` entry for local
commands, symptom tables, and evidence sources. It may add diagnosis evidence;
it cannot replace root-cause reproduction, the traceability row, production-path
proof, or weaken the widened check.
