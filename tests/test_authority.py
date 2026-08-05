"""Contract authority digest, material classify, write-set, pre-contract."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from acdd.adapter import Adapter, CheckBinding, GateBinding
from acdd.authority import (
    assert_changed_paths_allowed,
    assert_precontract_clean,
    assert_writes_not_shrunk,
    authority_digest,
    classify_contract_change,
)
from acdd.model import AcddError, Check, Gate, Profile, Subtask, load_document
from acdd.record import (
    finalize_gate,
    record_check,
    record_review,
    record_subtask_contract,
    reopen_gate,
)
from acdd.validate import validate


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"], cwd=root, check=True, capture_output=True
    )
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def _doc(tmp_path: Path, *, with_review: bool = False) -> tuple[Path, Profile, list[Adapter]]:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "src" / "second.py").write_text("print('second')\n", encoding="utf-8")
    document_path = tmp_path / "task.md"
    document_path.write_text(
        """\
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
""",
        encoding="utf-8",
    )
    checks: tuple[Check, ...] = ()
    gates_binding: dict[str, GateBinding] = {"contract/v1": GateBinding()}
    verify_binding: dict[str, GateBinding] = {}
    if with_review:
        checks = (Check("contract-verify", "review", "success", "contract-verify"),)
        gates_binding = {"contract/v1": GateBinding()}
        verify_binding = {
            "contract/v1": GateBinding(
                checks={"contract-verify": CheckBinding(argv=("true",), cwd=".")}
            )
        }
    contract = Gate(
        "contract/v1",
        "task",
        checks,
        ("source",),
        ("pass",),
        review_dimensions=("completeness",) if with_review else (),
    )
    build = Gate(
        "build/v1",
        "implementation",
        (Check("runtime-and-integration", "command", "success"),),
        ("source",),
        ("pass",),
    )
    adapters = [
        Adapter("task", "task", "artifacts", tmp_path, gates_binding),
        Adapter(
            "implementation",
            "implementation",
            "artifacts",
            tmp_path,
            {
                "build/v1": GateBinding(
                    checks={"runtime-and-integration": CheckBinding(argv=("true",), cwd=".")}
                )
            },
        ),
    ]
    if with_review:
        adapters.append(Adapter("verify", "contract-verify", "artifacts", tmp_path, verify_binding))
    return document_path, Profile("task/v1", [contract, build]), adapters


def _transcript(path: Path, *, evidence_id: str, dimensions: list[str]) -> None:
    author = "11111111-1111-4111-8111-111111111111"
    inspector = "33333333-3333-4333-8333-333333333333"
    confirmer = "22222222-2222-4222-8222-222222222222"
    rows = [
        {"type": "review_raw", "reviewerSessionUuid": inspector, "raw": "partition ok"},
        {"type": "review_raw", "reviewerSessionUuid": confirmer, "raw": "confirm pass"},
        {
            "type": "review_terminal",
            "evidenceId": evidence_id,
            "gate": "contract/v1",
            "check": "contract-verify",
            "verdict": "pass",
            "authorSessionUuid": author,
            "reviewerSessionUuid": confirmer,
            "scope": ["contract"],
            "reviewedSessionUuids": [inspector, confirmer],
            "performedChecks": dimensions,
        },
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_classify_material_for_supersede_and_overlap():
    first = Subtask("first", ("src/a.py",), (), "a")
    assert (
        classify_contract_change(
            Subtask("fix", ("src/b.py",), (), "b", supersedes="first"),
            contracted_active=(first,),
        )
        == "material"
    )
    assert (
        classify_contract_change(
            Subtask("overlap", ("src/a.py",), (), "o"), contracted_active=(first,)
        )
        == "material"
    )
    assert (
        classify_contract_change(Subtask("add", ("src/b.py",), (), "n"), contracted_active=(first,))
        == "additive"
    )


def test_classify_repair_id_is_material():
    first = Subtask("first", ("src/a.py",), (), "a")
    assert (
        classify_contract_change(
            Subtask("wave1-repair", ("src/b.py",), (), "r", depends_on=("first",)),
            contracted_active=(first,),
        )
        == "material"
    )
    assert (
        classify_contract_change(
            Subtask("finding-fix", ("src/c.py",), (), "f"),
            contracted_active=(first,),
        )
        == "material"
    )


def test_write_set_rejects_escape():
    with pytest.raises(AcddError, match="outside active subtask writes"):
        assert_changed_paths_allowed(["src/other.py"], allowed_writes=["src/app.py"])
    assert_changed_paths_allowed(["src/app.py"], allowed_writes=["src/app.py"])
    assert_changed_paths_allowed(["src/pkg/x.py"], allowed_writes=["src/pkg"])


def test_anti_shrink_rejects_missing_prior_write():
    with pytest.raises(AcddError, match="shrank writes"):
        assert_writes_not_shrunk(
            ["src/app.py", "src/second.py"],
            ["src/app.py"],
            allow_scope_reduction=False,
        )
    assert_writes_not_shrunk(
        ["src/app.py", "src/second.py"],
        ["src/app.py"],
        allow_scope_reduction=True,
    )


def test_precontract_blocks_source_dirty(tmp_path: Path):
    document_path, _, _ = _doc(tmp_path)
    document = load_document(document_path)
    with pytest.raises(AcddError, match="before contract/v1 pass"):
        assert_precontract_clean(
            document_path=document.path,
            inputs=document.inputs,
            receipts=document.receipts,
            workspace=tmp_path,
            dirty_paths=["src/app.py"],
        )
    assert_precontract_clean(
        document_path=document.path,
        inputs=document.inputs,
        receipts=document.receipts,
        workspace=tmp_path,
        dirty_paths=["tests/test_proof.py"],
    )


def test_supersede_appends_via_contract_subtask(tmp_path: Path):
    document_path, profile, adapters = _doc(tmp_path)
    finalize_gate(
        document=load_document(document_path),
        profile=profile,
        adapters=adapters,
        workspace_root=tmp_path,
        gate=profile.gates[0],
        evidence_id="contract.bundle",
        adapter=adapters[0],
    )
    document_path.write_text(
        document_path.read_text(encoding="utf-8").replace(
            "acceptance: first behavior\n",
            "acceptance: first behavior\n"
            "  - id: replacement\n    writes: [src/app.py]\n    reads: []\n"
            "    acceptance: replacement\n    supersedes: first\n",
        ),
        encoding="utf-8",
    )
    part = record_subtask_contract(
        document=load_document(document_path),
        profile=profile,
        workspace_root=tmp_path,
        adapter=adapters[0],
        adapters=adapters,
        subtask_id="replacement",
        evidence_id="contract.replacement",
    )
    assert part["subtask"] == "replacement"
    assert part["supersedes"] == "first"


def test_reopen_forbidden_after_freeze(tmp_path: Path):
    document_path, profile, adapters = _doc(tmp_path)
    finalize_gate(
        document=load_document(document_path),
        profile=profile,
        adapters=adapters,
        workspace_root=tmp_path,
        gate=profile.gates[0],
        evidence_id="contract.bundle",
        adapter=adapters[0],
    )
    with pytest.raises(AcddError, match="reopen of contract/v1 is forbidden"):
        reopen_gate(
            document=load_document(document_path),
            gate=profile.gates[0],
            workspace_root=tmp_path,
        )


def test_replacement_append_rejects_write_shrink(tmp_path: Path):
    document_path, profile, adapters = _doc(tmp_path)
    document_path.write_text(
        document_path.read_text(encoding="utf-8").replace(
            "writes: [src/app.py]",
            "writes: [src/app.py, src/second.py]",
        ),
        encoding="utf-8",
    )
    finalize_gate(
        document=load_document(document_path),
        profile=profile,
        adapters=adapters,
        workspace_root=tmp_path,
        gate=profile.gates[0],
        evidence_id="contract.bundle",
        adapter=adapters[0],
    )
    document_path.write_text(
        document_path.read_text(encoding="utf-8").replace(
            "acceptance: first behavior\n",
            "acceptance: first behavior\n"
            "  - id: replacement\n    writes: [src/app.py]\n    reads: []\n"
            "    acceptance: replacement\n    supersedes: first\n",
        ),
        encoding="utf-8",
    )
    with pytest.raises(AcddError, match="shrank writes"):
        record_subtask_contract(
            document=load_document(document_path),
            profile=profile,
            workspace_root=tmp_path,
            adapter=adapters[0],
            adapters=adapters,
            subtask_id="replacement",
            evidence_id="contract.replacement",
        )
    part = record_subtask_contract(
        document=load_document(document_path),
        profile=profile,
        workspace_root=tmp_path,
        adapter=adapters[0],
        adapters=adapters,
        subtask_id="replacement",
        evidence_id="contract.replacement",
        allow_scope_reduction=True,
    )
    assert part["subtask"] == "replacement"


def test_build_requires_changed_or_git(tmp_path: Path):
    document_path, profile, adapters = _doc(tmp_path)
    finalize_gate(
        document=load_document(document_path),
        profile=profile,
        adapters=adapters,
        workspace_root=tmp_path,
        gate=profile.gates[0],
        evidence_id="contract.bundle",
        adapter=adapters[0],
    )
    with pytest.raises(AcddError, match="git worktree or explicit --changed"):
        record_check(
            document=load_document(document_path),
            workspace_root=tmp_path,
            gate=profile.gates[1],
            check_id="runtime-and-integration",
            evidence_id="build.1",
            adapter=adapters[1],
            adapters=adapters,
        )
    with pytest.raises(AcddError, match="outside active subtask writes"):
        record_check(
            document=load_document(document_path),
            workspace_root=tmp_path,
            gate=profile.gates[1],
            check_id="runtime-and-integration",
            evidence_id="build.2",
            adapter=adapters[1],
            adapters=adapters,
            changed_paths=["src/second.py"],
        )
    payload, ok = record_check(
        document=load_document(document_path),
        workspace_root=tmp_path,
        gate=profile.gates[1],
        check_id="runtime-and-integration",
        evidence_id="build.3",
        adapter=adapters[1],
        adapters=adapters,
        changed_paths=["src/app.py"],
    )
    assert ok and payload is not None


def test_build_git_write_set(tmp_path: Path):
    document_path, profile, adapters = _doc(tmp_path)
    _git_init(tmp_path)
    finalize_gate(
        document=load_document(document_path),
        profile=profile,
        adapters=adapters,
        workspace_root=tmp_path,
        gate=profile.gates[0],
        evidence_id="contract.bundle",
        adapter=adapters[0],
    )
    (tmp_path / "src" / "second.py").write_text("print('dirty')\n", encoding="utf-8")
    with pytest.raises(AcddError, match="outside active subtask writes"):
        record_check(
            document=load_document(document_path),
            workspace_root=tmp_path,
            gate=profile.gates[1],
            check_id="runtime-and-integration",
            evidence_id="build.git",
            adapter=adapters[1],
            adapters=adapters,
        )


def test_authority_digest_requires_matching_verify_after_additive(tmp_path: Path):
    document_path, profile, adapters = _doc(tmp_path, with_review=True)
    transcript = tmp_path / "artifacts" / "verify.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    _transcript(transcript, evidence_id="contract.verify", dimensions=["completeness"])
    record_review(
        document=load_document(document_path),
        workspace_root=tmp_path,
        gate=profile.gates[0],
        check_id="contract-verify",
        evidence_id="contract.verify",
        adapter=adapters[2],
        transcript=transcript,
        author_uuid="11111111-1111-4111-8111-111111111111",
        reviewer_uuid="22222222-2222-4222-8222-222222222222",
        verdict="pass",
        adapters=adapters,
    )
    digest_before = authority_digest(load_document(document_path).subtasks)
    evidence = load_document(document_path).evidence[0]
    assert evidence["authorityDigest"] == digest_before
    finalize_gate(
        document=load_document(document_path),
        profile=profile,
        adapters=adapters,
        workspace_root=tmp_path,
        gate=profile.gates[0],
        evidence_id="contract.bundle",
        adapter=adapters[0],
    )
    assert (
        validate(load_document(document_path), profile, adapters=adapters, workspace_root=tmp_path)
        == []
    )

    document_path.write_text(
        document_path.read_text(encoding="utf-8").replace(
            "acceptance: first behavior\n",
            "acceptance: first behavior\n"
            "  - id: second\n    writes: [src/second.py]\n    reads: []\n"
            "    acceptance: second\n    dependsOn: [first]\n",
        ),
        encoding="utf-8",
    )
    record_subtask_contract(
        document=load_document(document_path),
        profile=profile,
        workspace_root=tmp_path,
        adapter=adapters[0],
        adapters=adapters,
        subtask_id="second",
        evidence_id="contract.second",
    )
    errors = validate(
        load_document(document_path), profile, adapters=adapters, workspace_root=tmp_path
    )
    assert any(error.invariant == 4 and "authority digest" in str(error) for error in errors)

    transcript2 = tmp_path / "artifacts" / "verify2.jsonl"
    _transcript(transcript2, evidence_id="contract.verify2", dimensions=["completeness"])
    record_review(
        document=load_document(document_path),
        workspace_root=tmp_path,
        gate=profile.gates[0],
        check_id="contract-verify",
        evidence_id="contract.verify2",
        adapter=adapters[2],
        transcript=transcript2,
        author_uuid="11111111-1111-4111-8111-111111111111",
        reviewer_uuid="22222222-2222-4222-8222-222222222222",
        verdict="pass",
        adapters=adapters,
    )
    assert (
        validate(load_document(document_path), profile, adapters=adapters, workspace_root=tmp_path)
        == []
    )
