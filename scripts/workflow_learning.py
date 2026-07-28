from __future__ import annotations

import re


class WorkflowLearningError(ValueError):
    pass


ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,120}$")


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise WorkflowLearningError(f"{label} must be a mapping")
    return dict(value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise WorkflowLearningError(f"{label} must be a list of non-empty strings")
    return tuple(value)


def _text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise WorkflowLearningError(f"{label} must be a bounded non-empty string")
    return value


def validate_contract(value: object) -> dict[str, object]:
    contract = _mapping(value, "workflow-learning contract")
    if set(contract) != {
        "apiVersion",
        "kind",
        "id",
        "trigger",
        "inputs",
        "cycle",
        "output",
        "verdictEffect",
        "receiptEffect",
        "defaultDisposition",
        "dispositionEffects",
        "guidanceCompatibility",
        "scopes",
        "dispositions",
        "requiredCandidateFields",
    }:
        raise WorkflowLearningError("workflow-learning contract fields mismatch")
    expected = {
        "apiVersion": "acdd/workflow-learning/v1",
        "kind": "workflow-learning-contract",
        "id": "acdd/workflow-learning/v1",
        "trigger": "after-terminal-review-report",
        "output": "workflowLearning",
        "verdictEffect": "none",
        "receiptEffect": "none",
        "defaultDisposition": "advisory",
    }
    for field, expected_value in expected.items():
        if contract.get(field) != expected_value:
            raise WorkflowLearningError(
                f"workflow-learning contract {field} must be {expected_value}"
            )
    if tuple(_strings(contract.get("inputs"), "inputs")) != (
        "terminalReviewReport",
        "confirmedFindings",
        "guidanceSnapshot",
    ):
        raise WorkflowLearningError("workflow-learning inputs are invalid")
    cycle = contract.get("cycle")
    if not isinstance(cycle, list):
        raise WorkflowLearningError("workflow-learning cycle must be a list")
    cycle_ids: list[str] = []
    for index, raw_step in enumerate(cycle):
        step = _mapping(raw_step, f"cycle[{index}]")
        if set(step) != {"id", "action"}:
            raise WorkflowLearningError(f"cycle[{index}] fields mismatch")
        cycle_ids.append(_text(step["id"], f"cycle[{index}].id", maximum=40))
        _text(step["action"], f"cycle[{index}].action", maximum=240)
    if cycle_ids != ["cluster", "trace", "propose", "classify", "adopt"]:
        raise WorkflowLearningError("workflow-learning cycle order is invalid")
    effects = _mapping(contract.get("dispositionEffects"), "dispositionEffects")
    if effects != {
        "advisory": "record",
        "candidate-required": "open-governance-change",
        "rejected": "record-rationale",
    }:
        raise WorkflowLearningError("dispositionEffects are invalid")
    compatibility = _mapping(
        contract.get("guidanceCompatibility"), "guidanceCompatibility"
    )
    if compatibility != {
        "missingSnapshot": "historical:no-snapshot",
        "laterGuidance": "not-in-task-snapshot",
        "blockingEligibility": "in-guidance-snapshot-or-authorized-amendment",
    }:
        raise WorkflowLearningError("guidanceCompatibility is invalid")
    if tuple(_strings(contract.get("scopes"), "scopes")) != (
        "task",
        "project",
        "canonical",
    ):
        raise WorkflowLearningError("workflow-learning scopes are invalid")
    if tuple(_strings(contract.get("dispositions"), "dispositions")) != (
        "advisory",
        "candidate-required",
        "rejected",
    ):
        raise WorkflowLearningError("workflow-learning dispositions are invalid")
    if set(
        _strings(contract.get("requiredCandidateFields"), "requiredCandidateFields")
    ) != {
        "id",
        "sourceFindings",
        "missedInvariant",
        "prevention",
        "scope",
        "disposition",
    }:
        raise WorkflowLearningError("requiredCandidateFields are invalid")
    return contract


def validate_record(
    value: object, contract: dict[str, object]
) -> dict[str, object]:
    validate_contract(contract)
    record = _mapping(value, "workflowLearning")
    if set(record) != {"apiVersion", "kind", "status", "guidanceSnapshot", "candidates"}:
        raise WorkflowLearningError("workflowLearning fields mismatch")
    if record["apiVersion"] != "acdd/workflow-learning/v1":
        raise WorkflowLearningError("workflowLearning apiVersion is invalid")
    if record["kind"] != "workflow-learning":
        raise WorkflowLearningError("workflowLearning kind is invalid")
    if record["status"] != "analyzed":
        raise WorkflowLearningError("workflowLearning status must be analyzed")
    snapshot = record["guidanceSnapshot"]
    _text(snapshot, "guidanceSnapshot", maximum=160)
    candidates = record["candidates"]
    if not isinstance(candidates, list) or len(candidates) > 30:
        raise WorkflowLearningError("candidates must be a bounded list")
    required = set(
        _strings(contract["requiredCandidateFields"], "requiredCandidateFields")
    )
    scopes = set(_strings(contract["scopes"], "scopes"))
    dispositions = set(_strings(contract["dispositions"], "dispositions"))
    for index, raw_candidate in enumerate(candidates):
        candidate = _mapping(raw_candidate, f"candidates[{index}]")
        if set(candidate) != required:
            raise WorkflowLearningError(f"candidates[{index}] fields mismatch")
        if candidate["scope"] not in scopes:
            raise WorkflowLearningError(f"candidates[{index}].scope is invalid")
        if candidate["disposition"] not in dispositions:
            raise WorkflowLearningError(
                f"candidates[{index}].disposition is invalid"
            )
        for field in ("id", "missedInvariant", "prevention"):
            maximum = 121 if field == "id" else 1000 if field == "missedInvariant" else 1500
            field_value = _text(
                candidate[field],
                f"candidates[{index}].{field}",
                maximum=maximum,
            )
            if field == "id" and ID_RE.fullmatch(field_value) is None:
                raise WorkflowLearningError(f"candidates[{index}].id is invalid")
        findings = _strings(
            candidate["sourceFindings"], f"candidates[{index}].sourceFindings"
        )
        if not 1 <= len(findings) <= 50:
            raise WorkflowLearningError(
                f"candidates[{index}].sourceFindings must be bounded"
            )
        for finding_index, finding in enumerate(findings):
            _text(
                finding,
                f"candidates[{index}].sourceFindings[{finding_index}]",
                maximum=64,
            )
    return record
