"""Unit tests for markdown_gate_check and contractSections extraction."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from acdd._doc import extract_sections
from acdd.adapter import load_adapter
from acdd.fingerprint import fingerprint_for_gate
from acdd.model import Check, Document, Gate, load_profile


def test_extract_sections_stops_at_h2_keeps_h3(tmp_path: Path):
    path = tmp_path / "doc.md"
    path.write_text(
        "# Title\n\n## Task execution contract\n\nmatrix row\n\n### Nested\n\nkeep me\n\n## Other\n\nout\n",
        encoding="utf-8",
    )
    sections = extract_sections(path, ("Task execution contract",))
    body = sections["Task execution contract"]
    assert "matrix row" in body
    assert "### Nested" in body
    assert "keep me" in body
    assert "## Other" not in body
    assert "out" not in body


def test_extract_sections_missing_heading_fails(tmp_path: Path):
    path = tmp_path / "doc.md"
    path.write_text("## Present\n\nok\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing headings"):
        extract_sections(path, ("Absent",))


def test_markdown_gate_check_forbid_multiline(tmp_path: Path, ROOT: Path):
    doc = tmp_path / "doc.md"
    doc.write_text("## Scope\n\nTODO: fix later\n", encoding="utf-8")
    script = ROOT / "acdd" / "share" / "scripts" / "markdown_gate_check.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            str(doc),
            "--require-section",
            "Scope",
            "--forbid-in-section",
            "Scope",
            r"^TODO:",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "forbidden pattern" in result.stderr


def test_contract_sections_change_stales_fingerprint(tmp_path: Path):
    doc_path = tmp_path / "task.md"
    doc_path.write_text(
        "---\ntitle: t\n---\n## Contract body\n\nv1\n",
        encoding="utf-8",
    )
    adapter_path = tmp_path / "task.yaml"
    adapter_path.write_text(
        """\
apiVersion: acdd/adapter/v1
id: task
role: task
gates:
  design/v1:
    contractSections: [Contract body]
    checks:
      design-basis: {argv: [/bin/true]}
""",
        encoding="utf-8",
    )
    adapter = load_adapter(adapter_path)
    gate = Gate(
        "design/v1",
        "task",
        (Check("design-basis", "basis", "success"),),
        ("structure",),
        ("pass",),
    )
    document = Document(
        title="t",
        inputs=[{"type": "structure", "path": "task.md"}],
        evidence=[],
        receipts=[],
        subtasks=[],
        path=doc_path,
    )
    first = fingerprint_for_gate(document, gate, tmp_path, adapter)
    doc_path.write_text(
        "---\ntitle: t\n---\n## Contract body\n\nv2 changed\n",
        encoding="utf-8",
    )
    second = fingerprint_for_gate(document, gate, tmp_path, adapter)
    assert first != second


def test_task_profile_check_owners(ROOT: Path):
    profile = load_profile(ROOT / "profiles" / "task" / "v1.yaml")
    contract = next(gate for gate in profile.gates if gate.id == "contract/v1")
    verify = next(check for check in contract.checks if check.id == "contract-verify")
    assert verify.owner == "contract-verify"
    assert verify.evidence_kind == "review"
