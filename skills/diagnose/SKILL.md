---
name: diagnose
description: "Use for bugs, tracebacks, test failures, regressions, or accepted review findings: reproduce, cluster symptoms, isolate root cause, and fix without guessing."
---

# Diagnose

**Leading word:** root cause.

Stop implementation guessing. Gather evidence, one hypothesis per root cause, and the smallest sufficient fix.

Most agent failures are **epistemic** (wrong premise / ignored available evidence),
not missing skill. Before planning a fix, validate the assumption that would
steer the repair against live outputs, Code Map/ast-grep, and the frozen
contract. Do not keep repairing under an unchecked premise.

## 1. Evidence

1. Read the full traceback or failure output.
2. Open the raising file:line and its direct callers.
3. Note boundary crossed (API, config, storage, auth, parse).
4. Structural inventory with ast-grep/search for the failing symbol if impact is unclear.
5. For a review transcript, use the Review row's partial or blocked note to
   open its JSONL, then read every review_raw response before interpreting the
   terminal. Raw output need not follow a schema: it remains unresolved input
   until confirmation or diagnosis evaluates it, never an empty finding set.

## 2. Closure map and Red

1. Cluster symptoms or findings that share a first violated invariant and owner.
2. Classify each review claim from the reviewed snapshot and source evidence:
   introduced-regression, pre-existing-missed, incomplete-remediation, duplicate,
   invalid, or plan-deferred. Do not classify by reviewer wording alone.
3. For each independent cluster, write: reachable scenario → canonical owner →
   post-fix invariant → forbidden effects → affected dimensions → regression.
4. Fill
   `plan/contract invariant → canonical owner → production consumer → persisted
   evidence → boundary regression` before editing. Missing cells block the fix.
5. If the governing decision does not already fix a public, persisted, security,
   concurrency, migration, multi-backend, or compatibility boundary, stop for a
   user decision before editing.
6. If Contract already passed, compare the work with its source contract. A new
   scope is a new subtask and part-and-binding pair, never an edited one.
7. Add or run the minimal reproduction and confirm the expected failure before
   editing production code. Prefer a production-path seam over an isolated
   helper when the defect crosses stages. Reject regressions that stay green
   while the owning invariant is false or that expect plan-forbidden behavior.

## 3. Fix and verify

1. Fix each root cause at its owning boundary. Restore every spanned error
   boundary; a local symptom patch is incomplete remediation.
2. Re-run every cluster reproduction until green.
3. Verify affected callers, paths, backends, authority modes, and compatibility
   surfaces; scan for obsolete behavior.
4. Run lint/type checks when touched, then the nearest owning suite.
5. If three fix attempts fail **or** two attempts still rest on the same
   unvalidated premise, stop: rediagnose (fresh evidence), append a replacement
   subtask via `contract-subtask` when scope must change (never reopen after
   freeze), or escalate. Do not invent pass receipts or extend a
   thin `*-repair` to green the validator.

## Done

- Root cause fixed and verified by reproduction
- Traceability row and production-path evidence complete for each cluster
- No known regression in the widened checks
- Handoff states cause, change, and verification

## ACDD context

Use the current owner adapter and bound `promptAppend` for repository-local
commands and evidence. They may add context, never replace root-cause
reproduction, the closure map, production-path proof, or widened verification.
