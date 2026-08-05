"""Synthesize acdd/process-report/1 metadata from a validated document."""

from __future__ import annotations

import json
from pathlib import Path

from ._doc import relative_ref, utc_now
from .model import Document, Profile


def build_process_report(
    document: Document,
    profile: Profile,
    *,
    workspace_root: Path,
    pending_receipt: dict | None = None,
) -> dict:
    workspace_root = workspace_root.resolve()
    gates: list[dict] = []
    by_gate: dict[str, dict] = {}
    for receipt in document.receipts:
        gate_id = receipt.get("gate")
        if not isinstance(gate_id, str):
            continue
        entry = {
            "id": gate_id,
            "status": receipt.get("status"),
            "fingerprint": receipt.get("fingerprint"),
            "evidence": receipt.get("evidence"),
        }
        by_gate[gate_id] = entry
    if pending_receipt and isinstance(pending_receipt.get("gate"), str):
        gate_id = pending_receipt["gate"]
        by_gate[gate_id] = {
            "id": gate_id,
            "status": pending_receipt.get("status"),
            "fingerprint": pending_receipt.get("fingerprint"),
            "evidence": pending_receipt.get("evidence"),
        }
    for gate in profile.gates:
        if gate.id in by_gate:
            gates.append(by_gate[gate.id])
    review_refs: dict[str, str] = {}
    for item in document.evidence:
        if item.get("kind") == "review" and isinstance(item.get("transcriptRef"), str):
            review_refs["transcriptRef"] = item["transcriptRef"]
        if item.get("kind") == "bundle" and isinstance(item.get("processReportRef"), str):
            review_refs["priorProcessReportRef"] = item["processReportRef"]
    try:
        doc_rel = relative_ref(workspace_root, document.path)
    except ValueError:
        doc_rel = str(document.path)
    return {
        "type": "acdd_process_report",
        "format": "acdd/process-report/1",
        "profileId": profile.id,
        "document": doc_rel,
        "recordedAt": utc_now(),
        "gates": gates,
        "evidenceCount": len(document.evidence),
        "subtaskIds": [task.id for task in document.subtasks],
        "review": review_refs,
    }


def write_process_report(path: Path, report: dict) -> None:
    path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
