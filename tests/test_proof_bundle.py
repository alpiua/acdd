from __future__ import annotations

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


FP = _load("acdd_fingerprint")
DOC = _load("acdd_document")
VALIDATOR = _load("validate_acdd")
RECORD = _load("record_proof")


GATES = (
    "matrix/v1",
    "architecture/v1",
    "red/v1",
    "runtime/v1",
    "parity/v1",
    "security/v1",
    "release/v1",
    "review/v1",
    "handoff/v1",
)


def _task_text(paths: list[tuple[str, str]]) -> str:
    path_yaml = "\n".join(f"  - type: {kind}\n    path: {path}" for kind, path in paths)
    semantic_sections = "\n\n".join(
        f"## {name}\n\ncontract.proof — decision.one proof.red-one"
        for name in FP.TASK_SEMANTIC_SECTIONS
    )
    rows = "\n".join(
        f"| `{gate}` | `pending` | pending | `pending` | `pending` |" for gate in GATES
    )
    return f"""---
title: fixture
status: todo
delivery_profile: acdd/task/v1
---

# Fixture

{semantic_sections}

## ACDD inputs

```yaml
apiVersion: acdd/inputs/v1
kind: inputs
paths:
{path_yaml}
```

## ACDD gate evidence

```yaml
[]
```

## ACDD receipts

| Gate | Status | Evidence / receipt | Input fingerprint | Recorded UTC |
|---|---|---|---|---|
{rows}
"""


def _fixture(tmp_path: Path) -> tuple[Path, tuple[Path, Path]]:
    for name in (
        "source.py",
        "test.py",
        "config.yaml",
        "generated.py",
        "dep.txt",
        "env.txt",
        "findings.txt",
    ):
        (tmp_path / name).write_text(name, encoding="utf-8")
    document = tmp_path / "task.md"
    document.write_text(
        _task_text(
            [
                ("source", "source.py"),
                ("test", "test.py"),
                ("configuration", "config.yaml"),
                ("generated", "generated.py"),
                ("dependency", "dep.txt"),
                ("environment", "env.txt"),
                ("accepted-review-findings", "findings.txt"),
            ]
        ),
        encoding="utf-8",
    )
    task_adapter = tmp_path / "task-adapter.yaml"
    task_adapter.write_text(
        """apiVersion: acdd/adapter/v1
kind: adapter
id: fixture-task/v1
role: task
provides: [task_read, task_write, impact]
procedure: [read]
authority:
  impact:
    domains: [deployment]
constraints: [bounded]
inputAuthorities:
  bound-document: [task.md]
  dependency: ["*"]
  environment: ["*"]
  accepted-review-findings: ["*"]
""",
        encoding="utf-8",
    )
    implementation = tmp_path / "implementation-adapter.yaml"
    implementation.write_text(
        """apiVersion: acdd/adapter/v1
kind: adapter
id: fixture-implementation/v1
role: implementation
provides: [source_map, docs_search, structural_search, run_gate, independent_review, review_execution]
procedure: [inspect]
authority: {source: fixture}
constraints: [bounded]
gateProcedures:
  architecture/v1: {verifier: isolated}
  review/v1: {reviewer: isolated}
inputAuthorities:
  source: ["*"]
  test: ["*"]
  configuration: ["*"]
  generated: ["*"]
  dependency: ["*"]
  environment: ["*"]
  accepted-review-findings: ["*"]
""",
        encoding="utf-8",
    )
    return document, (task_adapter, implementation)


def _live_fp(document: Path, adapters: tuple[Path, ...], workspace: Path) -> str:
    return FP.fingerprint_inputs(
        document=document,
        profile=ROOT / "profiles" / "task" / "v1.yaml",
        receipt_contract=ROOT / "contracts" / "receipt" / "task" / "v1.yaml",
        adapters=adapters,
        workspace_root=workspace,
        include_types=frozenset(FP.INPUT_TYPES),
    ).sha256


def _policies() -> tuple[object, ...]:
    core = VALIDATOR.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    return VALIDATOR._gate_policies(core)


def test_proof_bundle_parses_and_rejects_secrets(tmp_path: Path) -> None:
    document, _ = _fixture(tmp_path)
    digest = "sha256:" + "0" * 64
    bad = f"""```yaml
apiVersion: acdd/gate-evidence/v1
kind: proof-bundle
id: live.bundle
gate: runtime/v1
inputFingerprint: {digest}
claims: [runtime/v1, parity/v1]
commands:
  - exactCommand: pytest
    recordedAt: "2026-07-24T00:00:00Z"
    exitCode: 0
    output: "token=secret-value"
    redacted: false
    result: pass
```"""
    text = document.read_text(encoding="utf-8").replace("```yaml\n[]\n```", bad)
    with pytest.raises(DOC.DocumentError, match="unredacted secret"):
        DOC.parse_evidence(text, workspace_root=tmp_path, semantic=None)

    good = bad.replace(
        'output: "token=secret-value"', 'output: "token=<redacted>"'
    ).replace("redacted: false", "redacted: true")
    text = document.read_text(encoding="utf-8").replace("```yaml\n[]\n```", good)
    parsed = DOC.parse_evidence(text, workspace_root=tmp_path, semantic=None)
    assert parsed["live.bundle"].kind == "proof-bundle"
    assert parsed["live.bundle"].data["claims"] == ["runtime/v1", "parity/v1"]


def test_proof_bundle_requires_gate_in_claims(tmp_path: Path) -> None:
    document, _ = _fixture(tmp_path)
    digest = "sha256:" + "0" * 64
    bad = f"""```yaml
apiVersion: acdd/gate-evidence/v1
kind: proof-bundle
id: live.bundle
gate: security/v1
inputFingerprint: {digest}
claims: [runtime/v1, parity/v1]
commands:
  - exactCommand: true
    recordedAt: "2026-07-24T00:00:00Z"
    exitCode: 0
    output: ok
    redacted: true
    result: pass
```"""
    text = document.read_text(encoding="utf-8").replace("```yaml\n[]\n```", bad)
    with pytest.raises(DOC.DocumentError, match="gate must be one of claims"):
        DOC.parse_evidence(text, workspace_root=tmp_path, semantic=None)


def test_mixed_invalidation_claims_are_rejected_by_policy_set() -> None:
    policies = {policy.gate: policy for policy in _policies()}
    claims = ["runtime/v1", "red/v1"]
    claim_invalidation = {
        frozenset(policies[claim].invalidation_inputs) for claim in claims
    }
    assert len(claim_invalidation) != 1


def test_command_evidence_still_cannot_cover_two_receipts(tmp_path: Path) -> None:
    document, adapters = _fixture(tmp_path)
    live_fp = _live_fp(document, adapters, tmp_path)
    evidence = f"""```yaml
apiVersion: acdd/gate-evidence/v1
kind: command
id: live.one
gate: runtime/v1
inputFingerprint: {live_fp}
exactCommand: "true"
recordedAt: "2026-07-24T12:00:00Z"
exitCode: 0
output: ok
redacted: true
result: pass
```"""
    text = document.read_text(encoding="utf-8").replace("```yaml\n[]\n```", evidence)
    for gate in ("runtime/v1", "parity/v1"):
        text = text.replace(
            f"| `{gate}` | `pending` | pending | `pending` | `pending` |",
            f"| `{gate}` | `pass` | evidence=live.one | `{live_fp}` | `2026-07-24T12:00:00Z` |",
        )
    document.write_text(text, encoding="utf-8")
    with pytest.raises(DOC.DocumentError) as excinfo:
        DOC.validate_document(
            document=document,
            profile=ROOT / "profiles" / "task" / "v1.yaml",
            receipt_contract=ROOT / "contracts" / "receipt" / "task" / "v1.yaml",
            adapters=adapters,
            workspace_root=tmp_path,
            policies=_policies(),
            plan=False,
            impact_axes=frozenset({"deployment"}),
        )
    message = str(excinfo.value)
    assert (
        "cannot satisfy multiple receipts" in message
        or "gate does not match receipt" in message
        or "later gate cannot be terminal before predecessors" in message
    )


def test_redact_secrets_and_truncate() -> None:
    text, changed = RECORD.redact_secrets("password=super-secret ok")
    assert changed is True
    assert "super-secret" not in text
    assert "<redacted>" in text
    huge = "x" * (DOC.MAX_OUTPUT_BYTES + 100)
    clipped = RECORD.truncate_output(huge)
    assert len(clipped.encode("utf-8")) <= DOC.MAX_OUTPUT_BYTES + 64
    assert "...<truncated>..." in clipped


def test_record_proof_writes_bundle(tmp_path: Path) -> None:
    document, adapters = _fixture(tmp_path)
    task_adapter, implementation = adapters
    output_file = tmp_path / "out.txt"
    output_file.write_text("password=should-hide\nall good\n", encoding="utf-8")
    cmd = [
        sys.executable,
        str(SCRIPTS / "record_proof.py"),
        "--document",
        str(document),
        "--workspace-root",
        str(tmp_path),
        "--profile",
        str(ROOT / "profiles" / "task" / "v1.yaml"),
        "--receipt-contract",
        str(ROOT / "contracts" / "receipt" / "task" / "v1.yaml"),
        "--adapter",
        f"task={task_adapter}",
        "--adapter",
        f"implementation={implementation}",
        "--id",
        "live.bundle",
        "--claim",
        "runtime/v1",
        "--claim",
        "parity/v1",
        "--claim",
        "security/v1",
        "--claim",
        "release/v1",
        "--no-run",
        "--exit-code",
        "0",
        "--output-file",
        str(output_file),
        "--cmd",
        "pytest -q",
        "--recorded-at",
        "2026-07-24T12:00:00Z",
        "--write",
    ]
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    written = document.read_text(encoding="utf-8")
    assert "kind: proof-bundle" in written
    assert "live.bundle" in written
    assert "password=should-hide" not in written
    assert "<redacted>" in written
    for gate in ("runtime/v1", "parity/v1", "security/v1", "release/v1"):
        assert f"| `{gate}` | `pass` | evidence=live.bundle |" in written
    parsed = DOC.parse_evidence(written, workspace_root=tmp_path, semantic=None)
    assert parsed["live.bundle"].kind == "proof-bundle"
    assert set(parsed["live.bundle"].data["claims"]) == {
        "runtime/v1",
        "parity/v1",
        "security/v1",
        "release/v1",
    }
    # Fingerprint in receipts must match live invalidation set.
    live_fp = _live_fp(document, adapters, tmp_path)
    assert live_fp in written


def test_record_proof_single_claim_writes_command_kind(tmp_path: Path) -> None:
    document, adapters = _fixture(tmp_path)
    task_adapter, implementation = adapters
    output_file = tmp_path / "out.txt"
    output_file.write_text("ok\n", encoding="utf-8")
    cmd = [
        sys.executable,
        str(SCRIPTS / "record_proof.py"),
        "--document",
        str(document),
        "--workspace-root",
        str(tmp_path),
        "--profile",
        str(ROOT / "profiles" / "task" / "v1.yaml"),
        "--receipt-contract",
        str(ROOT / "contracts" / "receipt" / "task" / "v1.yaml"),
        "--adapter",
        f"task={task_adapter}",
        "--adapter",
        f"implementation={implementation}",
        "--id",
        "runtime.one",
        "--claim",
        "runtime/v1",
        "--no-run",
        "--exit-code",
        "0",
        "--output-file",
        str(output_file),
        "--cmd",
        "true",
        "--recorded-at",
        "2026-07-24T12:00:00Z",
        "--write",
    ]
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    written = document.read_text(encoding="utf-8")
    assert "kind: command" in written
    assert "runtime.one" in written
    assert "| `runtime/v1` | `pass` | evidence=runtime.one |" in written


def test_legacy_single_command_still_parses(tmp_path: Path) -> None:
    document, _ = _fixture(tmp_path)
    digest = "sha256:" + "a" * 64
    evidence = f"""```yaml
apiVersion: acdd/gate-evidence/v1
kind: command
id: runtime.legacy
gate: runtime/v1
inputFingerprint: {digest}
exactCommand: pytest
recordedAt: "2026-07-24T12:00:00Z"
exitCode: 0
output: ok
redacted: true
result: pass
```"""
    text = document.read_text(encoding="utf-8").replace("```yaml\n[]\n```", evidence)
    parsed = DOC.parse_evidence(text, workspace_root=tmp_path, semantic=None)
    assert parsed["runtime.legacy"].kind == "command"


def test_build_evidence_object_shapes() -> None:
    single = RECORD.build_evidence_object(
        evidence_id="one",
        claims=["runtime/v1"],
        input_fingerprint="sha256:" + "b" * 64,
        exact_command="true",
        recorded_at="2026-07-24T00:00:00Z",
        exit_code=0,
        output="ok",
        redacted=True,
        result="pass",
        artifacts=None,
    )
    assert single["kind"] == "command"
    bundle = RECORD.build_evidence_object(
        evidence_id="bundle",
        claims=["runtime/v1", "parity/v1"],
        input_fingerprint="sha256:" + "c" * 64,
        exact_command="true",
        recorded_at="2026-07-24T00:00:00Z",
        exit_code=0,
        output="ok",
        redacted=True,
        result="pass",
        artifacts=["log.txt"],
    )
    assert bundle["kind"] == "proof-bundle"
    assert bundle["claims"] == ["runtime/v1", "parity/v1"]
    assert bundle["artifacts"] == ["log.txt"]
