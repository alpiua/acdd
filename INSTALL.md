# Install and integrate ACDD Workflow

## Requirements

- Python 3.11+
- PyYAML
- pytest for contract tests
- owner adapters stored under each domain repository's `.acdd/`

Run:

```bash
python3 -m pytest tests -q
```

## Owner bundles

An owner bundle contains its adapters, procedures, templates, validators,
configuration, and tests:

```text
<domain>/.acdd/
  task-adapter.yaml
  plan-adapter.yaml
  implementation-adapter.yaml
  scripts/
  templates/
  tests/
```

Use only the adapter roles implemented by that domain.

## Task flow

```bash
python3 scripts/validate_acdd.py \
  --profile profiles/task/v1.yaml \
  --workspace-root . \
  --adapter task=examples/planner/.acdd/task-adapter.yaml \
  --adapter implementation=examples/codebase/.acdd/implementation-adapter.yaml
```

Every route names one executor adapter. For task `architecture/v1`, the task adapter
selects the Pi inbound coordinator, concrete verification contract, model, command CWD,
and tool envelope. The implementation adapter contributes source, test, configuration,
caller, backend, architecture-reference, and structural-search authority without
selecting the G0 runtime. For task `review/v1`, the implementation adapter selects
`pi-review-agents` overview and denies the G0 verifier. Capability-based receipt
validation requires isolation, read-only execution, all four partitions, and one
coordinator verdict; runtime is retained as provenance.

## Plan flow

```bash
python3 scripts/validate_acdd.py \
  --profile profiles/plan/v1.yaml \
  --workspace-root . \
  --adapter plan=examples/planner/.acdd/plan-adapter.yaml
```

The plan adapter defines planning evidence, hierarchy mapping, shape validation,
publication, and final plan review. Planner uses bounded Pi inbound verification
for intermediate questions and `pi-review-agents` overview mode for the complete
planning set.

## Audit publication

Add an audit adapter when the owner selects a final report:

```bash
--adapter audit=examples/audit/.acdd/audit-adapter.yaml
```

The producing adapter returns a terminal review result. The audit adapter
validates and publishes the selected report. Gate receipts remain in the bound
task or primary plan.

## External mappings and impact

Adapters map ACDD owner kinds to external classes while preserving
`roadmap → phase → milestone → task`.

- Linear: Initiative → Project → Project Milestone → Issue.
- Jira: Initiative → Epic → Version/Release → Story or Task.
- Planner: roadmap file → phase file → milestone file → task file.

Impact axes are domain-owned. The examples cover software delivery, data
platform, regulated/security, product/customer, and commercial variants.

## Inline evidence and fingerprints

Declare typed paths under `## ACDD inputs`, store bounded discriminated evidence
under `## ACDD gate evidence`, and reference it as `evidence=<id>` from the
receipt table. Strict validation adds the bound document, profile, receipt
contract, and supplied adapters, builds the canonical snapshot in memory, and
applies the selected gate policy. It writes no provenance files.

Repository gates:

```bash
python3 -m pytest tests -q
python3 scripts/validate_acdd.py --profile profiles/task/v1.yaml --workspace-root . \
  --document examples/task/TASK.md \
  --adapter task=examples/planner/.acdd/task-adapter.yaml \
  --adapter implementation=examples/codebase/.acdd/implementation-adapter.yaml
python3 scripts/validate_acdd.py --profile profiles/plan/v1.yaml --workspace-root . \
  --document PLAN.md \
  --adapter plan=examples/planner/.acdd/plan-adapter.yaml
python3 scripts/check_simple_plan.py --plan PLAN.md --strict
python3 scripts/check_markdown_links.py --root .
```
