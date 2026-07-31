from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from pathlib import Path

from ._doc import (append_evidence, command_outcome_ok, confined, prior_nonterminal, read_jsonl,
                   relative_ref, review_scope_ok, sha256, terminal_matches, upsert_receipt, utc_now)
from .adapter import Adapter
from .fingerprint import fingerprint_for_gate
from .model import INAPPLICABLE, PASS, AcddError, Check, Document, Gate

MAX_OUTPUT = 4096
_EVIDENCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SECRET = re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[=:]\s*[^\s]+|Bearer\s+\S+")
_KIND_REF = {"command": "commandReceipt", "basis": "basisRef"}

def _command_record(*, argv: tuple[str, ...], cwd: Path, evidence_id: str, gate_id: str,
                    check_id: str, timeout_seconds: int = 300) -> dict:
    started = time.monotonic()
    timed_out, exec_error, exit_code = False, False, 0
    try:
        result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout_seconds, check=False)
        exit_code, output = result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        exit_code, output, timed_out = 124, f"timeout after {timeout_seconds}s", True
    except OSError as exc:
        exit_code, output, exec_error = 127, f"failed to execute {argv[0]!r}: {exc}", True
    redacted = _SECRET.sub("<redacted>", output)[:MAX_OUTPUT]
    record = {"type": "command_run", "evidenceId": evidence_id, "gate": gate_id, "check": check_id,
              "argv": [_SECRET.sub("<redacted>", a) for a in argv], "exitCode": exit_code,
              "durationMs": int((time.monotonic() - started) * 1000), "output": redacted,
              "redacted": redacted != output[:MAX_OUTPUT], "timestamp": utc_now()}
    record.update((k, True) for k, v in (("timeout", timed_out), ("executionError", exec_error)) if v)
    return record

def _find_check(gate: Gate, check_id: str) -> Check:
    check = next((item for item in gate.checks if item.id == check_id), None)
    if check is None:
        raise AcddError(f"unknown check {check_id!r} for {gate.id}")
    return check

def _require_fresh_id(document: Document, evidence_id: str) -> None:
    if not _EVIDENCE_ID.fullmatch(evidence_id):
        raise AcddError("evidence id must contain only letters, digits, dot, underscore, or dash")
    if any(item.get("id") == evidence_id for item in document.evidence):
        raise AcddError(f"evidence id already exists: {evidence_id}")

def _reject_duplicate_check(document: Document, gate: Gate, check_id: str, fingerprint: str) -> None:
    if any(item.get("gate") == gate.id and item.get("check") == check_id and item.get("kind") != "bundle"
           and item.get("inputFingerprint") == fingerprint for item in document.evidence):
        raise AcddError(f"evidence for {gate.id}.{check_id} already recorded at the current fingerprint")

def record_check(*, document: Document, workspace_root: Path, gate: Gate, check_id: str,
                 evidence_id: str, adapter: Adapter, classified_refs: list[dict] | None = None) -> tuple[dict | None, bool]:
    _require_fresh_id(document, evidence_id)
    if adapter.role != gate.owner:
        raise AcddError(f"adapter role {adapter.role!r} does not own {gate.id}")
    check = _find_check(gate, check_id)
    binding = adapter.gates.get(gate.id)
    if binding is None or check_id not in binding.checks:
        raise AcddError(f"adapter lacks binding for {gate.id}.{check_id}")
    if check.evidence_kind == "review":
        raise AcddError("review evidence must be registered with acdd review")
    fingerprint = fingerprint_for_gate(document, gate, workspace_root, adapter)
    _reject_duplicate_check(document, gate, check_id, fingerprint)
    basis_scope: list[str] = []
    if check.evidence_kind == "basis":
        basis_scope = [e["path"] for e in document.inputs
                       if e.get("type") in gate.invalidates_on and isinstance(e.get("path"), str)]
        classified = {item.get("path") for item in classified_refs or [] if isinstance(item, dict)}
        if not classified_refs or not set(basis_scope).issubset(classified):
            raise AcddError("basis evidence requires classifiedRefs covering the gate input scope")
    artifact_dir = confined(workspace_root, relative_ref(workspace_root, adapter.resolve(adapter.artifact_dir)),
                            "artifactDir")
    artifact_path = artifact_dir / f"{evidence_id}.jsonl"
    if artifact_path.exists():
        artifact_path.unlink()  # overwrite orphan from a failed prior run
    artifact_dir.mkdir(parents=True, exist_ok=True)
    check_binding = binding.checks[check_id]
    cwd = confined(workspace_root, check_binding.cwd, "adapter cwd")
    if not cwd.is_dir():
        raise AcddError(f"adapter cwd does not exist: {check_binding.cwd!r}")
    argv = tuple(arg.replace("{document}", str(document.path)) for arg in check_binding.argv)
    terminal = _command_record(argv=argv, cwd=cwd, evidence_id=evidence_id, gate_id=gate.id,
                               check_id=check_id, timeout_seconds=check_binding.timeout_seconds)
    with artifact_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(terminal, sort_keys=True) + "\n")
    if not command_outcome_ok(check, terminal):
        return None, False
    payload = {"kind": check.evidence_kind, "id": evidence_id, "gate": gate.id, "check": check_id,
               "issuerRole": adapter.role, "artifactSha256": sha256(artifact_path),
               "inputFingerprint": fingerprint, "recordedAt": utc_now(),
               _KIND_REF[check.evidence_kind]: relative_ref(workspace_root, artifact_path)}
    if check.evidence_kind == "basis":
        payload.update({"scope": basis_scope, "classifiedRefs": classified_refs or []})
    append_evidence(document.path, payload)
    return payload, True

def record_review(*, document: Document, workspace_root: Path, gate: Gate, check_id: str,
                  evidence_id: str, adapter: Adapter, transcript: Path, author_uuid: str,
                  reviewer_uuid: str, verdict: str) -> dict:
    if adapter.role != gate.owner or _find_check(gate, check_id).evidence_kind != "review":
        raise AcddError("review command requires an owner-bound review check")
    if gate.id not in adapter.gates or check_id not in adapter.gates[gate.id].checks:
        raise AcddError("review adapter lacks the required check binding")
    _require_fresh_id(document, evidence_id)
    fingerprint = fingerprint_for_gate(document, gate, workspace_root, adapter)
    _reject_duplicate_check(document, gate, check_id, fingerprint)
    transcript_path = confined(workspace_root, str(transcript), "review transcript")
    if not transcript_path.is_file():
        raise AcddError("review transcript is missing")
    try:
        author, reviewer = uuid.UUID(author_uuid), uuid.UUID(reviewer_uuid)
    except ValueError as exc:
        raise AcddError("review session UUIDs are invalid") from exc
    if author == reviewer or verdict != "pass":
        raise AcddError("review requires verdict=pass and distinct session UUIDs")
    records = read_jsonl(transcript_path)
    terminal = records[-1] if records else {}
    if (not records or not terminal_matches(terminal, evidence_id, gate.id, check_id)
            or terminal.get("type") != "review_terminal" or terminal.get("verdict") != PASS):
        raise AcddError("review transcript terminal must be review_terminal with verdict=pass")
    if (str(terminal.get("authorSessionUuid")) != author_uuid
            or str(terminal.get("reviewerSessionUuid")) != reviewer_uuid):
        raise AcddError("review terminal session UUIDs must match --author-uuid/--reviewer-uuid")
    if not review_scope_ok(gate.review_dimensions, terminal):
        raise AcddError("review terminal must declare a non-empty scope and performedChecks "
                        f"covering {sorted(gate.review_dimensions)!r}")
    payload = {"kind": "review", "id": evidence_id, "gate": gate.id, "check": check_id,
               "issuerRole": adapter.role, "transcriptRef": relative_ref(workspace_root, transcript_path),
               "artifactSha256": sha256(transcript_path), "inputFingerprint": fingerprint,
               "recordedAt": utc_now(), "authorSessionUuid": author_uuid,
               "reviewerSessionUuid": reviewer_uuid, "verdict": verdict}
    append_evidence(document.path, payload)
    return payload

def finalize_gate(*, document: Document, workspace_root: Path, gate: Gate, evidence_id: str,
                  adapter: Adapter, status: str = "pass", reason_code: str | None = None) -> dict:
    if adapter.role != gate.owner:
        raise AcddError(f"adapter role {adapter.role!r} does not own {gate.id}")
    if gate.id not in adapter.gates or set(adapter.gates[gate.id].checks) != {check.id for check in gate.checks}:
        raise AcddError(f"adapter bindings do not exactly cover {gate.id}")
    if status not in gate.terminals:
        raise AcddError(f"status {status!r} is not terminal for {gate.id}")
    _require_fresh_id(document, evidence_id)
    prior = prior_nonterminal(document.receipts, gate.id)
    if prior is not None:
        raise AcddError(f"cannot finalize {gate.id}: prior gate {prior} is not terminal")
    fingerprint = fingerprint_for_gate(document, gate, workspace_root, adapter)
    members = [item for item in document.evidence if item.get("gate") == gate.id and item.get("kind") != "bundle"
               and item.get("inputFingerprint") == fingerprint]
    check_ids = {check.id for check in gate.checks}
    if status == INAPPLICABLE:
        if reason_code not in gate.inapplicable_reason_codes:
            raise AcddError(f"invalid inapplicable reason for {gate.id}")
        if members:
            raise AcddError(f"inapplicable {gate.id} must not include check evidence")
        member_ids: list[str] = []
    else:
        by_check = {item.get("check"): item for item in members
                    if isinstance(item.get("check"), str)}
        if len(by_check) != len(members) or set(by_check) != check_ids:
            raise AcddError(f"cannot finalize {gate.id}: exactly one successful evidence per check is required")
        member_ids = [by_check[check.id]["id"] for check in gate.checks]
    payload = {"kind": "bundle", "id": evidence_id, "gate": gate.id, "issuerRole": adapter.role,
               "checkEvidence": member_ids, "inputFingerprint": fingerprint, "recordedAt": utc_now()}
    if reason_code:
        payload["reasonCode"] = reason_code
    append_evidence(document.path, payload)
    upsert_receipt(doc_path=document.path, gate_id=gate.id, status=status,
                   evidence_ref=f"bundle={evidence_id}", fingerprint=fingerprint, recorded_at=utc_now())
    return payload
