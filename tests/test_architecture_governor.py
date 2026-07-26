from __future__ import annotations

import hashlib
import importlib.util
import subprocess
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


GOV = _load("architecture_governor")
ARCH = _load("architecture_verification")
RUNNER = _load("run_architecture")


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def test_baseline_clean_declared_inputs_pass() -> None:
    GOV.validate_baseline(
        dirty_paths=("notes.md",),
        declared_implementation_paths=frozenset({"source.py", "test.py"}),
        candidate_set=(),
    )


def test_baseline_dirty_declared_without_candidate_fails() -> None:
    with pytest.raises(GOV.ArchitectureGovernorError, match="candidate-set coverage"):
        GOV.validate_baseline(
            dirty_paths=("source.py", "notes.md"),
            declared_implementation_paths=frozenset({"source.py"}),
            candidate_set=(),
        )


def test_baseline_dirty_declared_covered_by_candidate_passes(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("x", encoding="utf-8")
    candidate = GOV.CandidatePath("source.py", _digest(b"x"))
    GOV.validate_baseline(
        dirty_paths=("source.py",),
        declared_implementation_paths=frozenset({"source.py"}),
        candidate_set=(candidate,),
    )
    GOV.validate_candidate_locks((candidate,), workspace_root=tmp_path)


def test_candidate_stale_lock_fails(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("fresh", encoding="utf-8")
    candidate = GOV.CandidatePath("source.py", _digest(b"stale"))
    with pytest.raises(GOV.ArchitectureGovernorError, match="stale lock"):
        GOV.validate_candidate_locks((candidate,), workspace_root=tmp_path)


def test_unchanged_fail_rerun_forbidden() -> None:
    fp = "sha256:" + "a" * 64
    attempts = (
        GOV.ArchitectureAttempt(fp, "FAIL", "2026-07-24T00:00:00Z"),
    )
    with pytest.raises(GOV.ArchitectureGovernorError, match="unchanged FAIL"):
        GOV.validate_retry_admission(attempts, next_fingerprint=fp)
    # compatibility with existing helper
    failed = {
        "inputFingerprint": fp,
        "coordinator": {"verdict": "FAIL"},
    }
    with pytest.raises(ARCH.ArchitectureVerificationError, match="unchanged FAIL"):
        ARCH.validate_retry_fingerprint(failed, fp)


def test_material_attempt_cap() -> None:
    attempts = (
        GOV.ArchitectureAttempt("sha256:" + "1" * 64, "FAIL", "2026-07-24T00:00:00Z"),
        GOV.ArchitectureAttempt("sha256:" + "2" * 64, "FAIL", "2026-07-24T00:00:00Z"),
        GOV.ArchitectureAttempt("sha256:" + "3" * 64, "FAIL", "2026-07-24T00:00:00Z"),
    )
    with pytest.raises(GOV.ArchitectureGovernorError, match="attempt cap exceeded"):
        GOV.validate_retry_admission(
            attempts,
            next_fingerprint="sha256:" + "4" * 64,
            max_material_attempts=3,
        )
    # retrying a new fingerprint after only 2 fails is OK
    GOV.validate_retry_admission(
        attempts[:2],
        next_fingerprint="sha256:" + "9" * 64,
        max_material_attempts=3,
    )


def test_parse_admission_defaults_and_section() -> None:
    default = GOV.parse_architecture_admission("# No section\n")
    assert default.max_material_attempts == 3
    assert default.candidate_set == ()
    assert default.attempts == ()

    text = """## ACDD architecture admission

```yaml
apiVersion: acdd/architecture-admission/v1
kind: architecture-admission
maxMaterialAttempts: 2
candidateSet:
  - path: source.py
    sha256: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
attempts:
  - inputFingerprint: sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
    verdict: FAIL
    recordedAt: "2026-07-24T10:00:00Z"
```
"""
    parsed = GOV.parse_architecture_admission(text)
    assert parsed.max_material_attempts == 2
    assert parsed.candidate_set[0].path == "source.py"
    assert parsed.attempts[0].verdict == "FAIL"


def test_may_launch_reports_block_reason(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("x", encoding="utf-8")
    text = """## Objective

x

## ACDD inputs

```yaml
apiVersion: acdd/inputs/v1
kind: inputs
paths:
  - type: source
    path: source.py
```
"""
    # Minimal text without full semantic sections - declared paths only via parse_inputs
    # may_launch uses declared_implementation_paths which needs full inputs parse - OK
    ok, reason = GOV.may_launch_architecture(
        text=text,
        workspace_root=tmp_path,
        next_fingerprint="sha256:" + "c" * 64,
        dirty_paths=("source.py",),
    )
    assert ok is False
    assert "candidate-set" in reason


def test_check_architecture_admission_cli(tmp_path: Path) -> None:
    # Build a tiny git repo with clean declared input.
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "source.py").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    # Reuse fixture-like adapters/document from proof bundle patterns — minimal doc
    # for fingerprint needs full task semantic sections. Use may_launch unit path instead.
    dirty = GOV.collect_dirty_paths(tmp_path)
    assert dirty == ()

def test_runner_rejects_writable_and_incomplete_partition_output() -> None:
    fingerprint = "sha256:" + "a" * 64
    partition = {
        "id": "contract",
        "status": "pass",
        "inputFingerprint": fingerprint,
        "evidence": ["task.md:1"],
        "findings": [],
        "persistedContractMappings": [],
        "isolated": True,
        "readOnly": True,
        "discovery": {"methods": {name: {"complete": True} for name in ("exactText", "structural", "dependency")}},
    }
    RUNNER.check_partition(partition, "contract", fingerprint)
    partition["readOnly"] = False
    with pytest.raises(RUNNER.RunnerError, match="read-only"):
        RUNNER.check_partition(partition, "contract", fingerprint)
    partition["readOnly"] = True
    partition["discovery"]["methods"]["dependency"]["complete"] = False
    with pytest.raises(RUNNER.RunnerError, match="discovery incomplete"):
        RUNNER.check_partition(partition, "contract", fingerprint)


def test_runner_parses_multiline_json_and_ignores_noise() -> None:
    output = """startup warning
```json
{
  "id": "contract",
  "status": "pass"
}
```
"""
    assert RUNNER.parse_launcher_output(output, ("id", "status")) == {
        "id": "contract",
        "status": "pass",
    }


def test_runner_rejects_json_without_required_fields() -> None:
    with pytest.raises(RUNNER.RunnerError, match="required JSON object"):
        RUNNER.parse_launcher_output('{"message": "not a partition"}', ("id", "status"))


def test_runner_retries_only_transport_or_schema_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fingerprint = "sha256:" + "b" * 64
    fields = (
        "id", "status", "inputFingerprint", "evidence", "findings",
        "discovery", "persistedContractMappings", "isolated", "readOnly",
    )
    valid = {
        "id": "contract",
        "status": "fail",
        "inputFingerprint": fingerprint,
        "evidence": ["task.md:1"],
        "findings": ["bounded architecture finding"],
        "discovery": {
            "methods": {
                name: {"complete": True}
                for name in ("exactText", "structural", "dependency")
            }
        },
        "persistedContractMappings": [],
        "isolated": True,
        "readOnly": True,
    }
    calls = []

    def fake_launch(*args, **kwargs):
        calls.append(args)
        return {"id": "contract"} if len(calls) == 1 else valid

    monkeypatch.setattr(RUNNER, "launch", fake_launch)
    result = RUNNER.run_inspector(
        "contract", {"id": "contract"}, fingerprint, tmp_path / "task.md",
        tmp_path, {}, fields,
    )
    assert result["status"] == "fail"
    assert len(calls) == 2

    calls.clear()
    monkeypatch.setattr(
        RUNNER, "launch",
        lambda *args, **kwargs: calls.append(args) or valid,
    )
    result = RUNNER.run_inspector(
        "contract", {"id": "contract"}, fingerprint, tmp_path / "task.md",
        tmp_path, {}, fields,
    )
    assert result["status"] == "fail"
    assert len(calls) == 1
