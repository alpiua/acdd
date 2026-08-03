"""One focused regression per universal invariant."""

from __future__ import annotations

import json
from pathlib import Path

from acdd._doc import sha256
from acdd.adapter import load_adapter
from acdd.cli import main
from acdd.fingerprint import fingerprint_for_gate
from acdd.model import (
    Check,
    Document,
    Gate,
    Profile,
    load_document,
    load_profile,
)
from acdd.validate import validate


def _args(doc: Path, profile: Path, adapter: Path) -> list[str]:
    return [
        str(doc),
        str(profile),
        "--workspace-root",
        str(doc.parent),
        "--adapter",
        f"implementation={adapter}",
    ]


def _final(core):
    doc, profile, adapter = core
    assert (
        main(
            [
                "record",
                *_args(doc, profile, adapter),
                "--gate",
                "build/v1",
                "--check",
                "runtime-and-integration",
                "--id",
                "build.check",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "finalize",
                *_args(doc, profile, adapter),
                "--gate",
                "build/v1",
                "--id",
                "build.bundle",
            ]
        )
        == 0
    )
    return doc, profile, adapter


def _errors(doc: Path, profile: Path, adapter: Path):
    return validate(
        load_document(doc),
        load_profile(profile),
        adapters=[load_adapter(adapter)],
        workspace_root=doc.parent,
    )


def test_invariant_1_rejects_unknown_status(core):
    doc, profile, adapter = core
    doc.write_text(
        doc.read_text(encoding="utf-8").replace("| build/v1 | pending", "| build/v1 | impossible"),
        encoding="utf-8",
    )
    assert any(error.invariant == 1 for error in _errors(doc, profile, adapter))


def test_invariant_2_rejects_tampered_artifact(core):
    doc, profile, adapter = _final(core)
    (doc.parent / "artifacts" / "build.check.jsonl").write_text("tampered\n", encoding="utf-8")
    assert any(error.invariant == 2 for error in _errors(doc, profile, adapter))


def test_invariant_3_binds_receipt_and_bundle(core):
    doc, profile, adapter = _final(core)
    doc.write_text(
        doc.read_text(encoding="utf-8")
        .replace("| build/v1 | pass |", "| build/v1 | pass |", 1)
        .replace(" | sha256:", " | sha256:bad", 1),
        encoding="utf-8",
    )
    assert any(error.invariant == 3 for error in _errors(doc, profile, adapter))


def test_invariant_4_detects_changed_input(core):
    doc, profile, adapter = _final(core)
    (doc.parent / "src" / "app.py").write_text("changed\n", encoding="utf-8")
    assert any(error.invariant == 4 for error in _errors(doc, profile, adapter))


def test_invariant_5_rejects_wrong_bundle_owner(core):
    doc, profile, adapter = _final(core)
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "issuerRole: implementation", "issuerRole: task", 1
        ),
        encoding="utf-8",
    )
    assert any(error.invariant == 5 for error in _errors(doc, profile, adapter))


def test_invariant_6_rejects_unbounded_subtask(core):
    doc, profile, adapter = core
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "subtasks: []",
            """subtasks:
  - id: bad
    writes: [outside.py]
    reads: []
    acceptance: ''""",
        ),
        encoding="utf-8",
    )
    assert any(error.invariant == 6 for error in _errors(doc, profile, adapter))


def _terminal_document(
    tmp_path: Path, *, kind: str, status: str, reason: str | None = None
) -> tuple[Document, Profile]:
    from acdd.adapter import Adapter, CheckBinding, GateBinding

    check_id = "independent-review" if kind == "review" else "runtime-and-integration"
    gate = Gate(
        "review/v1" if kind == "review" else "build/v1",
        "review" if kind == "review" else "implementation",
        (Check(check_id, kind, "success"),),
        (),
        ("pass", "inapplicable") if kind != "review" else ("pass",),
        ("build.no-runnable-source",),
    )
    path = tmp_path / "artifact.jsonl"
    child_id = "child"
    record = {
        "type": "review_terminal" if kind == "review" else "command_run",
        "evidenceId": child_id,
        "gate": gate.id,
        "check": gate.checks[0].id,
    }
    if kind == "review":
        record.update(
            {
                "verdict": "pass",
                "authorSessionUuid": "00000000-0000-4000-8000-000000000001",
                "reviewerSessionUuid": "00000000-0000-4000-8000-000000000002",
                "reviewedSessionUuids": ["00000000-0000-4000-8000-000000000002"],
                "scope": ["src/"],
                "performedChecks": [],
            }
        )
    else:
        record["exitCode"] = 0
    records = (
        [
            {
                "type": "review_raw",
                "reviewerSessionUuid": "00000000-0000-4000-8000-000000000002",
                "raw": '{"findings": []}',
            }
        ]
        if kind == "review"
        else []
    ) + [record]
    path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")
    document = Document(
        title="T", inputs=[], evidence=[], receipts=[], subtasks=[], path=tmp_path / "task.md"
    )
    adapter = Adapter(
        gate.owner,
        gate.owner,
        "artifacts",
        tmp_path,
        {gate.id: GateBinding(checks={check_id: CheckBinding(argv=("/bin/true",))})},
    )
    fingerprint = fingerprint_for_gate(document, gate, tmp_path, adapter)
    child = {
        "kind": kind,
        "id": child_id,
        "gate": gate.id,
        "check": gate.checks[0].id,
        "issuerRole": gate.owner,
        "artifactSha256": sha256(path),
        "inputFingerprint": fingerprint,
        {"review": "transcriptRef", "command": "commandReceipt"}[kind]: "artifact.jsonl",
    }
    if kind == "review":
        child.update(
            {
                "verdict": "pass",
                "authorSessionUuid": "00000000-0000-4000-8000-000000000001",
                "reviewerSessionUuid": "00000000-0000-4000-8000-000000000001",
            }
        )
    check_evidence = [] if status == "inapplicable" else [child_id]
    bundle = {
        "kind": "bundle",
        "id": "bundle",
        "gate": gate.id,
        "issuerRole": gate.owner,
        "checkEvidence": check_evidence,
        "inputFingerprint": fingerprint,
    }
    if reason is not None:
        bundle["reasonCode"] = reason
    document.evidence = ([child] if check_evidence else []) + [bundle]
    document.receipts = [
        {
            "gate": gate.id,
            "status": status,
            "evidence": "bundle=bundle",
            "fingerprint": fingerprint,
            "recordedAt": "now",
        }
    ]
    return document, Profile("test", [gate])


def test_invariant_7_requires_distinct_review_uuids(tmp_path: Path):
    document, profile = _terminal_document(tmp_path, kind="review", status="pass")
    assert any(
        error.invariant == 7 for error in validate(document, profile, workspace_root=tmp_path)
    )


def test_invariant_8_requires_declared_reason(tmp_path: Path):
    document, profile = _terminal_document(
        tmp_path, kind="command", status="inapplicable", reason="wrong.reason"
    )
    assert any(
        error.invariant == 8 for error in validate(document, profile, workspace_root=tmp_path)
    )
