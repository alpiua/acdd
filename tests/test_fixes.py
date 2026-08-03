"""Regressions for the acdd-v2 audit fixes."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from acdd._doc import command_outcome_ok, sha256
from acdd.adapter import AdapterError, load_adapter
from acdd.cli import main
from acdd.fingerprint import fingerprint_for_gate, fingerprint_gate
from acdd.model import (
    AcddError,
    Check,
    Document,
    Gate,
    Profile,
    Subtask,
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


def _review_raw(
    *, reviewer_uuid: str = "00000000-0000-4000-8000-000000000002", raw: str = '{"findings": []}'
) -> dict:
    return {"type": "review_raw", "reviewerSessionUuid": reviewer_uuid, "raw": raw}


def test_basis_artifact_with_failed_outcome_is_rejected(tmp_path: Path):
    (tmp_path / "a.yaml").write_text(
        """\
apiVersion: acdd/adapter/v1
id: x
role: implementation
gates:
  build/v1:
    checks:
      c: {argv: [/bin/true]}
""",
        encoding="utf-8",
    )
    adapter = load_adapter(tmp_path / "a.yaml")
    artifact = tmp_path / "basis.jsonl"
    artifact.write_text(
        json.dumps(
            {
                "type": "command_run",
                "evidenceId": "e1",
                "gate": "build/v1",
                "check": "c",
                "exitCode": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    gate = Gate(
        "build/v1", "implementation", (Check("c", "basis", "success"),), ("source",), ("pass",)
    )
    document = Document(
        title="T", inputs=[], evidence=[], receipts=[], subtasks=[], path=tmp_path / "task.md"
    )
    fingerprint = fingerprint_for_gate(document, gate, tmp_path, adapter)
    child = {
        "kind": "basis",
        "id": "e1",
        "gate": "build/v1",
        "check": "c",
        "issuerRole": "implementation",
        "artifactSha256": sha256(artifact),
        "inputFingerprint": fingerprint,
        "basisRef": "basis.jsonl",
        "scope": [],
        "classifiedRefs": [],
    }
    bundle = {
        "kind": "bundle",
        "id": "b",
        "gate": "build/v1",
        "issuerRole": "implementation",
        "checkEvidence": ["e1"],
        "inputFingerprint": fingerprint,
    }
    document.evidence = [child, bundle]
    document.receipts = [
        {
            "gate": "build/v1",
            "status": "pass",
            "evidence": "bundle=b",
            "fingerprint": fingerprint,
            "recordedAt": "now",
        }
    ]
    errors = validate(document, Profile("t", [gate]), adapters=[adapter], workspace_root=tmp_path)
    assert any(error.invariant == 9 for error in errors)


def test_basis_scope_must_cover_declared_inputs(tmp_path: Path):
    (tmp_path / "artifact.jsonl").write_text(
        json.dumps(
            {
                "type": "command_run",
                "evidenceId": "e1",
                "gate": "build/v1",
                "check": "c",
                "exitCode": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    artifact = tmp_path / "artifact.jsonl"
    gate = Gate(
        "build/v1", "implementation", (Check("c", "basis", "success"),), ("source",), ("pass",)
    )
    document = Document(
        title="T",
        inputs=[{"type": "source", "path": "src/app.py"}],
        evidence=[],
        receipts=[],
        subtasks=[],
        path=tmp_path / "task.md",
    )
    evidence = {
        "kind": "basis",
        "id": "e1",
        "gate": "build/v1",
        "check": "c",
        "issuerRole": "implementation",
        "scope": [],
        "classifiedRefs": [],
        "artifactSha256": sha256(artifact),
        "basisRef": "artifact.jsonl",
    }
    document.evidence = [evidence]
    errors = validate(document, Profile("t", [gate]), workspace_root=tmp_path)
    assert any(error.invariant == 2 and "coverage" in str(error) for error in errors)


def test_multi_record_command_artifact_is_rejected(tmp_path: Path):
    gate = Gate("build/v1", "implementation", (Check("c", "command", "success"),), (), ("pass",))
    document = Document(
        title="T", inputs=[], evidence=[], receipts=[], subtasks=[], path=tmp_path / "task.md"
    )
    artifact = tmp_path / "run.jsonl"
    record = {
        "type": "command_run",
        "evidenceId": "e1",
        "gate": "build/v1",
        "check": "c",
        "exitCode": 0,
    }
    artifact.write_text(json.dumps(record) + "\n" + json.dumps(record) + "\n", encoding="utf-8")
    document.evidence = [
        {
            "kind": "command",
            "id": "e1",
            "gate": "build/v1",
            "check": "c",
            "issuerRole": "implementation",
            "artifactSha256": sha256(artifact),
            "commandReceipt": "run.jsonl",
        }
    ]
    errors = validate(document, Profile("t", [gate]), workspace_root=tmp_path)
    assert any(error.invariant == 2 and "exactly one record" in str(error) for error in errors)


def test_directory_symlink_is_rejected(tmp_path: Path):
    source = tmp_path / "src"
    source.mkdir()
    target = source / "target"
    target.mkdir()
    (target / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (source / "linked").symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink inputs are not supported"):
        fingerprint_gate(tmp_path, [{"type": "source", "path": "src"}], types=["source"])


def test_validator_rejects_unhashable_bundle_member(tmp_path: Path):
    from acdd.adapter import Adapter, CheckBinding, GateBinding

    gate = Gate("build/v1", "implementation", (Check("c", "command", "success"),), (), ("pass",))
    document = Document(
        title="T", inputs=[], evidence=[], receipts=[], subtasks=[], path=tmp_path / "t.md"
    )
    adapter = Adapter(
        "implementation",
        "implementation",
        "artifacts",
        tmp_path,
        {"build/v1": GateBinding(checks={"c": CheckBinding(argv=("/bin/true",))})},
    )
    fingerprint = fingerprint_for_gate(document, gate, tmp_path, adapter)
    document.evidence = [
        {
            "kind": "bundle",
            "id": "b",
            "gate": "build/v1",
            "issuerRole": "implementation",
            "checkEvidence": [{}],
            "inputFingerprint": fingerprint,
        }
    ]
    document.receipts = [
        {
            "gate": "build/v1",
            "status": "pass",
            "evidence": "bundle=b",
            "fingerprint": fingerprint,
            "recordedAt": "now",
        }
    ]

    errors = validate(
        document, Profile("t", [gate]), adapters=[adapter], workspace_root=tmp_path
    )
    assert any(error.invariant == 2 and "invalid bundle members" in str(error) for error in errors)


def test_missing_executable_returns_error_not_traceback(core):
    doc, profile, adapter = core
    adapter.write_text(
        adapter.read_text(encoding="utf-8").replace(
            "argv: [python3, -c, \"print('green')\"]", "argv: [nonexistent-binary-xyz]"
        ),
        encoding="utf-8",
    )
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
                "build.runtime",
            ]
        )
        == 1
    )
    artifact_text = (doc.parent / "artifacts" / "build.runtime.jsonl").read_text(encoding="utf-8")
    assert json.loads(artifact_text)["exitCode"] == 127


def test_transitive_dependency_serializes_conflict(tmp_path: Path):
    gate = Gate("build/v1", "implementation", (Check("c", "command", "success"),), (), ("pass",))
    document = Document(
        title="T",
        inputs=[{"type": "source", "path": "x.py"}],
        evidence=[],
        receipts=[
            {
                "gate": "build/v1",
                "status": "pending",
                "evidence": "pending",
                "fingerprint": "pending",
                "recordedAt": "pending",
            }
        ],
        subtasks=[
            Subtask("a", ("x.py",), (), "A"),
            Subtask("b", (), (), "B", ("a",)),
            Subtask("c", ("x.py",), (), "C", ("b",)),
        ],
        path=tmp_path / "task.md",
    )
    errors = validate(document, Profile("t", [gate]), workspace_root=tmp_path)
    assert not any(error.invariant == 6 for error in errors)


def test_unserialized_conflict_still_rejected(tmp_path: Path):
    gate = Gate("build/v1", "implementation", (Check("c", "command", "success"),), (), ("pass",))
    document = Document(
        title="T",
        inputs=[{"type": "source", "path": "x.py"}],
        evidence=[],
        receipts=[
            {
                "gate": "build/v1",
                "status": "pending",
                "evidence": "pending",
                "fingerprint": "pending",
                "recordedAt": "pending",
            }
        ],
        subtasks=[
            Subtask("a", ("x.py",), (), "A"),
            Subtask("b", (), (), "B", ("a",)),
            Subtask("c", ("x.py",), (), "C"),
        ],
        path=tmp_path / "task.md",
    )
    errors = validate(document, Profile("t", [gate]), workspace_root=tmp_path)
    assert any(error.invariant == 6 for error in errors)


def test_cyclic_subtask_dependencies_rejected(tmp_path: Path):
    gate = Gate("build/v1", "implementation", (Check("c", "command", "success"),), (), ("pass",))
    document = Document(
        title="T",
        inputs=[],
        evidence=[],
        receipts=[
            {
                "gate": "build/v1",
                "status": "pending",
                "evidence": "pending",
                "fingerprint": "pending",
                "recordedAt": "pending",
            }
        ],
        subtasks=[Subtask("a", (), (), "A", ("b",)), Subtask("b", (), (), "B", ("a",))],
        path=tmp_path / "task.md",
    )
    errors = validate(document, Profile("t", [gate]), workspace_root=tmp_path)
    assert any(error.invariant == 6 and "acyclic" in str(error) for error in errors)


def test_record_review_resolves_transcript_against_workspace_root(tmp_path: Path, monkeypatch):
    monkeypatch.chdir("/tmp")
    (tmp_path / "a.yaml").write_text(
        """\
apiVersion: acdd/adapter/v1
id: r
role: review
gates:
  review/v1:
    checks:
      independent-review: {argv: [echo]}
""",
        encoding="utf-8",
    )
    adapter = load_adapter(tmp_path / "a.yaml")
    gate = Gate(
        "review/v1",
        "review",
        (Check("independent-review", "review", "success"),),
        (),
        ("pass",),
        (),
        ("parity", "security"),
    )
    transcript = tmp_path / "rev.jsonl"
    terminal = {
        "type": "review_terminal",
        "evidenceId": "r1",
        "gate": "review/v1",
        "check": "independent-review",
        "scope": ["src/"],
        "performedChecks": ["parity", "security"],
        "verdict": "pass",
        "authorSessionUuid": "00000000-0000-4000-8000-000000000001",
        "reviewerSessionUuid": "00000000-0000-4000-8000-000000000003",
        "reviewedSessionUuids": ["00000000-0000-4000-8000-000000000002"],
    }
    raw = _review_raw(raw="reviewer response without a machine-readable schema")
    confirmation = _review_raw(
        reviewer_uuid="00000000-0000-4000-8000-000000000003", raw="confirmation review: PASS"
    )
    document = Document(
        title="T", inputs=[], evidence=[], receipts=[], subtasks=[], path=tmp_path / "d.md"
    )
    document.path.write_text("---\ntitle: T\n---\n## Evidence\n\n## Receipts\n", encoding="utf-8")
    from acdd.record import record_review

    def write_transcript():
        transcript.write_text(
            "\n".join(json.dumps(row) for row in (raw, confirmation, terminal)) + "\n",
            encoding="utf-8",
        )

    write_transcript()
    with pytest.raises(AcddError, match="review transcript"):
        record_review(
            document=document,
            workspace_root=tmp_path,
            gate=gate,
            check_id="independent-review",
            evidence_id="r1",
            adapter=adapter,
            transcript=Path("rev.jsonl"),
            author_uuid="00000000-0000-4000-8000-000000000001",
            reviewer_uuid="00000000-0000-4000-8000-000000000003",
            verdict="pass",
        )
    terminal["reviewedSessionUuids"].append("00000000-0000-4000-8000-000000000003")
    terminal["verdict"] = "fail"
    write_transcript()
    with pytest.raises(AcddError, match="review_terminal"):
        record_review(
            document=document,
            workspace_root=tmp_path,
            gate=gate,
            check_id="independent-review",
            evidence_id="r1",
            adapter=adapter,
            transcript=Path("rev.jsonl"),
            author_uuid="00000000-0000-4000-8000-000000000001",
            reviewer_uuid="00000000-0000-4000-8000-000000000003",
            verdict="pass",
        )
    terminal["verdict"] = "pass"
    terminal["reviewerSessionUuid"] = "00000000-0000-4000-8000-000000000004"
    write_transcript()
    with pytest.raises(AcddError, match="session UUIDs"):
        record_review(
            document=document,
            workspace_root=tmp_path,
            gate=gate,
            check_id="independent-review",
            evidence_id="r1",
            adapter=adapter,
            transcript=Path("rev.jsonl"),
            author_uuid="00000000-0000-4000-8000-000000000001",
            reviewer_uuid="00000000-0000-4000-8000-000000000003",
            verdict="pass",
        )
    terminal["reviewerSessionUuid"] = "00000000-0000-4000-8000-000000000003"
    write_transcript()
    payload = record_review(
        document=document,
        workspace_root=tmp_path,
        gate=gate,
        check_id="independent-review",
        evidence_id="r1",
        adapter=adapter,
        transcript=Path("rev.jsonl"),
        author_uuid="00000000-0000-4000-8000-000000000001",
        reviewer_uuid="00000000-0000-4000-8000-000000000003",
        verdict="pass",
    )
    assert payload["transcriptRef"] == "rev.jsonl"
    assert payload["artifactSha256"] == sha256(transcript)


def test_non_dict_inputs_entry_is_a_clean_error(tmp_path: Path):
    (tmp_path / "d.md").write_text(
        """\
---
title: T
---
## Inputs
```yaml
paths:
  - just-a-string
```
## Receipts
""",
        encoding="utf-8",
    )
    with pytest.raises(AcddError, match="invalid Inputs entry"):
        load_document(tmp_path / "d.md")


def test_adapter_cwd_escape_is_rejected(core):
    doc, profile, adapter = core
    adapter.write_text(
        adapter.read_text(encoding="utf-8").replace("cwd: .", "cwd: /etc"), encoding="utf-8"
    )
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
                "build.runtime",
            ]
        )
        == 2
    )


def test_adapter_timeout_seconds_is_validated(tmp_path: Path):
    path = tmp_path / "a.yaml"
    path.write_text(
        """\
apiVersion: acdd/adapter/v1
id: x
role: implementation
gates:
  build/v1:
    checks:
      c: {argv: [/bin/true], timeoutSeconds: 0}
""",
        encoding="utf-8",
    )
    with pytest.raises(AdapterError, match="timeoutSeconds"):
        load_adapter(path)
    path.write_text(
        path.read_text(encoding="utf-8").replace("timeoutSeconds: 0", "timeoutSeconds: 5"),
        encoding="utf-8",
    )
    assert load_adapter(path).gates["build/v1"].checks["c"].timeout_seconds == 5


def test_adapter_rejects_non_string_artifact_dir(tmp_path: Path):
    path = tmp_path / "a.yaml"
    path.write_text(
        """
apiVersion: acdd/adapter/v1
id: x
role: implementation
artifactDir: []
gates: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(AdapterError, match="artifactDir"):
        load_adapter(path)


def test_partial_receipt_must_be_fully_pending(tmp_path: Path):
    gate = Gate("build/v1", "implementation", (Check("c", "command", "success"),), (), ("pass",))
    document = Document(
        title="T",
        inputs=[],
        evidence=[],
        receipts=[
            {
                "gate": "build/v1",
                "status": "partial",
                "evidence": "garbage",
                "fingerprint": "garbage",
                "recordedAt": "never",
            }
        ],
        subtasks=[],
        path=tmp_path / "task.md",
    )
    errors = validate(document, Profile("t", [gate]), workspace_root=tmp_path)
    assert any(error.invariant == 1 for error in errors)


def test_document_profile_mismatch_is_rejected(core):
    doc, profile, adapter = core
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "planning_profile: test/v1", "planning_profile: other/v1"
        ),
        encoding="utf-8",
    )
    errors = validate(
        load_document(doc),
        load_profile(profile),
        adapters=[load_adapter(adapter)],
        workspace_root=doc.parent,
    )
    assert any(error.invariant == 1 and "declares" in str(error) for error in errors)


def test_plan_edit_does_not_stale_receipt(core):
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
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "subtasks: []",
            """subtasks:
  - id: docs
    writes: [src/app.py]
    reads: []
    acceptance: guide written""",
        ),
        encoding="utf-8",
    )
    errors = validate(
        load_document(doc),
        load_profile(profile),
        adapters=[load_adapter(adapter)],
        workspace_root=doc.parent,
    )
    assert not any(error.invariant == 4 for error in errors)


def test_unrelated_input_type_does_not_stale_receipt(core):
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
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            """paths:
  - {type: source, path: src/app.py}""",
            """paths:
  - {type: source, path: src/app.py}
  - {type: docs, path: docs/guide.md}""",
        ),
        encoding="utf-8",
    )
    errors = validate(
        load_document(doc),
        load_profile(profile),
        adapters=[load_adapter(adapter)],
        workspace_root=doc.parent,
    )
    assert not any(error.invariant == 4 for error in errors)


def test_note_column_rules(tmp_path: Path):
    gate = Gate("build/v1", "implementation", (Check("c", "command", "success"),), (), ("pass",))
    profile = Profile("t", [gate])

    def errors_for(status: str, note: str | None):
        cells = ["build/v1", status, "pending", "pending", "pending"] + (
            [note] if note is not None else []
        )
        document = Document(
            title="T",
            inputs=[],
            evidence=[],
            receipts=[
                dict(
                    zip(("gate", "status", "evidence", "fingerprint", "recordedAt", "note"), cells)
                )
            ],
            subtasks=[],
            path=tmp_path / "t.md",
        )
        return validate(document, profile, workspace_root=tmp_path)

    assert not any(e.invariant == 1 for e in errors_for("blocked", "waiting on infra"))
    assert not any(e.invariant == 1 for e in errors_for("partial", None))
    assert any(e.invariant == 1 for e in errors_for("pending", "not allowed"))
    assert any(e.invariant == 1 for e in errors_for("blocked", ""))


def test_acdd_discovery_loads_adapters(core):
    doc, profile, adapter = core
    discovered = doc.parent / "sub" / ".acdd"
    discovered.mkdir(parents=True)
    (discovered / "impl.yaml").write_text(adapter.read_text(encoding="utf-8"), encoding="utf-8")
    args = [str(doc), str(profile), "--workspace-root", str(doc.parent)]
    assert (
        main(
            [
                "record",
                *args,
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
    assert main(["finalize", *args, "--gate", "build/v1", "--id", "build.bundle"]) == 0
    assert main(["validate", *args]) == 0


def test_acdd_discovery_rejects_duplicate_roles(core):
    doc, profile, adapter = core
    for name in ("one", "two"):
        directory = doc.parent / name / ".acdd"
        directory.mkdir(parents=True)
        (directory / "impl.yaml").write_text(adapter.read_text(encoding="utf-8"), encoding="utf-8")
    assert main(["validate", str(doc), str(profile), "--workspace-root", str(doc.parent)]) == 2


def test_adapter_outside_workspace_is_rejected(core):
    doc, profile, _adapter = core
    assert (
        main(
            [
                "validate",
                str(doc),
                str(profile),
                "--workspace-root",
                str(doc.parent),
                "--adapter",
                "implementation=/etc/passwd",
            ]
        )
        == 2
    )


def test_discovery_prunes_vendor_dirs(core):
    doc, _profile, adapter = core
    stray = doc.parent / ".venv" / "lib" / ".acdd"
    stray.mkdir(parents=True)
    (stray / "stray.yaml").write_text(adapter.read_text(encoding="utf-8"), encoding="utf-8")
    from acdd.cli import _discover

    assert _discover(doc.parent) == []
    nested = doc.parent / "pkg" / ".acdd"
    nested.mkdir(parents=True)
    (nested / "impl.yaml").write_text(adapter.read_text(encoding="utf-8"), encoding="utf-8")
    assert _discover(doc.parent) == [nested / "impl.yaml"]


def test_overflow_receipt_row_is_a_shape_error(core):
    doc, profile, adapter = core
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "| build/v1 | pending | pending | pending | pending |",
            "| build/v1 | pending | pending | pending | pending | note | junk |",
        ),
        encoding="utf-8",
    )
    errors = validate(
        load_document(doc),
        load_profile(profile),
        adapters=[load_adapter(adapter)],
        workspace_root=doc.parent,
    )
    assert any(error.invariant == 1 for error in errors)


def test_review_dimensions_required_in_transcript(tmp_path: Path):
    (tmp_path / "p.yaml").write_text(
        """\
apiVersion: acdd/profile/v1
kind: profile
id: t
gates:
  - id: review/v1
    owner: review
    checks:
      - {id: independent-review, evidenceKind: review}
    invalidatesOn: []
    reviewDimensions: [parity, security]
    terminals: [pass]
""",
        encoding="utf-8",
    )
    (tmp_path / "a.yaml").write_text(
        """\
apiVersion: acdd/adapter/v1
id: r
role: review
gates:
  review/v1:
    checks:
      independent-review: {argv: [pi, --print, "{prompt}"]}
""",
        encoding="utf-8",
    )
    (tmp_path / "d.md").write_text(
        "---\ntitle: T\n---\n## Evidence\n\n## Receipts\n", encoding="utf-8"
    )
    adapter = load_adapter(tmp_path / "a.yaml")
    gate = Gate(
        "review/v1",
        "review",
        (Check("independent-review", "review", "success"),),
        (),
        ("pass",),
        (),
        ("parity", "security"),
    )
    transcript = tmp_path / "rev.jsonl"
    raw = _review_raw()
    terminal = {
        "type": "review_terminal",
        "evidenceId": "r1",
        "gate": "review/v1",
        "check": "independent-review",
        "scope": ["src/"],
        "performedChecks": ["parity"],
        "verdict": "pass",
        "authorSessionUuid": "00000000-0000-4000-8000-000000000001",
        "reviewerSessionUuid": "00000000-0000-4000-8000-000000000002",
        "reviewedSessionUuids": ["00000000-0000-4000-8000-000000000002"],
    }
    transcript.write_text(
        "\n".join(json.dumps(row) for row in (raw, terminal)) + "\n", encoding="utf-8"
    )
    from acdd.record import record_review

    document = Document(
        title="T", inputs=[], evidence=[], receipts=[], subtasks=[], path=tmp_path / "d.md"
    )
    with pytest.raises(AcddError, match="covering"):
        record_review(
            document=document,
            workspace_root=tmp_path,
            gate=gate,
            check_id="independent-review",
            evidence_id="r1",
            adapter=adapter,
            transcript=transcript,
            author_uuid="00000000-0000-4000-8000-000000000001",
            reviewer_uuid="00000000-0000-4000-8000-000000000002",
            verdict="pass",
        )
    terminal["performedChecks"] = ["parity", "security", "performance"]
    transcript.write_text(
        "\n".join(json.dumps(row) for row in (raw, terminal)) + "\n", encoding="utf-8"
    )
    record_review(
        document=document,
        workspace_root=tmp_path,
        gate=gate,
        check_id="independent-review",
        evidence_id="r1",
        adapter=adapter,
        transcript=transcript,
        author_uuid="00000000-0000-4000-8000-000000000001",
        reviewer_uuid="00000000-0000-4000-8000-000000000002",
        verdict="pass",
    )


def test_discovery_rejects_unknown_check_on_active_gate(core):
    doc, profile, _adapter = core
    (doc.parent / "side" / ".acdd").mkdir(parents=True)
    (doc.parent / "side" / ".acdd" / "x.yaml").write_text(
        """\
apiVersion: acdd/adapter/v1
id: stray
role: implementation
gates:
  build/v1:
    checks:
      c: {argv: [/bin/true]}
  mystery/v1:
    checks:
      c: {argv: [/bin/true]}
""",
        encoding="utf-8",
    )
    buf = io.StringIO()
    original, sys.stderr = sys.stderr, buf
    try:
        rc = main(["validate", str(doc), str(profile), "--workspace-root", str(doc.parent)])
    finally:
        sys.stderr = original
    assert rc == 1
    err = buf.getvalue()
    assert "invariant 5" in err
    assert "unknown check" in err


def test_discovery_ignores_adapters_for_inactive_profile_roles(core):
    doc, profile, adapter = core
    (doc.parent / "plan" / ".acdd").mkdir(parents=True)
    (doc.parent / "plan" / ".acdd" / "plan.yaml").write_text(
        """\
apiVersion: acdd/adapter/v1
id: plan
role: plan
gates:
  decompose/v1:
    checks:
      matrix: {argv: [/bin/true]}
""",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "validate",
                str(doc),
                str(profile),
                "--workspace-root",
                str(doc.parent),
                "--adapter",
                f"implementation={adapter}",
            ]
        )
        == 0
    )


def test_profile_rejects_review_dimensions_without_review_check(tmp_path: Path):
    path = tmp_path / "p.yaml"
    path.write_text(
        """\
apiVersion: acdd/profile/v1
kind: profile
id: t
gates:
  - id: build/v1
    owner: implementation
    checks:
      - {id: c, evidenceKind: command}
    invalidatesOn: []
    reviewDimensions: [parity]
    terminals: [pass]
""",
        encoding="utf-8",
    )
    with pytest.raises(AcddError, match="reviewDimensions"):
        load_profile(path)


def test_review_transcript_non_string_elements_rejected(tmp_path: Path):
    gate = Gate(
        "review/v1",
        "review",
        (Check("independent-review", "review", "success"),),
        (),
        ("pass",),
        (),
        ("parity", "security"),
    )
    artifact = tmp_path / "rev.jsonl"
    terminal = {
        "type": "review_terminal",
        "evidenceId": "r1",
        "gate": "review/v1",
        "check": "independent-review",
        "scope": ["src/"],
        "performedChecks": [42, 42, "parity"],
        "verdict": "pass",
        "authorSessionUuid": "00000000-0000-4000-8000-000000000001",
        "reviewerSessionUuid": "00000000-0000-4000-8000-000000000002",
        "reviewedSessionUuids": ["00000000-0000-4000-8000-000000000002"],
    }
    artifact.write_text(
        "\n".join(json.dumps(row) for row in (_review_raw(), terminal)) + "\n", encoding="utf-8"
    )
    document = Document(
        title="T",
        inputs=[],
        evidence=[
            {
                "kind": "review",
                "id": "r1",
                "gate": "review/v1",
                "check": "independent-review",
                "issuerRole": "review",
                "transcriptRef": "rev.jsonl",
                "artifactSha256": sha256(artifact),
                "authorSessionUuid": "00000000-0000-4000-8000-000000000001",
                "reviewerSessionUuid": "00000000-0000-4000-8000-000000000002",
                "verdict": "pass",
            }
        ],
        receipts=[],
        subtasks=[],
        path=tmp_path / "t.md",
    )
    errors = validate(document, Profile("t", [gate]), workspace_root=tmp_path)
    assert any(error.invariant == 11 for error in errors)
    artifact.write_text("not JSON\n", encoding="utf-8")
    errors = validate(document, Profile("t", [gate]), workspace_root=tmp_path)
    assert any(error.invariant == 2 for error in errors)


def test_discovery_rejects_symlinked_adapter_files(tmp_path: Path):
    import os

    real = tmp_path / "real.yaml"
    real.write_text("apiVersion: acdd/adapter/v1\nid: x\nrole: task\ngates: {}", encoding="utf-8")
    (tmp_path / ".acdd").mkdir()
    lnk = tmp_path / ".acdd" / "x.yaml"
    os.symlink(real, lnk)
    from acdd.cli import _discover

    assert _discover(tmp_path) == []


def test_failed_record_allows_retry_same_id(core):
    doc, profile, adapter = core
    adapter.write_text(
        adapter.read_text(encoding="utf-8").replace(
            "argv: [python3, -c, \"print('green')\"]",
            'argv: [python3, -c, "import sys; sys.exit(1)"]',
        ),
        encoding="utf-8",
    )
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
                "build.retry",
            ]
        )
        == 1
    )
    assert (doc.parent / "artifacts" / "build.retry.jsonl").is_file()
    adapter.write_text(
        adapter.read_text(encoding="utf-8").replace(
            'argv: [python3, -c, "import sys; sys.exit(1)"]',
            "argv: [python3, -c, \"print('green')\"]",
        ),
        encoding="utf-8",
    )
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
                "build.retry",
            ]
        )
        == 0
    )


def test_expected_failure_rejects_reserved_exit_codes(tmp_path: Path):
    artifact = tmp_path / "run.jsonl"
    artifact.write_text(
        json.dumps(
            {
                "type": "command_run",
                "evidenceId": "e1",
                "gate": "build/v1",
                "check": "c",
                "exitCode": 124,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    gate = Gate(
        "build/v1", "implementation", (Check("c", "command", "expected-failure"),), (), ("pass",)
    )
    document = Document(
        title="T",
        inputs=[],
        evidence=[
            {
                "kind": "command",
                "id": "e1",
                "gate": "build/v1",
                "check": "c",
                "issuerRole": "implementation",
                "artifactSha256": sha256(artifact),
                "commandReceipt": "run.jsonl",
            }
        ],
        receipts=[],
        subtasks=[],
        path=tmp_path / "t.md",
    )
    errors = validate(document, Profile("t", [gate]), workspace_root=tmp_path)
    assert any(error.invariant == 9 for error in errors)


def test_record_review_rejects_non_terminal_type(tmp_path: Path):
    (tmp_path / "a.yaml").write_text(
        """\
apiVersion: acdd/adapter/v1
id: r
role: review
gates:
  review/v1:
    checks:
      independent-review: {argv: [echo]}
""",
        encoding="utf-8",
    )
    adapter = load_adapter(tmp_path / "a.yaml")
    gate = Gate(
        "review/v1",
        "review",
        (Check("independent-review", "review", "success"),),
        (),
        ("pass",),
        (),
        ("parity",),
    )
    transcript = tmp_path / "rev.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "type": "command_run",
                "evidenceId": "r1",
                "gate": "review/v1",
                "check": "independent-review",
                "scope": ["src/"],
                "performedChecks": ["parity"],
                "exitCode": 0,
                "verdict": "pass",
                "authorSessionUuid": "00000000-0000-4000-8000-000000000001",
                "reviewerSessionUuid": "00000000-0000-4000-8000-000000000002",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    document = Document(
        title="T", inputs=[], evidence=[], receipts=[], subtasks=[], path=tmp_path / "d.md"
    )
    document.path.write_text("---\ntitle: T\n---\n## Evidence\n\n## Receipts\n", encoding="utf-8")
    from acdd.record import record_review

    with pytest.raises(AcddError, match="review_terminal"):
        record_review(
            document=document,
            workspace_root=tmp_path,
            gate=gate,
            check_id="independent-review",
            evidence_id="r1",
            adapter=adapter,
            transcript=transcript,
            author_uuid="00000000-0000-4000-8000-000000000001",
            reviewer_uuid="00000000-0000-4000-8000-000000000002",
            verdict="pass",
        )


def test_terminal_gate_requires_prior_gates(tmp_path: Path):
    profile = Profile(
        "t",
        [
            Gate("design/v1", "task", (Check("c", "command", "success"),), (), ("pass",)),
            Gate("build/v1", "implementation", (Check("c", "command", "success"),), (), ("pass",)),
        ],
    )
    document = Document(
        title="T",
        inputs=[],
        evidence=[],
        receipts=[
            {
                "gate": "design/v1",
                "status": "pending",
                "evidence": "pending",
                "fingerprint": "pending",
                "recordedAt": "pending",
            },
            {
                "gate": "build/v1",
                "status": "pass",
                "evidence": "bundle=b",
                "fingerprint": "fp",
                "recordedAt": "now",
            },
        ],
        subtasks=[],
        path=tmp_path / "t.md",
    )
    errors = validate(document, profile, workspace_root=tmp_path)
    assert any(error.invariant == 1 and "prior gate" in str(error) for error in errors)


def test_duplicate_check_evidence_rejected_on_record(core):
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
                "build.one",
            ]
        )
        == 0
    )
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
                "build.two",
            ]
        )
        == 2
    )


def test_inapplicable_rejects_check_evidence(core):
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
                "--status",
                "inapplicable",
                "--reason-code",
                "build.no-runnable-source",
            ]
        )
        == 2
    )


def test_inapplicable_with_empty_bundle_passes(core):
    doc, profile, adapter = core
    assert (
        main(
            [
                "finalize",
                *_args(doc, profile, adapter),
                "--gate",
                "build/v1",
                "--id",
                "build.inapp",
                "--status",
                "inapplicable",
                "--reason-code",
                "build.no-runnable-source",
            ]
        )
        == 0
    )
    assert (
        validate(
            load_document(doc),
            load_profile(profile),
            adapters=[load_adapter(adapter)],
            workspace_root=doc.parent,
        )
        == []
    )


def test_profile_rejects_scalar_invalidates_on(tmp_path: Path):
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        """
apiVersion: acdd/profile/v1
kind: profile
id: t
gates:
  - id: build/v1
    owner: implementation
    checks: [{id: c, evidenceKind: command}]
    invalidatesOn: source
    terminals: [pass]
""",
        encoding="utf-8",
    )
    with pytest.raises(AcddError, match="invalidatesOn"):
        load_profile(profile)


def test_cli_reports_malformed_profile_yaml(tmp_path: Path, capsys):
    profile = tmp_path / "profile.yaml"
    profile.write_text("gates: [", encoding="utf-8")
    assert main(["validate", str(tmp_path / "missing.md"), str(profile)]) == 2
    assert "ACDD ERROR:" in capsys.readouterr().err


def test_finalize_rejects_missing_predecessor_receipt(core):
    doc, profile, adapter = core
    profile.write_text(
        """
apiVersion: acdd/profile/v1
kind: profile
id: test/v1
gates:
  - id: design/v1
    owner: task
    checks: [{id: c, evidenceKind: command}]
    invalidatesOn: []
    terminals: [pass]
  - id: build/v1
    owner: implementation
    checks: [{id: runtime-and-integration, evidenceKind: command}]
    invalidatesOn: [source]
    terminals: [pass, inapplicable]
    inapplicableReasonCodes: [build.no-runnable-source]
""",
        encoding="utf-8",
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
                "--status",
                "inapplicable",
                "--reason-code",
                "build.no-runnable-source",
            ]
        )
        == 2
    )
    assert "build.bundle" not in doc.read_text(encoding="utf-8")


def test_finalize_rejects_tampered_current_evidence(core):
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
    (doc.parent / "artifacts" / "build.check.jsonl").write_text("tampered\n", encoding="utf-8")
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
        == 2
    )
    assert "build.bundle" not in doc.read_text(encoding="utf-8")


def test_finalize_rejects_terminal_gate(core):
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
    assert (
        main(
            [
                "finalize",
                *_args(doc, profile, adapter),
                "--gate",
                "build/v1",
                "--id",
                "build.second",
            ]
        )
        == 2
    )


def test_finalize_replaces_stale_terminal_gate(core):
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
                "build.before",
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
                "build.before.bundle",
            ]
        )
        == 0
    )
    (doc.parent / "src" / "app.py").write_text("print('fixed')\n", encoding="utf-8")
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
                "build.after",
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
                "build.after.bundle",
            ]
        )
        == 0
    )
    assert (
        validate(
            load_document(doc),
            load_profile(profile),
            adapters=[load_adapter(adapter)],
            workspace_root=doc.parent,
        )
        == []
    )


def test_command_outcome_rejects_boolean_exit_code():
    assert not command_outcome_ok(
        Check("c", "command", "success"), {"type": "command_run", "exitCode": False}
    )
