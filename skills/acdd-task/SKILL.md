---
name: acdd-task
description: Execute one bound implementation task through acdd/task/v1 with explicit task and implementation adapters.
---

# ACDD Task

Use [`acdd/task/v1`](../../profiles/task/v1.yaml) for one bound task.

1. Supply the task and implementation adapters to `scripts/validate_acdd.py`.
2. Before loading or running any adapter-declared procedure, resource, or
   script, resolve its relative path from the adapter file's directory, verify
   that the resolved target exists and remains inside the adapter authority
   root, and use that resolved target. Never reinterpret it from the session
   working directory or treat a search/glob miss as proof that it is absent.
3. For an independently executed gate, treat `runtime` as provenance only.
   Never search for or invoke it as a tool. Invoke the concrete
   `launcher.target` according to `launcher.kind`, substitute declared argument
   placeholders, deliver the prompt through `launcher.promptTransport`, and
   verify that the target is available before launch.
4. Select the next gate by profile queue and load every routed owner procedure.
5. Record `impact` against the task adapter's required axes, including rollout
   and rollback when deployment is affected.
6. Keep typed inputs, bounded evidence, fingerprints, and one current receipt
   inline in the bound task.
7. Complete `architecture/v1` through its task-executor procedure. Require one
   coordinator, every read-only partition, capability-based PASS validation, and
   a changed fingerprint before any FAIL rerun; repeat until PASS without asking.
   Do not admit the closure-review runtime while this gate is queued.
8. Preserve the frozen `red/v1` command evidence and proof component lock.
9. Run live runtime, parity, security, and release proofs after implementation.
10. Run `review/v1` through the implementation adapter after source, tests,
   configuration, and release evidence settle.
11. Apply accepted findings, rerun affected live gates, and repeat the final
   review against the current fingerprint.
12. Use the audit adapter for a selected final code-review report.
13. Complete handoff with current receipts and empty blockers.

Use [receipt lifecycle](references/receipts.md), the
[architecture contract](references/architecture.md), and the
[persisted contract propagation matrix](references/value-domains.md).
