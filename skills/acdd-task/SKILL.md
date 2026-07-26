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
7. **G0 Architecture**: Freeze one candidate, then use the owner architecture wrapper once. Keep the keyword-discovered code map in the task. The runner performs preflight/admission, computes one architecture fingerprint from declared files under the implementation repository's `services/`, `packages/`, `core/`, and `extensions/` roots only, runs four read-only inspectors concurrently, starts one coordinator only after they finish, and records the terminal attempt. It never fingerprints the task, adapters, runner, docs, `.pi*` artifacts, or other workflow state, and never recomputes a second snapshot after launch. While VERIFYING, do not edit authority. On FAIL, remediate one reconciled findings batch, create a new candidate, and never manually relaunch an unchanged fingerprint. On cap exhaustion or runtime BLOCKED, stop.
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

