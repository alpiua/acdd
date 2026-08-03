"""Append-only subtask contracts after the task Contract gate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from acdd._doc import read_jsonl
from acdd.adapter import Adapter, GateBinding
from acdd.fingerprint import subtask_contract_hash, subtask_fingerprint
from acdd.model import AcddError, Gate, Profile, load_document
from acdd.record import finalize_gate, record_subtask_contract
from acdd.validate import validate


def _context(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "src" / "second.py").write_text("print('second')\n", encoding="utf-8")
    document_path = tmp_path / "task.md"
    document_path.write_text("""\
---
title: T
planning_profile: task/v1
---
## Plan
```yaml
subtasks:
  - id: first
    writes: [src/app.py]
    reads: []
    acceptance: first behavior
```
## Inputs
```yaml
paths:
  - {type: source, path: src}
```
## Evidence

## Receipts
| gate | status | evidence | fingerprint | recordedAt |
| --- | --- | --- | --- | --- |
| contract/v1 | pending | pending | pending | pending |
| build/v1 | pending | pending | pending | pending |
""", encoding="utf-8")
    contract = Gate("contract/v1", "task", (), ("source",), ("pass",))
    build = Gate("build/v1", "implementation", (), ("source",), ("pass",))
    task_adapter = Adapter("task", "task", "artifacts", tmp_path, {"contract/v1": GateBinding()})
    implementation_adapter = Adapter("implementation", "implementation", "artifacts", tmp_path,
                                     {"build/v1": GateBinding()})
    return document_path, Profile("task/v1", [contract, build]), contract, build, [task_adapter, implementation_adapter]


def _append(document_path: Path, text: str) -> None:
    document_path.write_text(document_path.read_text(encoding="utf-8").replace(
        "    acceptance: first behavior\n", f"    acceptance: first behavior\n{text}"), encoding="utf-8")


def _source_parts(document, root: Path) -> tuple[dict, list[dict]]:
    bundle = next(item for item in document.evidence if item.get("kind") == "bundle" and item.get("gate") == "contract/v1")
    records = read_jsonl(root / bundle["subtaskContractBundleRef"])
    assert records is not None
    return bundle, [record for record in records if record.get("type") == "subtask_contract"]


def test_additive_subtask_narrows_a_shared_input_without_staling_build(tmp_path: Path):
    document_path, profile, contract, build, adapters = _context(tmp_path)
    finalize_gate(document=load_document(document_path), profile=profile, adapters=adapters,
                  workspace_root=tmp_path, gate=contract, evidence_id="contract.bundle", adapter=adapters[0])
    bundle, original_parts = _source_parts(load_document(document_path), tmp_path)
    original_records = read_jsonl(tmp_path / bundle["subtaskContractBundleRef"])
    assert original_records is not None and len(original_records) == 2
    assert original_records[1]["type"] == "subtask_contract_binding"
    assert len(original_parts) == 1

    document_path.write_text(document_path.read_text(encoding="utf-8").replace(
        "acceptance: first behavior", "acceptance: changed behavior"), encoding="utf-8")
    errors = validate(load_document(document_path), profile, adapters=adapters, workspace_root=tmp_path)
    assert any(error.invariant == 6 and "source changed" in str(error) for error in errors)

    document_path.write_text(document_path.read_text(encoding="utf-8").replace(
        "acceptance: changed behavior", "acceptance: first behavior"), encoding="utf-8")
    finalize_gate(document=load_document(document_path), profile=profile, adapters=adapters,
                  workspace_root=tmp_path, gate=build, evidence_id="build.bundle", adapter=adapters[1])
    build_fingerprint = load_document(document_path).receipts[1]["fingerprint"]

    _append(document_path, "  - id: second\n    writes: [src/second.py]\n    reads: [src/app.py]\n"
                           "    acceptance: second behavior\n    dependsOn: [first]\n")
    errors = validate(load_document(document_path), profile, adapters=adapters, workspace_root=tmp_path)
    assert any(error.invariant == 6 and "has no source contract" in str(error) for error in errors)

    record_subtask_contract(document=load_document(document_path), profile=profile, workspace_root=tmp_path,
                            adapter=adapters[0], adapters=adapters, subtask_id="second",
                            evidence_id="contract.second")
    document = load_document(document_path)
    appended_bundle, parts = _source_parts(document, tmp_path)
    records = read_jsonl(tmp_path / appended_bundle["subtaskContractBundleRef"])
    assert appended_bundle["subtaskContractBundleRef"] == bundle["subtaskContractBundleRef"]
    assert records is not None and records[:2] == original_records
    assert parts[0] == original_parts[0]
    assert len(parts) == 2 and len(records) == 4 and all("partSha256" in part for part in parts)
    assert validate(document, profile, adapters=adapters, workspace_root=tmp_path) == []
    assert document.receipts[1]["fingerprint"] == build_fingerprint

def test_subtask_part_cannot_be_rewritten_with_a_new_self_hash(tmp_path: Path):
    document_path, profile, contract, _, adapters = _context(tmp_path)
    finalize_gate(document=load_document(document_path), profile=profile, adapters=adapters,
                  workspace_root=tmp_path, gate=contract, evidence_id="contract.bundle", adapter=adapters[0])
    document_path.write_text(document_path.read_text(encoding="utf-8").replace(
        "first behavior", "tampered behavior"), encoding="utf-8")
    document = load_document(document_path)
    bundle, _ = _source_parts(document, tmp_path)
    records = read_jsonl(tmp_path / bundle["subtaskContractBundleRef"])
    assert records is not None
    part = next(record for record in records if record["type"] == "subtask_contract")
    part["sourceFingerprint"] = subtask_fingerprint(document.subtasks[0])
    part["partSha256"] = subtask_contract_hash(part)
    (tmp_path / bundle["subtaskContractBundleRef"]).write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")

    errors = validate(load_document(document_path), profile, adapters=adapters, workspace_root=tmp_path)
    assert any(error.invariant == 2 and "source contract binding is missing or invalid" in str(error) for error in errors)

def test_replacement_supersedes_only_its_contracted_predecessor(tmp_path: Path):
    document_path, profile, contract, _, adapters = _context(tmp_path)
    finalize_gate(document=load_document(document_path), profile=profile, adapters=adapters,
                  workspace_root=tmp_path, gate=contract, evidence_id="contract.bundle", adapter=adapters[0])

    _append(document_path, "  - id: replacement\n    writes: [src/app.py]\n    reads: []\n"
                           "    acceptance: replacement behavior\n    supersedes: first\n")
    record_subtask_contract(document=load_document(document_path), profile=profile, workspace_root=tmp_path,
                            adapter=adapters[0], adapters=adapters, subtask_id="replacement",
                            evidence_id="contract.replacement")
    document = load_document(document_path)
    _, parts = _source_parts(document, tmp_path)
    contracts = {item["subtask"]: item for item in parts}
    assert validate(document, profile, adapters=adapters, workspace_root=tmp_path) == []
    assert contracts["first"].get("supersedes") is None
    assert contracts["replacement"]["supersedes"] == "first"

    _append(document_path, "  - id: another-replacement\n    writes: [src/app.py]\n    reads: []\n"
                           "    acceptance: another replacement\n    supersedes: first\n")
    with pytest.raises(AcddError, match="multiple replacements"):
        record_subtask_contract(document=load_document(document_path), profile=profile, workspace_root=tmp_path,
                                adapter=adapters[0], adapters=adapters, subtask_id="another-replacement",
                                evidence_id="contract.another-replacement")


def test_subtask_relationships_reject_a_mixed_dependency_replacement_cycle(tmp_path: Path):
    document_path, profile, _, _, adapters = _context(tmp_path)
    document_path.write_text(document_path.read_text(encoding="utf-8").replace(
        "acceptance: first behavior", "acceptance: first behavior\n    dependsOn: [replacement]"), encoding="utf-8")
    _append(document_path, "  - id: replacement\n    writes: [src/app.py]\n    reads: []\n"
                           "    acceptance: replacement behavior\n    supersedes: first\n")
    errors = validate(load_document(document_path), profile, adapters=adapters, workspace_root=tmp_path)
    assert any(error.invariant == 6 and "relationships must be acyclic" in str(error) for error in errors)


def test_subtask_scope_cannot_escape_a_shared_input(tmp_path: Path):
    document_path, profile, _, _, adapters = _context(tmp_path)
    document_path.write_text(document_path.read_text(encoding="utf-8").replace(
        "{type: source, path: src}", "{type: source, path: .}").replace(
        "writes: [src/app.py]", "writes: [../outside.py]"), encoding="utf-8")
    errors = validate(load_document(document_path), profile, adapters=adapters, workspace_root=tmp_path)
    assert any(error.invariant == 6 and "invalid scope" in str(error) for error in errors)
