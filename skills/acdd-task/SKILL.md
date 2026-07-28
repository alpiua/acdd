---
name: acdd-task
description: Execute one bound implementation task through acdd/task/v1 with explicit task and implementation adapters.
---

# ACDD Task

Use one bound task and its explicit task and implementation adapters.

```text
bind → G0 architecture → red proof → implement → proof bundle → review → handoff
```

## Route

1. First, resolve its relative path from the adapter file's directory, verify that the resolved target exists, and use it. Never reinterpret it from the session working directory after a search/glob miss.
2. Select the next profile gate; treat `runtime` as provenance only. Never search for or invoke it as a tool; invoke the adapter-declared `launcher.target`.
3. Record impact on every adapter-required axis. Keep task evidence in the task; keep G1 attempts, telemetry, and transcripts in adapter-owned runtime artifacts.

## G0 and G1

- Freeze the complete G0 authority before verification. Run the owner `verify` wrapper once; it performs preflight, admission, one frozen manifest, four independent inspectors, then a tool-free coordinator.
- Inspectors review task authority plus bounded code evidence. The coordinator reconciles validated partitions and owns the recommendation batch.
- A terminal PASS requires a complete validated wave and unchanged frozen inputs. Preserve completed partition findings on BLOCKED.
- Treat substantive FAIL content as remediation input. Change the semantic candidate before another launch; never rerun an unchanged FAIL fingerprint.
- Keep G0 immutable after PASS. Put later design changes in a complete G1 amendment, bind it to G0, and verify only that amendment with its own declared manifest.

## Completion

- Implement only a passed candidate, retain red proof, record proof through `record_proof.py`, compute invalidation after accepted changes, and run review/v1 through the implementation adapter.
- A receipt is current only while its declared inputs are current. Record blockers honestly and close only with current terminal evidence.
- After a selected terminal report, execute the profile-bound
  `workflowLearningContract` and project its validated record through the audit
  adapter.

Use [architecture](references/architecture.md), [receipts](references/receipts.md),
[workflow learning](references/learning.md), and
[value domains](references/value-domains.md) for gate schemas and propagation
rules.
