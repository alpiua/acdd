---
name: diagnose
description: "Use for bugs, tracebacks, test failures, or regressions: reproduce, isolate root cause, fix without guessing."
---

# Diagnose

**Leading word:** root cause.

Stop implementation guessing. Gather evidence, one hypothesis, minimal fix.

## 1. Evidence

1. Read the full traceback or failure output.
2. Open the raising file:line and its direct callers.
3. Note boundary crossed (API, config, storage, auth, parse).
4. Structural inventory with ast-grep/search for the failing symbol if impact is unclear.

## 2. Hypothesis and reproduction

1. Form **one** concrete root-cause hypothesis (not a symptom patch list).
2. Add or run a minimal reproduction (targeted test or isolated command).
3. Confirm it fails the expected way before editing production code.

## 3. Fix and verify

1. Fix the root cause at the owning boundary — not a local shim over the symptom.
2. Re-run the reproduction until green.
3. Widen checks: lint/type if touched, then the nearest suite for the area.
4. If three fix attempts fail: stop and escalate with traceback, attempts, and current hypothesis.

## Done

- Root cause fixed and verified by reproduction
- No known regression in the widened checks
- Handoff states cause, change, and verification

## Domain extension

Load the selected ContextUnity adapter's `skillExtensions.diagnose` entry for local
commands, symptom tables, and evidence sources. It may add diagnosis evidence;
it cannot replace root-cause reproduction or weaken the widened check.
