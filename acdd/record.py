from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from pathlib import Path

from . import _doc
from .adapter import Adapter, index_adapters
from .authority import (
    active_subtasks,
    assert_changed_paths_allowed,
    assert_precontract_clean,
    assert_writes_not_shrunk,
    authority_digest,
    classify_contract_change,
    gate_requires_authority_verify,
    matching_authority_verify,
    resolve_build_changed_paths,
    write_union,
)
from .fingerprint import fingerprint_for_gate, subtask_contract_part
from .model import (
    INAPPLICABLE,
    PASS,
    AcddError,
    Check,
    Document,
    Gate,
    Profile,
    check_owner,
)
from .process_report import build_process_report, write_process_report
from .validate import validate

MAX_OUTPUT = 4096
_EVIDENCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SECRET = re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[=:]\s*[^\s]+|Bearer\s+\S+")
_KIND_REF = {"command": "commandReceipt", "basis": "basisRef"}


def _command_record(
    *,
    argv: tuple[str, ...],
    cwd: Path,
    evidence_id: str,
    gate_id: str,
    check_id: str,
    timeout_seconds: int = 300,
) -> dict:
    started = time.monotonic()
    timed_out, exec_error, exit_code = False, False, 0
    try:
        result = subprocess.run(
            argv, cwd=cwd, text=True, capture_output=True, timeout=timeout_seconds, check=False
        )
        exit_code, output = result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        exit_code, output, timed_out = 124, f"timeout after {timeout_seconds}s", True
    except OSError as exc:
        exit_code, output, exec_error = 127, f"failed to execute {argv[0]!r}: {exc}", True
    redacted = _SECRET.sub("<redacted>", output)[:MAX_OUTPUT]
    record = {
        "type": "command_run",
        "evidenceId": evidence_id,
        "gate": gate_id,
        "check": check_id,
        "argv": [_SECRET.sub("<redacted>", arg) for arg in argv],
        "exitCode": exit_code,
        "durationMs": int((time.monotonic() - started) * 1000),
        "output": redacted,
        "redacted": redacted != output[:MAX_OUTPUT],
        "timestamp": _doc.utc_now(),
    }
    record.update(
        (key, True)
        for key, value in (("timeout", timed_out), ("executionError", exec_error))
        if value
    )
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


def _reject_duplicate_check(
    document: Document, gate: Gate, check_id: str, fingerprint: str
) -> None:
    for item in document.evidence:
        if (
            item.get("gate") != gate.id
            or item.get("check") != check_id
            or item.get("kind") == "bundle"
            or item.get("inputFingerprint") != fingerprint
        ):
            continue
        if (
            gate.id == "contract/v1"
            and item.get("kind") == "review"
            and item.get("authorityDigest") != authority_digest(document.subtasks)
        ):
            continue
        raise AcddError(
            f"evidence for {gate.id}.{check_id} already recorded at the current fingerprint"
        )


def record_check(
    *,
    document: Document,
    workspace_root: Path,
    gate: Gate,
    check_id: str,
    evidence_id: str,
    adapter: Adapter,
    classified_refs: list[dict] | None = None,
    adapters: list[Adapter] | dict[str, Adapter] | None = None,
    changed_paths: list[str] | None = None,
) -> tuple[dict | None, bool]:
    _require_fresh_id(document, evidence_id)
    check = _find_check(gate, check_id)
    owner = check_owner(gate, check)
    if adapter.role != owner:
        raise AcddError(f"adapter role {adapter.role!r} does not own {gate.id}.{check_id}")
    binding = adapter.gates.get(gate.id)
    if binding is None or check_id not in binding.checks:
        raise AcddError(f"adapter lacks binding for {gate.id}.{check_id}")
    if check.evidence_kind == "review":
        raise AcddError("review evidence must be registered with acdd review")
    assert_precontract_clean(
        document_path=document.path,
        inputs=document.inputs,
        receipts=document.receipts,
        workspace=workspace_root,
    )
    writes = [path for task in active_subtasks(document.subtasks) for path in task.writes]
    if gate.id == "build/v1":
        assert_changed_paths_allowed(
            resolve_build_changed_paths(workspace_root, changed_paths, inputs=document.inputs),
            allowed_writes=writes,
        )
    elif changed_paths is not None:
        assert_changed_paths_allowed(changed_paths, allowed_writes=writes)
    fingerprint = fingerprint_for_gate(
        document, gate, workspace_root, adapters if adapters is not None else adapter
    )
    _reject_duplicate_check(document, gate, check_id, fingerprint)
    basis_scope: list[str] = []
    if check.evidence_kind == "basis":
        basis_scope = [
            entry["path"]
            for entry in document.inputs
            if entry.get("type") in gate.invalidates_on and isinstance(entry.get("path"), str)
        ]
        classified = {item.get("path") for item in classified_refs or [] if isinstance(item, dict)}
        if not classified_refs or not set(basis_scope).issubset(classified):
            raise AcddError("basis evidence requires classifiedRefs covering the gate input scope")
    artifact_dir = _doc.confined(
        workspace_root,
        _doc.relative_ref(workspace_root, adapter.resolve(adapter.artifact_dir)),
        "artifactDir",
    )
    artifact_path = artifact_dir / f"{evidence_id}.jsonl"
    if artifact_path.exists():
        artifact_path.unlink()  # overwrite orphan from a failed prior run
    artifact_dir.mkdir(parents=True, exist_ok=True)
    check_binding = binding.checks[check_id]
    cwd = _doc.confined(workspace_root, check_binding.cwd, "adapter cwd")
    if not cwd.is_dir():
        raise AcddError(f"adapter cwd does not exist: {check_binding.cwd!r}")
    argv = tuple(arg.replace("{document}", str(document.path)) for arg in check_binding.argv)
    terminal = _command_record(
        argv=argv,
        cwd=cwd,
        evidence_id=evidence_id,
        gate_id=gate.id,
        check_id=check_id,
        timeout_seconds=check_binding.timeout_seconds,
    )
    with artifact_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(terminal, sort_keys=True) + "\n")
    if not _doc.command_outcome_ok(check, terminal):
        return None, False
    payload = {
        "kind": check.evidence_kind,
        "id": evidence_id,
        "gate": gate.id,
        "check": check_id,
        "issuerRole": adapter.role,
        "artifactSha256": _doc.sha256(artifact_path),
        "inputFingerprint": fingerprint,
        "recordedAt": _doc.utc_now(),
        _KIND_REF[check.evidence_kind]: _doc.relative_ref(workspace_root, artifact_path),
    }
    if check.evidence_kind == "basis":
        payload.update({"scope": basis_scope, "classifiedRefs": classified_refs or []})
    _doc.append_evidence(document.path, payload)
    return payload, True


def record_review(
    *,
    document: Document,
    workspace_root: Path,
    gate: Gate,
    check_id: str,
    evidence_id: str,
    adapter: Adapter,
    transcript: Path,
    author_uuid: str,
    reviewer_uuid: str,
    verdict: str,
    adapters: list[Adapter] | dict[str, Adapter] | None = None,
) -> dict:
    check = _find_check(gate, check_id)
    owner = check_owner(gate, check)
    if adapter.role != owner or check.evidence_kind != "review":
        raise AcddError("review command requires an owner-bound review check")
    if gate.id not in adapter.gates or check_id not in adapter.gates[gate.id].checks:
        raise AcddError("review adapter lacks the required check binding")
    _require_fresh_id(document, evidence_id)
    assert_precontract_clean(
        document_path=document.path,
        inputs=document.inputs,
        receipts=document.receipts,
        workspace=workspace_root,
    )
    fingerprint = fingerprint_for_gate(
        document, gate, workspace_root, adapters if adapters is not None else adapter
    )
    _reject_duplicate_check(document, gate, check_id, fingerprint)
    transcript_path = _doc.confined(workspace_root, str(transcript), "review transcript")
    if not transcript_path.is_file():
        raise AcddError("review transcript is missing")
    try:
        author, reviewer = uuid.UUID(author_uuid), uuid.UUID(reviewer_uuid)
    except ValueError as exc:
        raise AcddError("review session UUIDs are invalid") from exc
    if author == reviewer or verdict != "pass":
        raise AcddError("review requires verdict=pass and distinct session UUIDs")
    records = _doc.read_jsonl(transcript_path)
    terminal = records[-1] if records else {}
    if (
        not records
        or not _doc.terminal_matches(terminal, evidence_id, gate.id, check_id)
        or terminal.get("type") != "review_terminal"
        or terminal.get("verdict") != PASS
    ):
        raise AcddError("review transcript terminal must be review_terminal with verdict=pass")
    if (
        str(terminal.get("authorSessionUuid")) != author_uuid
        or str(terminal.get("reviewerSessionUuid")) != reviewer_uuid
    ):
        raise AcddError("review terminal session UUIDs must match --author-uuid/--reviewer-uuid")
    if not _doc.review_scope_ok(gate.review_dimensions, terminal, records):
        raise AcddError(
            f"review transcript must retain raw reviewer sessions, confirmation of each, a non-empty scope, and performedChecks covering {sorted(gate.review_dimensions)!r}"
        )
    payload = {
        "kind": "review",
        "id": evidence_id,
        "gate": gate.id,
        "check": check_id,
        "issuerRole": adapter.role,
        "transcriptRef": _doc.relative_ref(workspace_root, transcript_path),
        "artifactSha256": _doc.sha256(transcript_path),
        "inputFingerprint": fingerprint,
        "recordedAt": _doc.utc_now(),
        "authorSessionUuid": author_uuid,
        "reviewerSessionUuid": reviewer_uuid,
        "verdict": verdict,
    }
    if gate.id == "contract/v1":
        payload["authorityDigest"] = authority_digest(document.subtasks)
    _doc.append_evidence(document.path, payload)
    return payload


def _artifact_dir(workspace_root: Path, adapter: Adapter) -> Path:
    directory = _doc.confined(
        workspace_root,
        _doc.relative_ref(workspace_root, adapter.resolve(adapter.artifact_dir)),
        "artifactDir",
    )
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _subtask_contract_records(part: dict) -> tuple[dict, dict]:
    return part, {
        "type": "subtask_contract_binding",
        "id": f"{part['id']}.binding",
        "partId": part["id"],
        "partSha256": part["partSha256"],
    }


def _write_subtask_bundle(
    document: Document,
    workspace_root: Path,
    adapter: Adapter,
    evidence_id: str,
    contract_fingerprint: str,
) -> str:
    artifact = _artifact_dir(workspace_root, adapter) / f"{evidence_id}.subtasks.jsonl"
    if artifact.exists():
        raise AcddError(f"source contract bundle already exists: {artifact.name}")
    parts = [
        subtask_contract_part(task, f"{evidence_id}.subtask.{index}", contract_fingerprint)
        for index, task in enumerate(document.subtasks, 1)
    ]
    with artifact.open("x", encoding="utf-8") as handle:
        handle.writelines(
            json.dumps(record, sort_keys=True) + "\n"
            for part in parts
            for record in _subtask_contract_records(part)
        )
    return _doc.relative_ref(workspace_root, artifact)


def _contract_bundle(document: Document, receipt: dict) -> dict | None:
    evidence_id = str(receipt.get("evidence", "")).removeprefix("bundle=")
    return next(
        (
            item
            for item in document.evidence
            if item.get("id") == evidence_id and item.get("kind") == "bundle"
        ),
        None,
    )


def _safe_source_bundle(workspace_root: Path, bundle: dict | None) -> Path | None:
    if not bundle or not isinstance(bundle.get("subtaskContractBundleRef"), str):
        return None
    try:
        return _doc.confined(
            workspace_root, bundle["subtaskContractBundleRef"], "subtask contract bundle"
        )
    except AcddError:
        return None


def record_subtask_contract(
    *,
    document: Document,
    profile: Profile,
    workspace_root: Path,
    adapter: Adapter,
    subtask_id: str,
    evidence_id: str,
    adapters: list[Adapter] | None = None,
    allow_scope_reduction: bool = False,
) -> dict:
    gate = next((item for item in profile.gates if item.id == "contract/v1"), None)
    receipt = next((item for item in document.receipts if item.get("gate") == "contract/v1"), None)
    if gate is None or receipt is None or receipt.get("status") != PASS:
        raise AcddError("subtask contracts require a passed contract/v1 receipt")
    if adapter.role != gate.owner or gate.id not in adapter.gates:
        raise AcddError("subtask contracts require the Contract owner adapter")
    subtask = next((item for item in document.subtasks if item.id == subtask_id), None)
    if subtask is None:
        raise AcddError(f"unknown subtask {subtask_id!r}")
    bundle = _contract_bundle(document, receipt)
    artifact = _safe_source_bundle(workspace_root, bundle)
    records = _doc.read_jsonl(artifact) if artifact else None
    if records is None:
        raise AcddError("passed contract receipt lacks a valid source bundle")
    contracted_ids = {
        item["subtask"]
        for item in records
        if item.get("type") == "subtask_contract" and isinstance(item.get("subtask"), str)
    }
    contracted_tasks = tuple(task for task in document.subtasks if task.id in contracted_ids)
    contracted_active = active_subtasks(contracted_tasks)
    prior_writes = write_union(contracted_active)
    new_writes = write_union(active_subtasks(document.subtasks))
    if classify_contract_change(subtask, contracted_active=contracted_active) == "material":
        assert_writes_not_shrunk(
            prior_writes, new_writes, allow_scope_reduction=allow_scope_reduction
        )
    missing = f"invariant 6 (bounded): subtask {subtask_id!r} has no source contract"
    authority_gap = "invariant 4 (state): contract authority digest lacks matching contract-verify"
    errors = [
        error
        for error in validate(
            document, profile, adapters=adapters or [adapter], workspace_root=workspace_root
        )
        if str(error) not in {missing, authority_gap}
    ]
    if errors:
        raise AcddError(f"cannot contract invalid subtask: {errors[0]}")
    if not _EVIDENCE_ID.fullmatch(evidence_id) or any(
        item.get("id") == evidence_id for item in records
    ):
        raise AcddError(f"source contract id is invalid or already used: {evidence_id}")
    if any(item.get("subtask") == subtask.id for item in records):
        raise AcddError(f"subtask {subtask.id!r} already has a source contract")
    part = subtask_contract_part(subtask, evidence_id, str(receipt.get("fingerprint", "")))
    assert artifact is not None
    with artifact.open("a", encoding="utf-8") as handle:
        handle.writelines(
            json.dumps(record, sort_keys=True) + "\n" for record in _subtask_contract_records(part)
        )
    return part


def reopen_gate(*, document: Document, gate: Gate, workspace_root: Path) -> None:
    """Forbidden: freeze is append-only; use contract-subtask for later work."""
    del document, workspace_root
    raise AcddError(
        f"reopen of {gate.id} is forbidden after freeze; append addition or replacement "
        "via `acdd contract-subtask` (use supersedes for replacement), then re-run "
        "contract-verify so the authority digest matches"
    )


def _require_finalizable(
    document: Document, profile: Profile, adapters: list[Adapter], workspace_root: Path, gate: Gate
) -> None:
    errors = validate(document, profile, adapters=adapters, workspace_root=workspace_root)
    stale = f"invariant 4 (state): stale receipt for {gate.id}"
    replacing = any(str(error) == stale for error in errors)
    if errors := [error for error in errors if str(error) != stale]:
        raise AcddError(f"cannot finalize invalid document: {errors[0]}")
    index = next((index for index, item in enumerate(profile.gates) if item.id == gate.id), None)
    if index is None:
        raise AcddError(f"gate {gate.id!r} is not in the profile")
    receipts = {receipt["gate"]: receipt for receipt in document.receipts}
    for prior in profile.gates[:index]:
        if receipts[prior.id]["status"] not in {PASS, INAPPLICABLE}:
            raise AcddError(f"cannot finalize {gate.id}: prior gate {prior.id} is not terminal")
    if receipts[gate.id]["status"] in {PASS, INAPPLICABLE} and not replacing:
        raise AcddError(f"cannot finalize {gate.id}: gate is already terminal")


def _ensure_gate_check_bindings(gate: Gate, adapters_by_role: dict[str, Adapter]) -> None:
    for check in gate.checks:
        role = check_owner(gate, check)
        adapter = adapters_by_role.get(role)
        if (
            adapter is None
            or gate.id not in adapter.gates
            or check.id not in adapter.gates[gate.id].checks
        ):
            raise AcddError(f"missing adapter binding for {gate.id}.{check.id} (role {role!r})")
        for other in adapters_by_role.values():
            if (
                other.role != role
                and gate.id in other.gates
                and check.id in other.gates[gate.id].checks
            ):
                raise AcddError(
                    f"check {gate.id}.{check.id} is bound by non-owner role {other.role!r}"
                )


def finalize_gate(
    *,
    document: Document,
    profile: Profile,
    adapters: list[Adapter],
    workspace_root: Path,
    gate: Gate,
    evidence_id: str,
    adapter: Adapter,
    status: str = "pass",
    reason_code: str | None = None,
    allow_scope_reduction: bool = False,
) -> dict:
    del allow_scope_reduction  # retained on CLI for contract-subtask scope decisions only
    _require_finalizable(document, profile, adapters, workspace_root, gate)
    if adapter.role != gate.owner:
        raise AcddError(f"adapter role {adapter.role!r} does not own {gate.id}")
    assert_precontract_clean(
        document_path=document.path,
        inputs=document.inputs,
        receipts=document.receipts,
        workspace=workspace_root,
    )
    adapters_by_role = index_adapters(adapters)
    _ensure_gate_check_bindings(gate, adapters_by_role)
    if status not in gate.terminals:
        raise AcddError(f"status {status!r} is not terminal for {gate.id}")
    _require_fresh_id(document, evidence_id)
    fingerprint = fingerprint_for_gate(document, gate, workspace_root, adapters_by_role)
    members = [
        item
        for item in document.evidence
        if item.get("gate") == gate.id
        and item.get("kind") != "bundle"
        and item.get("inputFingerprint") == fingerprint
    ]
    check_ids = {check.id for check in gate.checks}
    if status == INAPPLICABLE:
        if reason_code not in gate.inapplicable_reason_codes:
            raise AcddError(f"invalid inapplicable reason for {gate.id}")
        if members:
            raise AcddError(f"inapplicable {gate.id} must not include check evidence")
        member_ids: list[str] = []
    else:
        by_check = {
            item.get("check"): item for item in members if isinstance(item.get("check"), str)
        }
        if len(by_check) != len(members) or set(by_check) != check_ids:
            raise AcddError(
                f"cannot finalize {gate.id}: exactly one successful evidence per check is required"
            )
        member_ids = [by_check[check.id]["id"] for check in gate.checks]
        if gate.id == "contract/v1" and gate_requires_authority_verify(gate):
            digest = authority_digest(document.subtasks)
            if not matching_authority_verify(
                digest=digest, evidence=list(by_check.values()), gate=gate
            ):
                raise AcddError(
                    "invariant 4 (state): contract authority digest lacks matching contract-verify",
                    invariant=4,
                )
    payload = {
        "kind": "bundle",
        "id": evidence_id,
        "gate": gate.id,
        "issuerRole": adapter.role,
        "checkEvidence": member_ids,
        "inputFingerprint": fingerprint,
        "recordedAt": _doc.utc_now(),
    }
    if gate.id == "contract/v1" and status == PASS:
        payload["subtaskContractBundleRef"] = _write_subtask_bundle(
            document, workspace_root, adapter, evidence_id, fingerprint
        )
    if gate.id == "handoff/v1" and status == PASS:
        report_path = _artifact_dir(workspace_root, adapter) / f"{evidence_id}.process-report.json"
        if report_path.exists():
            report_path.unlink()
        pending = {
            "gate": gate.id,
            "status": status,
            "fingerprint": fingerprint,
            "evidence": f"bundle={evidence_id}",
        }
        report = build_process_report(
            document,
            profile,
            workspace_root=workspace_root,
            pending_receipt=pending,
        )
        write_process_report(report_path, report)
        payload["processReportRef"] = _doc.relative_ref(workspace_root, report_path)
    if reason_code:
        payload["reasonCode"] = reason_code
    _doc.append_evidence(document.path, payload)
    _doc.upsert_receipt(
        doc_path=document.path,
        gate_id=gate.id,
        status=status,
        evidence_ref=f"bundle={evidence_id}",
        fingerprint=fingerprint,
        recorded_at=_doc.utc_now(),
    )
    return payload
