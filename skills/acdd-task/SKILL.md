---
name: acdd-task
description: Execute one bound implementation task through acdd/task/v1 with explicit task and implementation adapters.
---

# ACDD Task

Use [`acdd/task/v1`](../../profiles/task/v1.yaml) for one bound task.

## Orchestration Loop

```text
bind → G0 architecture → red proof → implement → proof-bundle → review → handoff
```

## Tool & Discovery Policy (Host-Neutral)

- **Orientation & Code Discovery**: Use host-neutral tools (`lean_ctx_ctx_compose`, `ast-grep`, adapter-declared discovery tools, or targeted searches). Do NOT use unguided `rg`/`cat`/`find` bash scans as primary codebase discovery.
- **Proof Recording**: Prefer `scripts/record_proof.py` to auto-record evidence and proof-bundles instead of manually editing SHA-256 tables.
- **Derived Blocks**: Generate the semantic contract fingerprint with `scripts/record_fingerprint.py`. Never transcribe `sha256`, `ids`, or `redProofFingerprint` by hand; all three are derived from the document's own semantic sections.
- **Shell Usage**: Restrict shell execution to running gate commands, validator scripts, and package tools.

## Execution Steps

1. Supply the task and implementation adapters to `scripts/validate_acdd.py`.
2. Before loading or running any adapter-declared procedure, resource, or script, resolve its relative path from the adapter file's directory, verify that the resolved target exists and remains inside the adapter authority root, and use that resolved target. Never reinterpret it from the session working directory or treat a search/glob miss as proof that it is absent.
3. For an independently executed gate, treat `runtime` as provenance only. Never search for or invoke it as a tool. Invoke the concrete `launcher.target` according to `launcher.kind`, substitute declared argument placeholders, deliver the prompt through `launcher.promptTransport`, and verify that the target is available before launch.
4. Select the next gate by profile queue and load routed owner procedures.
5. Record `impact` against adapter's required axes.
6. Keep typed inputs, bounded evidence, fingerprints, and receipts inline in the bound task.
7. **G0 Architecture**: Freeze one candidate, then invoke the owner wrapper's `verify` operation once. `verify` must prepare the semantic task fingerprint when required and then run the complete local preflight: roadmap drift, ACDD contract validation, and strict bound-task shape validation. It must stop before admission and launch no reviewer when any preflight check fails. After preflight passes, keep the keyword-discovered code map in the task, perform admission, take one frozen snapshot of the declared implementation files under `services/`, `packages/`, `core/`, and `extensions/`, and bind that code fingerprint to the current semantic task fingerprint as one architecture candidate fingerprint. Attempts, admission state, receipts, task frontmatter, adapters, runner code, docs, `.pi*` artifacts, and other workflow state must not affect it; semantic task remediation must create a new G0 candidate without requiring product-code edits. Run four read-only inspectors concurrently, then start one tool-free coordinator only after they finish; the coordinator must reconcile only the supplied validated partitions and must not search or call tools. Before recording any terminal result, recheck the same frozen task/code snapshot manifest and record BLOCKED if it changed; do not create a new candidate or relaunch inside that run. While VERIFYING, do not edit authority. Treat any response containing `FAIL` or a substantive finding as remediation input regardless of serialization shape: reject invalid shape, retry only that inspector, and preserve the finding through the valid retry. Require the coordinator to replace raw inspector advice with one architecturally complete recommendation batch: state each violated invariant and root cause, name the canonical owner boundary, define the required end state and full caller/transport/storage/backend/lifecycle propagation, prohibit symptom-level workarounds, and bind acceptance proof. If the coordinator returns an invalid shape, retry only the coordinator once with its prior FAIL/recommendations and the unchanged validated partitions; never rerun the inspectors for coordinator formatting. Record the valid coordinator-owned batch in the task. If coordinator validation still fails, record a BLOCKED attempt with every bounded inspector finding marked unreconciled instead of discarding them. Then remediate a valid batch in one semantic batch; never copy raw inspector patch advice into task authority or implementation. Create a new candidate and never manually relaunch an unchanged fingerprint. On cap exhaustion or runtime BLOCKED, stop.
   - **Partition failure preservation:** Collect every inspector future independently and wait for the entire wave. If one partition exhausts schema or transport retries, do not run the coordinator and do not discard completed outputs. Record BLOCKED with every validated partition status and bounded finding, plus the failed partition validation error and any substantive FAIL content recoverable from its malformed response.
   - **Pre-implementation review boundary:** Give inspectors read-only access to the frozen task and current code. Treat code as feasibility, ownership, caller, and persistence evidence—not as an implementation-completion gate. Accept `FAIL` only as a typed defect in the task candidate with bound-task evidence, code evidence, and a required task-authority change. Resolve any finding that only observes legacy/unimplemented code or restates a requirement already complete in the task.
   - **Usage accounting:** Capture structured usage emitted by every adapter-declared inspector and coordinator launcher, including formatting retries. Normalize supported launcher shapes into bounded per-launch input, output, cache-read, cache-write, total-token, and cost values plus aggregates in the terminal attempt and PASS verification evidence. Treat Pi `message_end.message.usage` as one transport shape, not as the generic runtime contract.
8. **G1 RED**: Preserve frozen `red/v1` command evidence and proof component lock.
9. **Implementation & Proof Bundle**: Implement the approved contract. Prefer `scripts/record_proof.py` with multiple `--claim` flags to record a single `proof-bundle` closing `runtime/v1`, `parity/v1`, `security/v1`, and `release/v1` simultaneously.
10. **Targeted Invalidation**: Use `scripts/compute_invalidation.py` after accepted changes. For `parity/v1` or `security/v1`, use terminal `inapplicable` only with validated machine applicability evidence.
11. **G3 Review State Machine**:
    - Run `review/v1` through the implementation adapter after code, tests, config, and release evidence settle.
    - Perform pre-review context compaction (clean transient build/test logs) prior to calling `review/v1`.
    - Asynchronous execution allowed: avoid status-polling loops.
    - On accepted findings: classify findings → fix → rerun affected live gates → re-review current fingerprint.
    - Stop condition: Zero open accepted findings and empty blockers. Do not launch a second final review without fingerprint change or accepted-finding remediation.
12. Use the audit adapter for selected final code-review report.
13. Complete handoff with current receipts and empty blockers.

## Troubleshooting & Fail-Closed Protocol

- **Stale Fingerprint Error** (`stale input fingerprint`): Run `python3 scripts/compute_invalidation.py` to identify affected downstream gates. Update modified input hashes via `scripts/record_proof.py` instead of hand-editing.
- **Admission Cap Exhausted** (`attempt cap reached` / `admission blocked`): Stop execution immediately. Record status `blocked` with explicit blocker reason. Never rerun an unchanged failed fingerprint.
- **Review Loop Prevention**: Perform a single asynchronous invocation of `review/v1`. Status polling loops are strictly forbidden.

Use [receipt lifecycle](references/receipts.md), the
[architecture contract](references/architecture.md), and the
[persisted contract propagation matrix](references/value-domains.md).
