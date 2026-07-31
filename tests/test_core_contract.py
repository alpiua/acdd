"""End-to-end regressions for the stable ACDD v2 core contract."""
from __future__ import annotations

from pathlib import Path

from acdd.cli import main
from acdd.model import load_document, load_profile
from acdd.validate import validate


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _args(doc: Path, profile: Path, adapter: Path) -> list[str]:
    return [str(doc), str(profile), "--workspace-root", str(doc.parent),
            "--adapter", f"implementation={adapter}"]


def test_record_finalize_validate_round_trip(core):
    doc, profile, adapter = core
    assert main(["record", *_args(doc, profile, adapter), "--gate", "build/v1",
                 "--check", "runtime-and-integration", "--id", "build.runtime"]) == 0
    assert main(["finalize", *_args(doc, profile, adapter), "--gate", "build/v1",
                 "--id", "build.bundle"]) == 0
    assert main(["validate", *_args(doc, profile, adapter)]) == 0


def test_failed_command_never_creates_pass_receipt(core):
    doc, profile, adapter = core
    text = adapter.read_text(encoding="utf-8").replace("print('green')", "raise SystemExit(3)")
    adapter.write_text(text, encoding="utf-8")
    assert main(["record", *_args(doc, profile, adapter), "--gate", "build/v1",
                 "--check", "runtime-and-integration", "--id", "build.runtime"]) == 1
    assert "| build/v1 | pending | pending | pending | pending |" in doc.read_text(encoding="utf-8")


def test_tampered_artifact_invalidates_final_receipt(core):
    doc, profile, adapter = core
    assert main(["record", *_args(doc, profile, adapter), "--gate", "build/v1",
                 "--check", "runtime-and-integration", "--id", "build.runtime"]) == 0
    assert main(["finalize", *_args(doc, profile, adapter), "--gate", "build/v1",
                 "--id", "build.bundle"]) == 0
    artifact = doc.parent / "artifacts" / "build.runtime.jsonl"
    artifact.write_text("tampered\n", encoding="utf-8")
    errors = validate(load_document(doc), load_profile(profile),
                      adapters=[], workspace_root=doc.parent)
    assert any(error.invariant == 2 for error in errors)


def test_expected_failure_accepts_nonzero_only(core):
    doc, profile, adapter = core
    profile.write_text(profile.read_text(encoding="utf-8").replace(
        "commandOutcome: success", "commandOutcome: expected-failure"), encoding="utf-8")
    adapter.write_text(adapter.read_text(encoding="utf-8").replace(
        "print('green')", "raise SystemExit(1)"), encoding="utf-8")
    assert main(["record", *_args(doc, profile, adapter), "--gate", "build/v1",
                 "--check", "runtime-and-integration", "--id", "build.runtime"]) == 0


def test_expected_failure_rejects_zero_exit(core):
    doc, profile, adapter = core
    profile.write_text(profile.read_text(encoding="utf-8").replace(
        "commandOutcome: success", "commandOutcome: expected-failure"), encoding="utf-8")
    assert main(["record", *_args(doc, profile, adapter), "--gate", "build/v1",
                 "--check", "runtime-and-integration", "--id", "build.runtime"]) == 1
    assert "build.runtime" not in doc.read_text(encoding="utf-8")


def test_adapter_artifact_escape_is_rejected(core):
    doc, profile, adapter = core
    adapter.write_text(adapter.read_text(encoding="utf-8").replace("artifactDir: artifacts", "artifactDir: ../outside"), encoding="utf-8")
    assert main(["record", *_args(doc, profile, adapter), "--gate", "build/v1",
                 "--check", "runtime-and-integration", "--id", "build.runtime"]) == 2


def test_adapter_prompt_change_stales_receipt(core):
    doc, profile, adapter = core
    (doc.parent / "prompts").mkdir()
    prompt = doc.parent / "prompts" / "build.md"
    prompt.write_text("Check the local runtime contract.\n", encoding="utf-8")
    adapter.write_text(adapter.read_text(encoding="utf-8").replace(
        "argv: [python3, -c, \"print('green')\"]", "argv: [python3, -c, \"print('green')\"]\n        promptAppend: prompts/build.md"), encoding="utf-8")
    assert main(["record", *_args(doc, profile, adapter), "--gate", "build/v1",
                 "--check", "runtime-and-integration", "--id", "build.runtime"]) == 0
    assert main(["finalize", *_args(doc, profile, adapter), "--gate", "build/v1",
                 "--id", "build.bundle"]) == 0
    prompt.write_text("Check the changed local runtime contract.\n", encoding="utf-8")
    assert main(["validate", *_args(doc, profile, adapter)]) == 1


def test_directory_child_changes_fingerprint(tmp_path: Path):
    from acdd.fingerprint import fingerprint_gate

    directory = tmp_path / "src"
    directory.mkdir()
    _write(directory / "one.py", "one\n")
    inputs = [{"type": "source", "path": "src"}]
    first = fingerprint_gate(tmp_path, inputs, types=["source"]).sha256
    _write(directory / "two.py", "two\n")
    assert fingerprint_gate(tmp_path, inputs, types=["source"]).sha256 != first
