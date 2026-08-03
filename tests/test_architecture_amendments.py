from __future__ import annotations

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


FP = _load("acdd_fingerprint")
DOC = _load("acdd_document")
RUNNER = _load("run_architecture")

ZERO = "sha256:" + "0" * 64


def _task(*, decision: str = "Use canonical owner.", review_status: str = "pending") -> str:
    semantic = """\
## G0 architecture baseline

decision.base fixes contract.base at authority.base.

## G1 redesign amendments

```yaml
apiVersion: acdd/architecture-amendments/v1
kind: architecture-amendments
items:
  - id: g1-redesign.ingestion
    baseG0Fingerprint: BASE
    rationale: Implementation discovery found a missing producer boundary.
    decisions:
      - DECISION
    coherence:
      - Preserves decision.base and authority.base.
    propagation:
      - caller -> contract -> canonical owner -> storage -> reader
    implementationPaths:
      - services/brain/ingestion.py
    proofIds:
      - proof.ingestion-boundary
    review:
      status: STATUS
      evidence: pending
      inputFingerprint: pending
      recordedAt: pending
    attempts: []
```
"""
    base = FP.semantic_task_fingerprint(semantic).sha256
    return (
        semantic.replace("BASE", base)
        .replace("DECISION", decision)
        .replace("STATUS", review_status)
    )


def _task_v2(
    *,
    receipt: str = "planner/.acdd-legacy/runtime/architecture-receipts/task/g1-redesign.ingestion.yaml",
    transcript: str = "planner/.acdd-legacy/runtime/architecture-transcripts/task/g1-redesign.ingestion.jsonl",
) -> str:
    return (
        _task()
        .replace("acdd/architecture-amendments/v1", "acdd/architecture-amendments/v2")
        .replace(
            "      evidence: pending",
            "\n".join(
                (
                    f"      receipt: {receipt}",
                    "      receiptSha256: pending",
                    f"      transcript: {transcript}",
                    "      transcriptSha256: pending",
                )
            ),
        )
        .replace("    attempts: []\n", "")
    )


def test_g1_redesign_does_not_change_frozen_g0_fingerprint() -> None:
    before = _task()
    after = _task(decision="Use a different canonical ingestion boundary.")
    assert FP.semantic_task_fingerprint(before) == FP.semantic_task_fingerprint(after)
    assert FP.architecture_amendment_fingerprint(
        before, "g1-redesign.ingestion"
    ) != FP.architecture_amendment_fingerprint(after, "g1-redesign.ingestion")
    assert "proof.ingestion-boundary" in FP.architecture_authority_ids(before)


def test_amendment_review_and_attempts_are_not_authority() -> None:
    text = _task()
    amendment = FP.parse_architecture_amendments(text)[0]
    changed = text.replace("attempts: []", f"""attempts:
      - inputFingerprint: {amendment.fingerprint}
        verdict: BLOCKED
        recordedAt: "2026-07-27T00:00:00Z"
""")
    assert FP.architecture_amendment_fingerprint(
        text, amendment.id
    ) == FP.architecture_amendment_fingerprint(changed, amendment.id)


def test_v2_receipt_pointer_is_not_amendment_authority() -> None:
    before = _task_v2()
    after = _task_v2(
        receipt="planner/.acdd-legacy/runtime/architecture-receipts/task/other.yaml",
        transcript="planner/.acdd-legacy/runtime/architecture-transcripts/task/other.jsonl",
    )
    first = FP.parse_architecture_amendments(before)[0]
    assert first.receipt_path.endswith("g1-redesign.ingestion.yaml")
    assert FP.architecture_amendment_fingerprint(before, first.id) == FP.architecture_amendment_fingerprint(after, first.id)


def test_launcher_delegates_raw_capture_to_adapter_sink(tmp_path: Path) -> None:
    transcript: list[dict[str, object]] = []
    result = RUNNER.launch(
        {
            "kind": "command",
            "target": sys.executable,
            "arguments": [
                "-c",
                "print('authorization=super-secret'); print('{\\\"ok\\\": true}')",
            ],
            "promptTransport": "final-argument",
        },
        "prompt",
        "session",
        tmp_path,
        ("ok",),
        transcript_sink=transcript.append,
        usage_context={"role": "inspector", "partition": "authority", "attempt": 1},
    )
    assert result == {"ok": True}
    assert "authorization=super-secret" in str(transcript)
    assert transcript[0]["usage"]["available"] is False


def test_launcher_binds_codex_workspace_to_command_cwd(tmp_path: Path) -> None:
    result = RUNNER.launch(
        {
            "kind": "command",
            "target": sys.executable,
            "arguments": [
                "-c",
                "import json, os; print(json.dumps({'workspace': os.environ['ACDD_CODEX_WORKSPACE']}))",
            ],
            "promptTransport": "final-argument",
        },
        "prompt",
        "session",
        tmp_path,
        ("workspace",),
    )
    assert result == {"workspace": str(tmp_path.resolve())}


def test_pending_amendment_blocks_terminal_runtime_receipt() -> None:
    text = _task()
    amendment = FP.parse_architecture_amendments(text)[0]
    semantic = FP.semantic_task_fingerprint(text)
    semantic_record = DOC.SemanticRecord(
        semantic.sha256,
        semantic.ids,
        semantic.red_proof_sha256,
        (),
    )
    receipts = (
        DOC.Receipt("architecture/v1", "pass", "g0", ZERO, "2026-07-27T00:00:00Z"),
        DOC.Receipt("runtime/v1", "pass", "runtime", ZERO, "2026-07-27T00:00:00Z"),
    )
    with pytest.raises(
        DOC.DocumentError, match="unreviewed architecture amendments.*block runtime/v1"
    ):
        DOC._validate_architecture_amendments(
            text=text,
            document=Path("/workspace/task.md"),
            workspace_root=Path("/workspace"),
            amendments=(amendment,),
            semantic_record=semantic_record,
            receipts=receipts,
            evidence={},
            expected_value_domain_ids=set(),
            architecture_verification_schema=None,
            architecture_verification_contract=None,
        )
    DOC._validate_architecture_amendments(
        text=text,
        document=Path("/workspace/task.md"),
        workspace_root=Path("/workspace"),
        amendments=(amendment,),
        semantic_record=semantic_record,
        receipts=receipts,
        evidence={},
        expected_value_domain_ids=set(),
        architecture_verification_schema=None,
        architecture_verification_contract=None,
        reviewing_amendment=amendment.id,
    )


def test_legacy_g0_can_host_amendment_without_fingerprint_migration() -> None:
    explicit = _task()
    amendment_section = "## G1 redesign amendments" + explicit.split(
        "## G1 redesign amendments", 1
    )[1]
    legacy_baseline = "\n\n".join(
        f"## {name}\nlegacy authority for {name}."
        for name in FP.TASK_REQUIRED_SECTIONS
    ) + "\n\n## Runtime path (required)\nlegacy runtime path.\n"
    legacy_fingerprint = FP.semantic_task_fingerprint(legacy_baseline).sha256
    explicit_fingerprint = FP.semantic_task_fingerprint(explicit).sha256
    text = legacy_baseline + "\n\n" + amendment_section.replace(
        explicit_fingerprint, legacy_fingerprint
    )
    semantic = FP.semantic_task_fingerprint(text)
    amendment = FP.parse_architecture_amendments(text)[0]

    assert semantic.sha256 == legacy_fingerprint
    assert amendment.base_g0_fingerprint == legacy_fingerprint
    authority = RUNNER.semantic_candidate_authority(text, amendment.id)
    assert "G0 architecture baseline" not in authority
    assert authority["Objective"] == "legacy authority for Objective."
    assert authority["G1 redesign amendment"]["id"] == amendment.id

    DOC._validate_architecture_amendments(
        text=text,
        document=Path("/workspace/task.md"),
        workspace_root=Path("/workspace"),
        amendments=(amendment,),
        semantic_record=DOC.SemanticRecord(
            semantic.sha256, semantic.ids, semantic.red_proof_sha256, ()
        ),
        receipts=(
            DOC.Receipt(
                "architecture/v1",
                "pass",
                "g0",
                ZERO,
                "2026-07-27T00:00:00Z",
            ),
        ),
        evidence={},
        expected_value_domain_ids=set(),
        architecture_verification_schema=None,
        architecture_verification_contract=None,
        reviewing_amendment=amendment.id,
    )


def test_g1_code_changes_do_not_stale_explicit_g0_receipt() -> None:
    text = _task()
    semantic = FP.semantic_task_fingerprint(text)
    approved_candidate = "sha256:" + "1" * 64
    evidence = DOC.Evidence(
        id="architecture.g0",
        kind="review",
        gate="architecture/v1",
        input_fingerprint=approved_candidate,
        data={
            "baseG0Fingerprint": semantic.sha256,
            "codeSnapshotFingerprint": "sha256:" + "2" * 64,
        },
    )
    receipt = DOC.Receipt(
        "architecture/v1",
        "pass",
        evidence.id,
        approved_candidate,
        "2026-07-27T00:00:00Z",
    )
    assert DOC._architecture_freshness_basis(
        text=text,
        semantic=semantic,
        gate_evidence=evidence,
        receipt=receipt,
        candidate_fingerprint="sha256:" + "3" * 64,
        legacy_code_fingerprint="sha256:" + "4" * 64,
    ) == frozenset({approved_candidate})

    changed_baseline = text.replace("decision.base", "decision.changed", 1)
    assert approved_candidate not in DOC._architecture_freshness_basis(
        text=changed_baseline,
        semantic=FP.semantic_task_fingerprint(changed_baseline),
        gate_evidence=evidence,
        receipt=receipt,
        candidate_fingerprint="sha256:" + "3" * 64,
        legacy_code_fingerprint="sha256:" + "4" * 64,
    )
