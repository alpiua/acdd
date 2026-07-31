"""Regression tests for receipt-contract hardening.

Covers the review self-invalidation fix, the evidence-bearing ``partial``
status, plan shape-gate inapplicability derived from ``planning_set``, plan
architecture freshness on the declared-input basis, and executor-declared
verification classes for architecture/review gates.
"""
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DOC = _load("acdd_document")
FP = _load("acdd_fingerprint")
VALIDATOR = _load("validate_acdd")

RECORDED = "2026-01-01T00:00:00Z"
SHAPE_GATES = {"roadmap-shape/v1", "milestone-shape/v1"}


def _fp(gate: str) -> str:
    """Per-gate fingerprint placeholder resolved against real gate policies."""
    return f"@@FP:{gate}@@"


def _policies() -> tuple[object, ...]:
    core = VALIDATOR.load_core(ROOT / "profiles" / "plan" / "v1.yaml")
    return VALIDATOR._gate_policies(core)


def _basis_block(evidence_id: str, gate: str) -> str:
    return f"""```yaml
apiVersion: acdd/gate-evidence/v1
kind: basis
id: {evidence_id}
gate: {gate}
inputFingerprint: {_fp(gate)}
summary: {gate} basis
authoritySources: [PLAN.md]
mappings: [PLAN.md]
```
"""


def _review_block(evidence_id: str, gate: str) -> str:
    return f"""```yaml
apiVersion: acdd/gate-evidence/v1
kind: review
id: {evidence_id}
gate: {gate}
inputFingerprint: {_fp(gate)}
adapter: plan
sessionUuid: "00000000-0000-4000-8000-000000000001"
authorSessionUuid: "00000000-0000-4000-8000-000000000002"
reviewer: plan-reviewer
independent: true
terminalVerdict: PASS
authoritySources: [PLAN.md]
productionPaths: [source.py]
directCallers: [source.py]
alternateCallers: []
contradictions: []
impactAxes: {{docs: checked}}
matrixMappings: [PLAN.md]
proofMappings: [source.py]
findings: []
inventoryComplete: true
decisionsResolved: true
callerCoverageComplete: true
persistedContractChange: false
persistedContractMappings: []
discoveryComplete: true
```
"""


def _inapplicable_block(evidence_id: str, gate: str, reason: str) -> str:
    return f"""```yaml
apiVersion: acdd/gate-evidence/v1
kind: command
id: {evidence_id}
gate: {gate}
inputFingerprint: {_fp(gate)}
exactCommand: planning-set shape eligibility derivation
recordedAt: "{RECORDED}"
exitCode: 0
output: "no artifacts of this shape in the planning set"
redacted: true
result: inapplicable
applicability:
  engine: planning-set
  evidenceRef: planning-set.manifest
  axesChecked: [docs]
  reasonCode: {reason}
```
"""


def _plan_document(
    *,
    planning_set: str,
    rows: list[tuple[str, str, str]],
    evidence: list[str],
) -> str:
    table = "\n".join(
        f"| {gate} | {status} | {cells} |" for gate, status, cells in rows
    )
    return f"""---
title: hardening fixture
kind: plan
planning_profile: acdd/plan/v1
{planning_set}
---
# Fixture plan

## ACDD inputs

```yaml
apiVersion: acdd/inputs/v1
kind: inputs
paths:
  - type: source
    path: source.py
```

## ACDD gate evidence

{''.join(evidence)}
## ACDD plan receipts

| Gate | Status | Evidence | InputFingerprint | RecordedAt |
| --- | --- | --- | --- | --- |
{table}
"""


def _pass_row(gate: str, evidence_id: str) -> tuple[str, str, str]:
    return (gate, "pass", f"evidence={evidence_id} | {_fp(gate)} | {RECORDED}")


def _pending_row(gate: str) -> tuple[str, str, str]:
    return (gate, "pending", "pending | pending | pending")


def _validate(tmp_path: Path, text: str) -> None:
    (tmp_path / "source.py").write_text("value = 1\n", encoding="utf-8")
    adapter = tmp_path / "plan-adapter.yaml"
    adapter.write_text(
        """apiVersion: acdd/adapter/v1
kind: adapter
role: plan
inputAuthorities:
  bound-document: [PLAN.md]
  source: [source.py]
""",
        encoding="utf-8",
    )
    document = tmp_path / "PLAN.md"
    document.write_text(text, encoding="utf-8")
    policies = _policies()
    for policy in policies:
        digest = FP.fingerprint_inputs(
            document=document,
            profile=ROOT / "profiles" / "plan" / "v1.yaml",
            receipt_contract=ROOT / "contracts" / "receipt" / "plan" / "v1.yaml",
            adapters=(adapter,),
            workspace_root=tmp_path,
            include_types=frozenset(policy.invalidation_inputs),
            include_classes=policy.invalidation_classes,
        ).sha256
        text = text.replace(_fp(policy.gate), digest)
    document.write_text(text, encoding="utf-8")
    DOC.validate_document(
        document=document,
        profile=ROOT / "profiles" / "plan" / "v1.yaml",
        receipt_contract=ROOT / "contracts" / "receipt" / "plan" / "v1.yaml",
        adapters=(adapter,),
        workspace_root=tmp_path,
        policies=policies,
        plan=True,
        impact_axes=frozenset({"docs"}),
        applicability_policy=DOC.PLAN_APPLICABILITY_POLICY,
    )


def _hardened_rows() -> tuple[list[tuple[str, str, str]], list[str]]:
    """Rows in canonical profile order with terminal predecessors."""
    rows = [
        _pass_row("intent/v1", "intent.pass"),
        _pass_row("evidence/v1", "evidence.pass"),
        _pass_row("architecture/v1", "architecture.pass"),
        _pass_row("plan-shape/v1", "planshape.pass"),
        (
            "roadmap-shape/v1",
            "inapplicable",
            f"evidence=roadmap.inapplicable | {_fp('roadmap-shape/v1')} | {RECORDED}",
        ),
        (
            "milestone-shape/v1",
            "inapplicable",
            f"evidence=milestone.inapplicable | {_fp('milestone-shape/v1')} | {RECORDED}",
        ),
        (
            "decomposition/v1",
            "partial",
            f"evidence=decomposition.partial | {_fp('decomposition/v1')} | {RECORDED}",
        ),
        _pending_row("review/v1"),
        _pending_row("publish/v1"),
        _pending_row("handoff/v1"),
    ]
    evidence = [
        _basis_block("intent.pass", "intent/v1"),
        _basis_block("evidence.pass", "evidence/v1"),
        _review_block("architecture.pass", "architecture/v1"),
        _basis_block("planshape.pass", "plan-shape/v1"),
        _inapplicable_block(
            "roadmap.inapplicable",
            "roadmap-shape/v1",
            "roadmap-shape.no_roadmap_or_phase_artifact_in_set",
        ),
        _inapplicable_block(
            "milestone.inapplicable",
            "milestone-shape/v1",
            "milestone-shape.no_milestone_or_task_artifact_in_set",
        ),
        _basis_block("decomposition.partial", "decomposition/v1"),
    ]
    return rows, evidence


EMPTY_PLANNING_SET = """planning_set:
  primary: PLAN.md
  roadmap: []
  phases: []
  milestones: []
  task_drafts: []"""

NONEMPTY_PLANNING_SET = """planning_set:
  primary: PLAN.md
  roadmap: [roadmap/00_OVERVIEW.md]
  phases: []
  milestones: []
  task_drafts: []"""


def test_partial_and_shape_inapplicable_receipts_validate(tmp_path: Path) -> None:
    rows, evidence = _hardened_rows()
    _validate(tmp_path, _plan_document(planning_set=EMPTY_PLANNING_SET, rows=rows, evidence=evidence))


def test_plan_architecture_pass_uses_declared_input_basis(tmp_path: Path) -> None:
    """Plan architecture/v1 has no task G0 sections; freshness binds the
    declared-input basis instead of the semantic candidate fingerprint."""
    rows, evidence = _hardened_rows()
    _validate(
        tmp_path,
        _plan_document(planning_set=EMPTY_PLANNING_SET, rows=rows, evidence=evidence),
    )


def test_shape_inapplicable_rejected_when_planning_set_declares_artifacts(
    tmp_path: Path,
) -> None:
    rows, evidence = _hardened_rows()
    with pytest.raises(
        DOC.DocumentError, match="cannot be inapplicable while planning_set declares"
    ):
        _validate(
            tmp_path,
            _plan_document(planning_set=NONEMPTY_PLANNING_SET, rows=rows, evidence=evidence),
        )


def test_inapplicable_rejected_outside_policy_gates(tmp_path: Path) -> None:
    rows, evidence = _hardened_rows()
    rows[3] = (
        "plan-shape/v1",
        "inapplicable",
        f"evidence=planshape.pass | {_fp('plan-shape/v1')} | {RECORDED}",
    )
    with pytest.raises(DOC.DocumentError, match="invalid status"):
        _validate(tmp_path, _plan_document(planning_set=EMPTY_PLANNING_SET, rows=rows, evidence=evidence))


def test_partial_row_requires_complete_inline_evidence(tmp_path: Path) -> None:
    rows, evidence = _hardened_rows()
    rows[6] = ("decomposition/v1", "partial", "pending | pending | pending")
    with pytest.raises(
        DOC.DocumentError, match="nonpending status requires complete inline evidence"
    ):
        _validate(tmp_path, _plan_document(planning_set=EMPTY_PLANNING_SET, rows=rows, evidence=evidence))


def test_terminal_receipt_after_partial_predecessor_is_rejected(tmp_path: Path) -> None:
    rows, evidence = _hardened_rows()
    rows[0] = (
        "intent/v1",
        "partial",
        f"evidence=intent.pass | {_fp('intent/v1')} | {RECORDED}",
    )
    rows[6] = _pending_row("decomposition/v1")
    with pytest.raises(
        DOC.DocumentError, match="later gate cannot be terminal before predecessors"
    ):
        _validate(tmp_path, _plan_document(planning_set=EMPTY_PLANNING_SET, rows=rows, evidence=evidence))


@pytest.mark.parametrize(
    "profile",
    ["task/v1.yaml", "task/v1-light.yaml", "plan/v1.yaml"],
)
def test_review_gate_is_not_invalidated_by_findings_acceptance(profile: str) -> None:
    core = VALIDATOR.load_core(ROOT / "profiles" / profile)
    review_inputs = set(
        core.receipt_contract["gatePolicies"]["review/v1"]["invalidationInputs"]
    )
    assert "accepted-review-findings" not in review_inputs
    assert "accepted-review-findings" in set(
        core.receipt_contract["invalidationInputs"]
    )


@pytest.mark.parametrize(
    "profile",
    ["task/v1.yaml", "task/v1-light.yaml", "plan/v1.yaml"],
)
def test_shipped_contracts_declare_partial_nonterminal_status(profile: str) -> None:
    core = VALIDATOR.load_core(ROOT / "profiles" / profile)
    assert core.receipt_contract["partialStatus"] == "partial"
    for statuses in core.receipt_contract["terminalStatuses"].values():
        assert "partial" not in statuses


def test_plan_contract_declares_shape_inapplicable_policy() -> None:
    core = VALIDATOR.load_core(ROOT / "profiles" / "plan" / "v1.yaml")
    policy = core.receipt_contract["inapplicablePolicy"]
    assert set(policy["gates"]) == SHAPE_GATES
    assert policy["engines"] == ["planning-set"]
    assert policy["forbiddenImpactAxes"] == []


def test_executor_procedures_declare_verification_class() -> None:
    core = VALIDATOR.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    adapter_path = ROOT / "examples" / "planner" / ".acdd" / "task-adapter.yaml"
    adapter = VALIDATOR.load_adapter(adapter_path, "task", core, allowed_root=ROOT)
    architecture = adapter["gateProcedures"]["architecture/v1"]
    assert architecture["verificationClass"] == "full-wave"


def test_missing_verification_class_fails_closed() -> None:
    core = VALIDATOR.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    adapter_path = ROOT / "examples" / "planner" / ".acdd" / "task-adapter.yaml"
    adapter = VALIDATOR.load_adapter(adapter_path, "task", core, allowed_root=ROOT)
    procedures = copy.deepcopy(adapter["gateProcedures"])
    del procedures["architecture/v1"]["verificationClass"]
    with pytest.raises(VALIDATOR.ContractError, match="verificationClass"):
        VALIDATOR._validate_executor_gate_procedures(
            procedures, core, "task", adapter_path, ROOT, "adapter.gateProcedures"
        )


def test_task_architecture_cannot_downgrade_verification_class() -> None:
    core = VALIDATOR.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    adapter_path = ROOT / "examples" / "planner" / ".acdd" / "task-adapter.yaml"
    adapter = VALIDATOR.load_adapter(adapter_path, "task", core, allowed_root=ROOT)
    procedures = copy.deepcopy(adapter["gateProcedures"])
    procedures["architecture/v1"]["verificationClass"] = "single-pass"
    with pytest.raises(
        VALIDATOR.ContractError, match="requires verificationClass: full-wave"
    ):
        VALIDATOR._validate_executor_gate_procedures(
            procedures, core, "task", adapter_path, ROOT, "adapter.gateProcedures"
        )
