from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "build_input_set.py"
SPEC = importlib.util.spec_from_file_location("build_input_set", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write_inputs(root: Path) -> None:
    (root / "task.md").write_text(
        "# Task\n\ncontract\n\n## G0 independent verification\nold receipt\n\n"
        "## ACDD receipts\nold table\n\n## Execution gates\n- [ ] G0 gate contract\n",
        encoding="utf-8",
    )
    for kind in sorted(MODULE.KINDS - {"task"}):
        (root / f"{kind}.txt").write_text(f"{kind}\n", encoding="utf-8")


def _spec() -> dict[str, object]:
    components: list[dict[str, object]] = []
    for kind in sorted(MODULE.KINDS):
        if kind == "task":
            files = [
                {
                    "path": "task.md",
                    "excludeMarkdownSections": [
                        "G0 independent verification",
                        "ACDD receipts",
                    ],
                    "normalizeMarkdownCheckboxesInSections": ["Execution gates"],
                }
            ]
        else:
            files = [{"path": f"{kind}.txt"}]
        components.append(
            {
                "kind": kind,
                "id": f"fixture:{kind}",
                "files": files,
                "gitHeads": [],
            }
        )
    return {"schema": MODULE.SPEC_SCHEMA, "components": components}


def test_receipt_only_markdown_changes_do_not_change_fingerprint(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    manifest_before, details_before = MODULE.build_input_set(_spec(), root=tmp_path)

    task = tmp_path / "task.md"
    task.write_text(
        task.read_text(encoding="utf-8")
        .replace("old receipt", "new receipt")
        .replace("old table", "new table"),
        encoding="utf-8",
    )
    manifest_after, details_after = MODULE.build_input_set(_spec(), root=tmp_path)

    assert manifest_after == manifest_before
    assert details_after["inputFingerprint"] == details_before["inputFingerprint"]


def test_gate_completion_checkbox_does_not_change_fingerprint(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    _, details_before = MODULE.build_input_set(_spec(), root=tmp_path)

    task = tmp_path / "task.md"
    task.write_text(task.read_text(encoding="utf-8").replace("- [ ] G0", "- [x] G0"), encoding="utf-8")
    _, details_after = MODULE.build_input_set(_spec(), root=tmp_path)

    assert details_after["inputFingerprint"] == details_before["inputFingerprint"]


def test_gate_contract_text_change_invalidates_fingerprint(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    _, details_before = MODULE.build_input_set(_spec(), root=tmp_path)

    task = tmp_path / "task.md"
    task.write_text(task.read_text(encoding="utf-8").replace("G0 gate contract", "changed gate contract"), encoding="utf-8")
    _, details_after = MODULE.build_input_set(_spec(), root=tmp_path)

    assert details_after["inputFingerprint"] != details_before["inputFingerprint"]


def test_task_contract_change_invalidates_fingerprint(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    _, details_before = MODULE.build_input_set(_spec(), root=tmp_path)

    task = tmp_path / "task.md"
    task.write_text(task.read_text(encoding="utf-8").replace("contract", "changed contract"), encoding="utf-8")
    _, details_after = MODULE.build_input_set(_spec(), root=tmp_path)

    assert details_after["inputFingerprint"] != details_before["inputFingerprint"]


def test_git_head_is_typed_component_input(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    spec = _spec()
    environment = next(
        component for component in spec["components"] if component["kind"] == "environment"
    )
    environment["gitHeads"] = ["."]

    _, details = MODULE.build_input_set(spec, root=tmp_path)
    environment_detail = next(
        component for component in details["components"] if component["kind"] == "environment"
    )

    assert any(entry["type"] == "git-head" for entry in environment_detail["entries"])


def test_missing_excluded_section_fails_closed(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    spec = _spec()
    task = next(component for component in spec["components"] if component["kind"] == "task")
    task["files"][0]["excludeMarkdownSections"].append("Missing section")

    with pytest.raises(MODULE.InputSpecError, match="missing excluded Markdown sections"):
        MODULE.build_input_set(spec, root=tmp_path)


def test_path_escape_fails_closed(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    spec = _spec()
    source = next(component for component in spec["components"] if component["kind"] == "source")
    source["files"] = [{"path": "../outside"}]

    with pytest.raises(MODULE.InputSpecError, match="escapes --root"):
        MODULE.build_input_set(spec, root=tmp_path)
