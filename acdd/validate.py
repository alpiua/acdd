from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from ._doc import (command_outcome_ok, prior_nonterminal, read_jsonl, resolve_under, review_scope_ok,
                   sha256, terminal_matches)
from .adapter import Adapter, index_adapters
from .fingerprint import fingerprint_for_gate
from .model import BLOCKED, INAPPLICABLE, PARTIAL, PASS, PENDING, STATUSES, AcddError, Document, Profile

EVIDENCE_KINDS = {"command", "basis", "review", "bundle"}
_ARTIFACT_FIELD = {"command": "commandReceipt", "basis": "basisRef", "review": "transcriptRef"}

def _safe_artifact(workspace_root: Path, relative: object) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    try:
        return resolve_under(workspace_root, relative, label="artifact")
    except ValueError:
        return None

def _overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right.rstrip("/") + "/") or right.startswith(left.rstrip("/") + "/")

def _reachable(deps: dict[str, set[str]], start: str, target: str) -> bool:
    seen, stack = set(), [start]
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node not in seen:
            seen.add(node)
            stack.extend(deps.get(node, ()))
    return False

def _has_cycle(deps: dict[str, set[str]]) -> bool:
    visiting, visited = set(), set()
    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(dep) for dep in deps.get(node, ())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False
    return any(visit(node) for node in deps)

def _conflicts(left, right, deps: dict[str, set[str]]) -> bool:
    return ((any(_overlap(a, b) for a in left.writes for b in (*right.writes, *right.reads))
             or any(_overlap(a, b) for a in right.writes for b in left.reads))
            and not (_reachable(deps, right.id, left.id) or _reachable(deps, left.id, right.id)))

def _independent_review(evidence: dict, terminal: dict | None) -> bool:
    author, reviewer = evidence.get("authorSessionUuid"), evidence.get("reviewerSessionUuid")
    try:
        distinct = bool(author and reviewer and uuid.UUID(str(author)) != uuid.UUID(str(reviewer)))
    except ValueError:
        return False
    if not distinct or evidence.get("verdict") != PASS:
        return False
    return terminal is None or (terminal.get("type") == "review_terminal" and terminal.get("verdict") == PASS
                                and str(terminal.get("authorSessionUuid")) == str(author)
                                and str(terminal.get("reviewerSessionUuid")) == str(reviewer))

def validate(doc: Document, profile: Profile, *, adapters: list[Adapter] | None = None,
             workspace_root: Path | None = None) -> list[AcddError]:
    errors: list[AcddError] = []
    err: Callable[[int, str], None] = lambda invariant, msg: errors.append(AcddError(msg, invariant=invariant))
    workspace = (workspace_root or doc.path.parent).resolve()
    try:
        adapters_by_role = index_adapters(adapters or [])
    except ValueError as exc:
        return [AcddError(str(exc), invariant=10)]
    gates = {gate.id: gate for gate in profile.gates}
    for adapter in adapters or []:
        unknown = set(adapter.gates) - set(gates)
        if unknown:
            err(10, f"invariant 10 (discovery): adapter {adapter.id!r} binds unknown gates {sorted(unknown)}")
    if doc.profile_id and profile.id and doc.profile_id != profile.id:
        err(1, f"invariant 1 (shape): document declares {doc.profile_id!r} but profile is {profile.id!r}")
    receipt_ids = [receipt.get("gate", "") for receipt in doc.receipts]
    if receipt_ids != [gate.id for gate in profile.gates] or len(set(receipt_ids)) != len(receipt_ids):
        err(1, "invariant 1 (shape): receipts must be exactly profile gates in order")
    pending_keys = ("evidence", "fingerprint", "recordedAt")
    for receipt in doc.receipts:
        gate, status = gates.get(receipt.get("gate")), receipt.get("status")
        if gate is None or status not in STATUSES:
            err(1, f"invariant 1 (shape): unknown gate or status in {receipt!r}")
        elif status in {PASS, INAPPLICABLE} and status not in gate.terminals:
            err(1, f"invariant 1 (shape): {status} not allowed for {gate.id}")
        elif status in {PENDING, PARTIAL, BLOCKED} and tuple(receipt.get(k) for k in pending_keys) != (PENDING,) * 3:
            err(1, f"invariant 1 (shape): non-terminal {receipt.get('gate')} is not fully pending")
        note = receipt.get("note")
        if note is not None and (status in {PENDING, PASS, INAPPLICABLE} or not note):
            err(1, f"invariant 1 (shape): note is only allowed on partial/blocked in {receipt.get('gate')}")
        if status in {PASS, INAPPLICABLE} and (prior := prior_nonterminal(doc.receipts, receipt.get("gate", ""))):
            err(1, f"invariant 1 (shape): terminal {receipt.get('gate')} requires prior gate {prior} terminal")
    evidence_by_id: dict[str, dict] = {}
    seen_sha: set[str] = set()
    terminals_by_id: dict[str, dict | None] = {}
    for evidence in doc.evidence:
        evidence_id = evidence.get("id")
        if not isinstance(evidence_id, str) or not evidence_id or evidence_id in evidence_by_id:
            err(2, "invariant 2 (real): evidence ids must be unique")
            continue
        evidence_by_id[evidence_id] = evidence
        kind = evidence.get("kind")
        if kind not in EVIDENCE_KINDS:
            err(2, f"invariant 2 (real): invalid kind for {evidence_id!r}")
            continue
        if kind == "bundle":
            continue
        gate = gates.get(evidence.get("gate"))
        check = next((item for item in gate.checks if item.id == evidence.get("check")), None) if gate else None
        if gate is None or check is None or evidence.get("issuerRole") != gate.owner or kind != check.evidence_kind:
            err(5, f"invariant 5 (authority): invalid evidence identity for {evidence_id!r}")
        artifact = _safe_artifact(workspace, evidence.get(_ARTIFACT_FIELD[kind]))
        declared_sha = evidence.get("artifactSha256")
        if artifact is None or not artifact.is_file() or not isinstance(declared_sha, str):
            err(2, f"invariant 2 (real): artifact missing for {evidence_id!r}")
            continue
        if declared_sha in seen_sha or sha256(artifact) != declared_sha:
            err(2, f"invariant 2 (real): checksum invalid or duplicate for {evidence_id!r}")
        seen_sha.add(declared_sha)
        records = read_jsonl(artifact)
        terminal = records[-1] if records else None
        terminals_by_id[evidence_id] = terminal
        gate_id, check_id = evidence.get("gate"), evidence.get("check")
        if not terminal_matches(terminal, evidence_id, gate_id, check_id):
            err(2, f"invariant 2 (real): terminal record invalid for {evidence_id!r}")
        elif kind in {"command", "basis"}:
            if len(records) != 1:
                err(2, f"invariant 2 (real): artifact for {evidence_id!r} must hold exactly one record")
            elif check is not None and not command_outcome_ok(check, terminal):
                err(9, f"invariant 9 (execution): command outcome invalid for {evidence_id!r}")
        elif kind == "review":
            if terminal.get("type") != "review_terminal" or terminal.get("verdict") != PASS:
                err(2, f"invariant 2 (real): review terminal invalid for {evidence_id!r}")
            elif gate is not None and not review_scope_ok(gate.review_dimensions, terminal):
                err(11, f"invariant 11 (complete): review transcript incomplete for {evidence_id!r}")
            elif not _independent_review(evidence, terminal):
                err(7, f"invariant 7 (review): invalid independent review for {evidence_id!r}")
        if kind == "basis" and gate is not None:
            expected = sorted(entry["path"] for entry in doc.inputs if entry.get("type") in gate.invalidates_on)
            classified = {item.get("path") for item in evidence.get("classifiedRefs") or [] if isinstance(item, dict)}
            scope = evidence.get("scope") or []
            if sorted(scope) != expected or not set(scope).issubset(classified):
                err(2, f"invariant 2 (real): basis coverage incomplete for {evidence_id!r}")
    for receipt in doc.receipts:
        gate = gates.get(receipt.get("gate"))
        if gate is None or receipt.get("status") not in {PASS, INAPPLICABLE}:
            continue
        bundle = evidence_by_id.get(receipt.get("evidence", "").removeprefix("bundle="))
        if not bundle or bundle.get("kind") != "bundle":
            err(2, f"invariant 2 (real): terminal {gate.id} lacks bundle")
            continue
        if bundle.get("gate") != gate.id or bundle.get("issuerRole") != gate.owner:
            err(5, f"invariant 5 (authority): bundle authority invalid for {gate.id}")
        adapter = adapters_by_role.get(gate.owner)
        if adapter is None or gate.id not in adapter.gates:
            err(5, f"invariant 5 (authority): missing owner adapter for {gate.id}")
        elif set(adapter.gates[gate.id].checks) != {check.id for check in gate.checks}:
            err(5, f"invariant 5 (authority): adapter bindings do not match {gate.id}")
        bundle_fp = bundle.get("inputFingerprint")
        if receipt.get("fingerprint") != bundle_fp:
            err(3, f"invariant 3 (bind): receipt/bundle mismatch for {gate.id}")
        try:
            computed = fingerprint_for_gate(doc, gate, workspace, adapter)
        except ValueError as exc:
            err(4, f"invariant 4 (state): {exc}")
            computed = None
        if computed and receipt.get("fingerprint") != computed:
            err(4, f"invariant 4 (state): stale receipt for {gate.id}")
        child_ids = bundle.get("checkEvidence") or []
        if (not isinstance(child_ids, list) or any(not isinstance(child_id, str) for child_id in child_ids)
                or len(child_ids) != len(set(child_ids))):
            err(2, f"invariant 2 (real): invalid bundle members for {gate.id}")
            continue
        children = [evidence_by_id.get(child_id) for child_id in child_ids]
        if any(child is None for child in children):
            err(2, f"invariant 2 (real): missing bundle member for {gate.id}")
            continue
        check_ids = {check.id for check in gate.checks}
        if receipt["status"] == PASS:
            if {child.get("check") for child in children if child} != check_ids or len(children) != len(check_ids):
                err(2, f"invariant 2 (real): bundle does not cover all checks for {gate.id}")
        if receipt["status"] == INAPPLICABLE:
            if bundle.get("reasonCode") not in gate.inapplicable_reason_codes:
                err(8, f"invariant 8 (reasoned): invalid reason for {gate.id}")
            if child_ids:
                err(8, f"invariant 8 (reasoned): inapplicable {gate.id} must not include check evidence")
        checks_by_id = {check.id: check for check in gate.checks}
        for child in children:
            check = checks_by_id.get(child.get("check"))
            if (check is None or child.get("gate") != gate.id or child.get("issuerRole") != gate.owner
                    or child.get("kind") != check.evidence_kind):
                err(5, f"invariant 5 (authority): invalid check evidence in {gate.id}")
                continue
            if child.get("inputFingerprint") != bundle_fp:
                err(3, f"invariant 3 (bind): check/bundle mismatch in {gate.id}")
            if check.evidence_kind == "review" and not _independent_review(child, terminals_by_id.get(child["id"])):
                err(7, f"invariant 7 (review): invalid independent review in {gate.id}")
    input_paths = {entry.get("path") for entry in doc.inputs if isinstance(entry, dict)}
    task_ids = {task.id for task in doc.subtasks}
    if len(task_ids) != len(doc.subtasks) or "" in task_ids:
        err(6, "invariant 6 (bounded): subtask ids must be unique")
    for task in doc.subtasks:
        if not task.acceptance.strip() or any(path not in input_paths for path in task.scope()):
            err(6, f"invariant 6 (bounded): invalid scope or acceptance for {task.id}")
        if any(dep not in task_ids or dep == task.id for dep in task.depends_on):
            err(6, f"invariant 6 (bounded): invalid dependency for {task.id}")
    dependencies = {task.id: set(task.depends_on) for task in doc.subtasks}
    if _has_cycle(dependencies):
        err(6, "invariant 6 (bounded): subtask dependencies must be acyclic")
    for index, left in enumerate(doc.subtasks):
        for right in doc.subtasks[index + 1:]:
            if _conflicts(left, right, dependencies):
                err(6, f"invariant 6 (bounded): conflicting subtasks {left.id}/{right.id} need dependency")
    return errors
