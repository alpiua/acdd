from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

FINGERPRINT_RE = re.compile(r"sha256:[0-9a-f]{64}")


class ArchitectureVerificationError(ValueError):
    pass


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ArchitectureVerificationError(f"{label}: expected a mapping")
    return value


def _strings(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ArchitectureVerificationError(f"{label}: expected a non-empty-string list")
    if len(value) != len(set(value)):
        raise ArchitectureVerificationError(f"{label}: duplicate values are not allowed")
    return list(value)


def _fingerprint(value: object, label: str) -> str:
    if not isinstance(value, str) or FINGERPRINT_RE.fullmatch(value) is None:
        raise ArchitectureVerificationError(f"{label}: invalid sha256 fingerprint")
    return value


def _uuid(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ArchitectureVerificationError(f"{label}: expected UUID string")
    try:
        UUID(value)
    except ValueError as exc:
        raise ArchitectureVerificationError(f"{label}: invalid UUID") from exc
    return value


DISCOVERY_CAPABILITIES = {
    "exactText": "source_map",
    "structural": "structural_search",
    "dependency": "impact",
}

PARTITION_FINDING_FIELDS = {
    "id",
    "defectKind",
    "candidateDefect",
    "taskEvidence",
    "codeEvidence",
    "requiredTaskChange",
}
PARTITION_DEFECT_KINDS = {
    "missing-requirement",
    "contradiction",
    "infeasible-boundary",
    "incomplete-propagation",
    "unprovable-acceptance",
}
USAGE_FIELDS = {"input", "output", "cacheRead", "cacheWrite", "cost", "totalTokens"}
REQUIRED_GUIDANCE_AXES = frozenset(
    {
        "canonical-owner",
        "production-path",
        "contract-propagation",
        "authority-identity",
        "lifecycle-failure-rollback-cleanup",
        "alternate-path-compatibility",
        "persisted-contract-parity",
        "impact-scope",
        "negative-cross-boundary-proof",
        "contradiction-blockers",
        "canonical-normalization",
        "authorization-before-selection",
        "terminal-outcome-truth",
        "terminal-projection-truth",
    }
)


def _validate_discovery(value: object, label: str) -> None:
    discovery = _mapping(value, label)
    if set(discovery) != {"repositoryRoot", "methods"}:
        raise ArchitectureVerificationError(
            f"{label}: expected repositoryRoot and methods only"
        )
    repository_root = discovery.get("repositoryRoot")
    if not isinstance(repository_root, str) or not repository_root.strip():
        raise ArchitectureVerificationError(f"{label}.repositoryRoot must be non-empty")
    methods = _mapping(discovery.get("methods"), f"{label}.methods")
    if set(methods) != set(DISCOVERY_CAPABILITIES):
        raise ArchitectureVerificationError(
            f"{label}.methods must contain exactText, structural, and dependency"
        )
    for method, required_capability in DISCOVERY_CAPABILITIES.items():
        receipt = _mapping(methods.get(method), f"{label}.methods.{method}")
        if set(receipt) != {"capability", "tools", "queries", "complete"}:
            raise ArchitectureVerificationError(
                f"{label}.methods.{method} must contain capability, tools, queries, and complete only"
            )
        if receipt.get("capability") != required_capability:
            raise ArchitectureVerificationError(
                f"{label}.methods.{method}.capability must be {required_capability!r}"
            )
        _strings(receipt.get("tools"), f"{label}.methods.{method}.tools")
        _strings(receipt.get("queries"), f"{label}.methods.{method}.queries")
        if receipt.get("complete") is not True:
            raise ArchitectureVerificationError(
                f"{label}.methods.{method}.complete must be true"
            )


def validate_partition_output(
    value: object,
    schema: dict[str, Any],
    *,
    label: str,
    expected_id: str | None = None,
    expected_fingerprint: str | None = None,
    expected_value_domain_ids: set[str] | frozenset[str] | None = None,
    expected_document: Path | None = None,
    expected_task_paths: set[str] | frozenset[str] | None = None,
    expected_coverage_paths: set[str] | frozenset[str] | None = None,
    expected_repository_root: str | None = None,
) -> tuple[str, str, set[str]]:
    partition = _mapping(value, label)
    required = set(schema["partitionRequiredFields"])
    blocked = set(schema["partitionForbiddenFields"]) & set(partition)
    if blocked:
        raise ArchitectureVerificationError(f"{label} cannot contain {sorted(blocked)}")
    if frozenset(partition) not in {
        frozenset(required),
        frozenset({*required, "contextReceipt"}),
    }:
        raise ArchitectureVerificationError(
            f"{label} fields must match the base or context-receipt partition contract"
        )
    partition_id = partition.get("id")
    if not isinstance(partition_id, str) or not partition_id.strip():
        raise ArchitectureVerificationError(f"{label}.id must be a non-empty string")
    if expected_id is not None and partition_id != expected_id:
        raise ArchitectureVerificationError(f"{label}.id must be {expected_id!r}")
    fingerprint = _fingerprint(partition.get("inputFingerprint"), f"{label}.inputFingerprint")
    if expected_fingerprint is not None and fingerprint != expected_fingerprint:
        raise ArchitectureVerificationError(f"{label}.inputFingerprint must match the review input")
    if expected_repository_root is not None:
        repository_root = partition.get("discovery")
        actual_root = repository_root.get("repositoryRoot") if isinstance(repository_root, dict) else None
        try:
            expected_path = Path(str(expected_repository_root)).resolve()
            actual_path = Path(str(actual_root)) if actual_root is not None else None
            if actual_path is not None and not actual_path.is_absolute():
                actual_path = expected_path / actual_path
            actual_root = actual_path.resolve().as_posix() if actual_path is not None else None
            expected_root = expected_path.as_posix()
        except (OSError, ValueError):
            actual_root = None
            expected_root = ""
        if actual_root != expected_root:
            raise ArchitectureVerificationError(
                f"{label}.discovery.repositoryRoot must match the bound repository root"
            )
    status = partition.get("status")
    if status not in {"pass", "fail"}:
        raise ArchitectureVerificationError(f"{label}.status must be pass or fail")
    if partition.get("isolated") is not True or partition.get("readOnly") is not True:
        raise ArchitectureVerificationError(f"{label} must be isolated and read-only")
    if "contextReceipt" in partition:
        context_receipt = _mapping(
            partition.get("contextReceipt"), f"{label}.contextReceipt"
        )
        if set(context_receipt) != {
            "manifestSha256",
            "sourcesRead",
            "retrievals",
        }:
            raise ArchitectureVerificationError(
                f"{label}.contextReceipt has invalid fields"
            )
        _fingerprint(
            context_receipt.get("manifestSha256"),
            f"{label}.contextReceipt.manifestSha256",
        )
        _strings(
            context_receipt.get("sourcesRead"),
            f"{label}.contextReceipt.sourcesRead",
        )
        _strings(
            context_receipt.get("retrievals"),
            f"{label}.contextReceipt.retrievals",
        )
    evidence = _strings(partition.get("evidence"), f"{label}.evidence")
    if any(re.fullmatch(r".+:[1-9][0-9]*", item) is None for item in evidence):
        raise ArchitectureVerificationError(f"{label}.evidence items must use path:line strings")
    _validate_discovery(partition.get("discovery"), f"{label}.discovery")
    findings = partition.get("findings")
    if not isinstance(findings, list):
        raise ArchitectureVerificationError(f"{label}.findings must be a list")
    finding_ids: list[str] = []
    for index, raw_finding in enumerate(findings):
        finding_label = f"{label}.findings[{index}]"
        finding = _mapping(raw_finding, finding_label)
        if set(finding) != PARTITION_FINDING_FIELDS:
            raise ArchitectureVerificationError(
                f"{finding_label} fields must exactly match {sorted(PARTITION_FINDING_FIELDS)}"
            )
        for field in ("id", "candidateDefect", "requiredTaskChange"):
            field_value = finding.get(field)
            if not isinstance(field_value, str) or not field_value.strip():
                raise ArchitectureVerificationError(f"{finding_label}.{field} must be non-empty")
        finding_ids.append(str(finding["id"]))
        if finding.get("defectKind") not in PARTITION_DEFECT_KINDS:
            raise ArchitectureVerificationError(
                f"{finding_label}.defectKind must be one of {sorted(PARTITION_DEFECT_KINDS)}"
            )
        for field in ("taskEvidence", "codeEvidence"):
            refs = _strings(finding.get(field), f"{finding_label}.{field}")
            if any(re.fullmatch(r".+:[1-9][0-9]*", item) is None for item in refs):
                raise ArchitectureVerificationError(
                    f"{finding_label}.{field} items must use path:line strings"
                )
            if field == "codeEvidence" and expected_coverage_paths is not None:
                for reference in refs:
                    path = reference.rsplit(":", 1)[0].replace("\\", "/")
                    if path not in expected_coverage_paths:
                        raise ArchitectureVerificationError(
                            f"{finding_label}.codeEvidence must reference bound coverage"
                        )
        if expected_document is not None:
            task_refs = list(finding["taskEvidence"])
            expected_paths = expected_task_paths or {expected_document.name}
            if any(
                item.rsplit(":", 1)[0].replace("\\", "/") not in expected_paths
                for item in task_refs
            ):
                raise ArchitectureVerificationError(
                    f"{finding_label}.taskEvidence must reference the bound task document"
                )
    if len(finding_ids) != len(set(finding_ids)):
        raise ArchitectureVerificationError(f"{label}.finding ids must be unique")
    if status == "pass" and findings:
        raise ArchitectureVerificationError(f"{label} cannot pass with findings")
    if status == "fail" and not findings:
        raise ArchitectureVerificationError(f"{label} cannot fail without a candidate-design finding")
    mappings = partition.get("persistedContractMappings")
    if not isinstance(mappings, list) or not all(
        isinstance(item, str) and item.strip() for item in mappings
    ):
        raise ArchitectureVerificationError(
            f"{label}.persistedContractMappings must be a string list"
        )
    if len(mappings) != len(set(mappings)):
        raise ArchitectureVerificationError(
            f"{label}.persistedContractMappings cannot contain duplicates"
        )
    expected_domains = set(expected_value_domain_ids or ())
    if expected_value_domain_ids is not None and not set(mappings) <= expected_domains:
        raise ArchitectureVerificationError(f"{label} maps unknown persisted contracts")
    if expected_value_domain_ids is not None and partition_id in {"contract", "persistence"} and set(mappings) != expected_domains:
        raise ArchitectureVerificationError(
            f"{label}.persistedContractMappings must exactly cover the task domain IDs"
        )
    return partition_id, str(status), set(mappings)


RECONCILED_RECOMMENDATION_FIELDS = {
    "id",
    "sourceFindings",
    "invariant",
    "rootCause",
    "canonicalOwner",
    "requiredChange",
    "propagation",
    "prohibitedShortcuts",
    "acceptanceProof",
    "evidence",
}
RECONCILED_RECOMMENDATION_DECISION_FIELDS = {
    *RECONCILED_RECOMMENDATION_FIELDS,
    "userDecisionRequired",
    "decisionOptions",
}


def _validate_reconciled_recommendations(
    coordinator: dict[str, Any],
    partitions: list[object],
    verdict: str,
) -> list[dict[str, Any]]:
    raw_refs = {
        f"{partition['id']}:{index}"
        for partition in partitions
        if isinstance(partition, dict)
        for index, _ in enumerate(partition.get("findings", []), 1)
    }
    resolved = coordinator.get("resolvedFindings", [])
    if not isinstance(resolved, list) or not all(
        isinstance(item, str) and item.strip() for item in resolved
    ):
        raise ArchitectureVerificationError(
            "coordinator.resolvedFindings must be a string list"
        )
    if len(resolved) != len(set(resolved)):
        raise ArchitectureVerificationError(
            "coordinator.resolvedFindings cannot contain duplicates"
        )
    raw = coordinator.get("reconciledRecommendations")
    if not isinstance(raw, list):
        raise ArchitectureVerificationError(
            "coordinator.reconciledRecommendations must be a list"
        )
    if verdict == "PASS" and raw:
        raise ArchitectureVerificationError(
            "PASS cannot contain reconciled recommendations"
        )
    if verdict == "FAIL" and not raw:
        raise ArchitectureVerificationError(
            "FAIL must contain an architecturally complete reconciled recommendation"
        )
    recommendations: list[dict[str, Any]] = []
    covered_refs: list[str] = list(resolved)
    ids: list[str] = []
    for index, value in enumerate(raw):
        label = f"coordinator.reconciledRecommendations[{index}]"
        recommendation = _mapping(value, label)
        if frozenset(recommendation) not in {
            frozenset(RECONCILED_RECOMMENDATION_FIELDS),
            frozenset(RECONCILED_RECOMMENDATION_DECISION_FIELDS),
        }:
            raise ArchitectureVerificationError(
                f"{label} fields must match the legacy or decision-aware recommendation contract"
            )
        recommendation_id = recommendation.get("id")
        if not isinstance(recommendation_id, str) or not recommendation_id.strip():
            raise ArchitectureVerificationError(f"{label}.id must be non-empty")
        ids.append(recommendation_id)
        for field in (
            "invariant",
            "rootCause",
            "canonicalOwner",
            "requiredChange",
        ):
            field_value = recommendation.get(field)
            if not isinstance(field_value, str) or not field_value.strip():
                raise ArchitectureVerificationError(f"{label}.{field} must be non-empty")
        source_refs = _strings(recommendation.get("sourceFindings"), f"{label}.sourceFindings")
        covered_refs.extend(source_refs)
        for field in (
            "propagation",
            "prohibitedShortcuts",
            "acceptanceProof",
            "evidence",
        ):
            values = _strings(recommendation.get(field), f"{label}.{field}")
            if field == "evidence" and any(
                re.fullmatch(r".+:[1-9][0-9]*", item) is None for item in values
            ):
                raise ArchitectureVerificationError(
                    f"{label}.evidence items must use path:line strings"
                )
        if "userDecisionRequired" in recommendation:
            decision_required = recommendation.get("userDecisionRequired")
            options = recommendation.get("decisionOptions")
            if not isinstance(decision_required, bool):
                raise ArchitectureVerificationError(
                    f"{label}.userDecisionRequired must be boolean"
                )
            if not isinstance(options, list) or not all(
                isinstance(item, str) and item.strip() for item in options
            ):
                raise ArchitectureVerificationError(
                    f"{label}.decisionOptions must be a string list"
                )
            if decision_required and (
                len(options) < 2
                or not any(item.startswith("update-task:") for item in options)
                or not any(item.startswith("create-linked-plan:") for item in options)
            ):
                raise ArchitectureVerificationError(
                    f"{label}: ambiguous architecture requires update-task and create-linked-plan options"
                )
            if not decision_required and options:
                raise ArchitectureVerificationError(
                    f"{label}: decisionOptions must be empty when no user decision is required"
                )
        recommendations.append(recommendation)
    if len(ids) != len(set(ids)):
        raise ArchitectureVerificationError("reconciled recommendation ids must be unique")
    if len(covered_refs) != len(set(covered_refs)):
        raise ArchitectureVerificationError(
            "each source finding must be resolved or belong to exactly one reconciled recommendation"
        )
    if set(covered_refs) != raw_refs:
        raise ArchitectureVerificationError(
            "resolved findings and reconciled recommendations must cover every inspector finding exactly once"
        )
    return recommendations


def _validate_usage(value: object, label: str = "result.usage") -> None:
    usage = _mapping(value, label)
    if set(usage) != {"launches", "totals"}:
        raise ArchitectureVerificationError(f"{label} must contain launches and totals only")
    launches = usage.get("launches")
    if not isinstance(launches, list):
        raise ArchitectureVerificationError(f"{label}.launches must be a list")
    sums = {field: 0 for field in USAGE_FIELDS}
    for index, raw in enumerate(launches):
        item_label = f"{label}.launches[{index}]"
        item = _mapping(raw, item_label)
        required = {
            "role", "partition", "attempt", "sessionUuid", "available", *USAGE_FIELDS
        }
        if set(item) != required:
            raise ArchitectureVerificationError(
                f"{item_label} fields must exactly match {sorted(required)}"
            )
        if item.get("role") not in {"inspector", "coordinator"}:
            raise ArchitectureVerificationError(f"{item_label}.role is invalid")
        if not isinstance(item.get("partition"), str) or not item["partition"].strip():
            raise ArchitectureVerificationError(f"{item_label}.partition must be non-empty")
        if not isinstance(item.get("attempt"), int) or item["attempt"] < 1:
            raise ArchitectureVerificationError(f"{item_label}.attempt must be positive")
        _uuid(item.get("sessionUuid"), f"{item_label}.sessionUuid")
        if not isinstance(item.get("available"), bool):
            raise ArchitectureVerificationError(f"{item_label}.available must be boolean")
        for field in USAGE_FIELDS:
            number = item.get(field)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or number < 0:
                raise ArchitectureVerificationError(f"{item_label}.{field} must be non-negative")
            sums[field] += number
        if item["totalTokens"] != (
            item["input"] + item["output"] + item["cacheRead"] + item["cacheWrite"]
        ):
            raise ArchitectureVerificationError(f"{item_label}.totalTokens is inconsistent")
        if item["available"] is False and any(item[field] != 0 for field in USAGE_FIELDS):
            raise ArchitectureVerificationError(f"{item_label} unavailable usage must be zero")
    totals = _mapping(usage.get("totals"), f"{label}.totals")
    if set(totals) != USAGE_FIELDS:
        raise ArchitectureVerificationError(
            f"{label}.totals fields must exactly match {sorted(USAGE_FIELDS)}"
        )
    if any(totals[field] != sums[field] for field in USAGE_FIELDS):
        raise ArchitectureVerificationError(f"{label}.totals must equal launch sums")


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ArchitectureVerificationError(f"cannot load {path}: {exc}") from exc
    return _mapping(value, str(path))


def validate_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if schema.get("apiVersion") != "acdd/architecture-verification-schema/v1":
        raise ArchitectureVerificationError("unsupported architecture verification schema")
    if schema.get("kind") != "architecture-verification-schema":
        raise ArchitectureVerificationError("architecture verification schema kind is invalid")
    required_capabilities = _strings(
        schema.get("requiredCapabilities"), "schema.requiredCapabilities"
    )
    if set(required_capabilities) != {"independent_review", "review_execution"}:
        raise ArchitectureVerificationError(
            "schema.requiredCapabilities must require independent_review and review_execution"
        )
    if schema.get("maxParallelInspectors") != 4:
        raise ArchitectureVerificationError("schema.maxParallelInspectors must be 4")
    required_guidance_axes = set(
        _strings(schema.get("requiredGuidanceAxes"), "schema.requiredGuidanceAxes")
    )
    if required_guidance_axes != REQUIRED_GUIDANCE_AXES:
        raise ArchitectureVerificationError(
            "schema.requiredGuidanceAxes must define the canonical architecture guidance axes"
        )
    inspector = _mapping(schema.get("inspectorPolicy"), "schema.inspectorPolicy")
    expected_inspector = {
        "readOnly": True,
        "mayWriteTask": False,
        "mayIssueReceipt": False,
        "mayReturnVerdict": False,
        "inputFingerprint": "shared",
    }
    if inspector != expected_inspector:
        raise ArchitectureVerificationError(
            "schema.inspectorPolicy must be read-only, non-writing, non-receipt, non-verdict, and shared-fingerprint"
        )
    coordinator = _mapping(schema.get("coordinatorPolicy"), "schema.coordinatorPolicy")
    for field, expected in {
        "authoritativeSessions": 1,
        "requireEveryPartition": True,
        "requireFindingReconciliation": True,
        "requirePersistedContractReconciliation": True,
        "allowResolvedFindings": True,
        "verdictOwner": "coordinator",
    }.items():
        if coordinator.get(field) != expected:
            raise ArchitectureVerificationError(
                f"schema.coordinatorPolicy.{field} must be {expected!r}"
            )
    finding_contract = _mapping(schema.get("findingContract"), "schema.findingContract")
    if set(_strings(finding_contract.get("requiredFields"), "schema.findingContract.requiredFields")) != PARTITION_FINDING_FIELDS:
        raise ArchitectureVerificationError("schema.findingContract.requiredFields must define the typed candidate finding")
    if set(_strings(finding_contract.get("defectKinds"), "schema.findingContract.defectKinds")) != PARTITION_DEFECT_KINDS:
        raise ArchitectureVerificationError("schema.findingContract.defectKinds must define the supported candidate defects")
    if finding_contract.get("currentCodeOnlyIsFinding") is not False:
        raise ArchitectureVerificationError("schema.findingContract.currentCodeOnlyIsFinding must be false")
    forbidden = set(_strings(schema.get("partitionForbiddenFields"), "schema.partitionForbiddenFields"))
    if forbidden != {"receipt", "verdict"}:
        raise ArchitectureVerificationError(
            "schema.partitionForbiddenFields must forbid receipt and verdict"
        )
    partition_required = set(
        _strings(schema.get("partitionRequiredFields"), "schema.partitionRequiredFields")
    )
    if partition_required != {
        "id",
        "status",
        "inputFingerprint",
        "evidence",
        "findings",
        "discovery",
        "persistedContractMappings",
        "isolated",
        "readOnly",
    }:
        raise ArchitectureVerificationError(
            "schema.partitionRequiredFields must define the typed partition output"
        )
    result_required = set(
        _strings(schema.get("resultRequiredFields"), "schema.resultRequiredFields")
    )
    if result_required != {
        "inputFingerprint",
        "runtime",
        "capabilities",
        "isolated",
        "readOnly",
        "authoritativeSessionUuids",
        "persistedContractIds",
        "partitions",
        "coordinator",
    }:
        raise ArchitectureVerificationError(
            "schema.resultRequiredFields must define the coordinator result"
        )
    return schema


def validate_contract(
    contract: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    validate_schema(schema)
    if contract.get("apiVersion") != "acdd/architecture-verification/v1":
        raise ArchitectureVerificationError("unsupported architecture verification contract")
    if contract.get("kind") != "architecture-verification":
        raise ArchitectureVerificationError("architecture verification contract kind is invalid")
    inspectors = contract.get("inspectors")
    if not isinstance(inspectors, list) or len(inspectors) != 4:
        raise ArchitectureVerificationError("contract.inspectors must contain exactly four partitions")
    ids: list[str] = []
    covered_axes: set[str] = set()
    for index, raw in enumerate(inspectors):
        inspector = _mapping(raw, f"contract.inspectors[{index}]")
        inspector_id = inspector.get("id")
        if not isinstance(inspector_id, str) or not inspector_id.strip():
            raise ArchitectureVerificationError(
                f"contract.inspectors[{index}].id must be a non-empty string"
            )
        ids.append(inspector_id)
        covered_axes.update(
            _strings(inspector.get("covers"), f"contract.inspectors[{index}].covers")
        )
        _strings(
            inspector.get("authority"), f"contract.inspectors[{index}].authority"
        )
    if len(ids) != len(set(ids)):
        raise ArchitectureVerificationError("contract inspector ids must be unique")
    missing_guidance_axes = sorted(REQUIRED_GUIDANCE_AXES - covered_axes)
    if missing_guidance_axes:
        raise ArchitectureVerificationError(
            "contract inspector coverage misses required guidance axes: "
            f"{missing_guidance_axes}"
        )
    inspector_map = {str(item["id"]): item for item in inspectors}
    for inspector_id in ("contract", "persistence"):
        inspector = inspector_map.get(inspector_id)
        if inspector is None or "persisted-contracts" not in inspector.get("covers", []):
            raise ArchitectureVerificationError(
                f"contract {inspector_id} inspector must cover persisted-contracts"
            )
    if contract.get("inspectorPolicy") != schema.get("inspectorPolicy"):
        raise ArchitectureVerificationError("contract inspectorPolicy must preserve the schema")
    contract_coordinator_policy = contract.get("coordinatorPolicy")
    schema_coordinator_policy = _mapping(schema.get("coordinatorPolicy"), "schema.coordinatorPolicy")
    compatible_coordinator_policies = [
        {
            key: value
            for key, value in schema_coordinator_policy.items()
            if key not in omitted
        }
        for omitted in (
            frozenset(),
            frozenset({"allowResolvedFindings"}),
        )
    ]
    if contract_coordinator_policy not in compatible_coordinator_policies:
        raise ArchitectureVerificationError("contract coordinatorPolicy must preserve the schema")
    if (
        "findingContract" in contract
        and contract.get("findingContract") != schema.get("findingContract")
    ):
        raise ArchitectureVerificationError("contract findingContract must preserve the schema")
    partition_output = _mapping(contract.get("partitionOutput"), "contract.partitionOutput")
    contract_required = set(
        _strings(partition_output.get("required"), "contract.partitionOutput.required")
    )
    if contract_required != set(schema["partitionRequiredFields"]):
        raise ArchitectureVerificationError(
            "contract partition output must preserve the schema"
        )
    if set(_strings(partition_output.get("status"), "contract.partitionOutput.status")) != {"pass", "fail"}:
        raise ArchitectureVerificationError(
            "contract partition status must be pass or fail"
        )
    receipt = _mapping(contract.get("receiptValidation"), "contract.receiptValidation")
    required = set(
        _strings(receipt.get("requiredCapabilities"), "contract.receiptValidation.requiredCapabilities")
    )
    if required != set(schema["requiredCapabilities"]):
        raise ArchitectureVerificationError(
            "contract receipt capabilities must preserve the schema"
        )
    for field in ("requireIsolated", "requireReadOnly", "requireCompleteCoverage"):
        if receipt.get(field) is not True:
            raise ArchitectureVerificationError(
                f"contract.receiptValidation.{field} must be true"
            )
    if receipt.get("equivalentRuntimesAllowed") is not True:
        raise ArchitectureVerificationError(
            "contract receipt validation must be capability-based, not runtime-label based"
        )
    return contract


def validate_result(
    contract: dict[str, Any],
    schema: dict[str, Any],
    result: dict[str, Any],
    *,
    expected_value_domain_ids: set[str] | None = None,
    expected_document: Path | None = None,
    expected_repository_root: str | None = None,
    expected_task_paths: set[str] | frozenset[str] | None = None,
    expected_coverage_paths: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    validate_contract(contract, schema)
    missing_result = set(schema["resultRequiredFields"]) - set(result)
    if missing_result:
        raise ArchitectureVerificationError(
            f"result misses required fields {sorted(missing_result)}"
        )
    if "usage" in result:
        _validate_usage(result.get("usage"))
    fingerprint = _fingerprint(result.get("inputFingerprint"), "result.inputFingerprint")
    runtime = result.get("runtime")
    if not isinstance(runtime, str) or not runtime.strip():
        raise ArchitectureVerificationError("result.runtime must record provenance")
    required_capabilities = set(schema["requiredCapabilities"])
    capabilities = set(_strings(result.get("capabilities"), "result.capabilities"))
    missing = required_capabilities - capabilities
    if missing:
        raise ArchitectureVerificationError(
            f"result capabilities miss {sorted(missing)}"
        )
    if result.get("isolated") is not True or result.get("readOnly") is not True:
        raise ArchitectureVerificationError("result must be isolated and read-only")
    sessions = result.get("authoritativeSessionUuids")
    if not isinstance(sessions, list) or len(sessions) != 1:
        raise ArchitectureVerificationError(
            "result must contain exactly one authoritative session UUID"
        )
    _uuid(sessions[0], "result.authoritativeSessionUuids[0]")
    value_domain_ids = result.get("persistedContractIds")
    if not isinstance(value_domain_ids, list) or not all(
        isinstance(item, str) and item.strip() for item in value_domain_ids
    ):
        raise ArchitectureVerificationError(
            "result.persistedContractIds must be a string list"
        )
    if len(value_domain_ids) != len(set(value_domain_ids)):
        raise ArchitectureVerificationError(
            "result.persistedContractIds cannot contain duplicates"
        )
    expected_domains = expected_value_domain_ids or set()
    if set(value_domain_ids) != expected_domains:
        raise ArchitectureVerificationError(
            "result.persistedContractIds must exactly match the task persisted-contract matrix"
        )
    partitions = result.get("partitions")
    if not isinstance(partitions, list):
        raise ArchitectureVerificationError("result.partitions must be a list")
    expected_ids = [str(item["id"]) for item in contract["inspectors"]]
    actual_ids: list[str] = []
    statuses: list[str] = []
    partition_value_domains: dict[str, set[str]] = {}
    for index, raw in enumerate(partitions):
        partition_id, status, mappings = validate_partition_output(
            raw,
            schema,
            label=f"result.partitions[{index}]",
            expected_fingerprint=fingerprint,
            expected_value_domain_ids=expected_domains,
            expected_document=expected_document,
            expected_task_paths=expected_task_paths,
            expected_coverage_paths=expected_coverage_paths,
            expected_repository_root=expected_repository_root,
        )
        actual_ids.append(partition_id)
        statuses.append(status)
        partition_value_domains[partition_id] = mappings
    if actual_ids != expected_ids:
        raise ArchitectureVerificationError(
            f"result must cover every partition in contract order: {expected_ids}"
        )
    coordinator = _mapping(result.get("coordinator"), "result.coordinator")
    if _uuid(coordinator.get("sessionUuid"), "result.coordinator.sessionUuid") != sessions[0]:
        raise ArchitectureVerificationError(
            "coordinator must own the authoritative session"
        )
    verdict = coordinator.get("verdict")
    if verdict not in {"PASS", "FAIL"}:
        raise ArchitectureVerificationError("coordinator verdict must be PASS or FAIL")
    if coordinator.get("findingsReconciled") is not True:
        raise ArchitectureVerificationError(
            "coordinator must reconcile partition findings"
        )
    if coordinator.get("persistedContractsReconciled") is not True:
        raise ArchitectureVerificationError(
            "coordinator must reconcile persisted persisted contracts"
        )
    expected_coordinator_fields = {
        "sessionUuid",
        "verdict",
        "findingsReconciled",
        "persistedContractsReconciled",
        "reconciledRecommendations",
        "resolvedFindings",
    }
    legacy_coordinator_fields = expected_coordinator_fields - {"resolvedFindings"}
    if frozenset(coordinator) not in {
        frozenset(expected_coordinator_fields),
        frozenset(legacy_coordinator_fields),
    }:
        raise ArchitectureVerificationError(
            "coordinator fields must match the v1 fields with optional resolvedFindings"
        )
    _validate_reconciled_recommendations(coordinator, partitions, str(verdict))
    for partition_id in ("contract", "persistence"):
        if partition_value_domains.get(partition_id) != expected_domains:
            raise ArchitectureVerificationError(
                f"{partition_id} partition must map every persisted persisted contract"
            )
    if verdict == "FAIL" and all(status == "pass" for status in statuses):
        raise ArchitectureVerificationError(
            "coordinator cannot FAIL when every partition passes"
        )
    return result


def validate_retry_fingerprint(
    failed_result: dict[str, Any], next_fingerprint: object
) -> str:
    coordinator = _mapping(failed_result.get("coordinator"), "failed_result.coordinator")
    if coordinator.get("verdict") != "FAIL":
        raise ArchitectureVerificationError("only a FAIL result can enter the retry loop")
    previous = _fingerprint(
        failed_result.get("inputFingerprint"), "failed_result.inputFingerprint"
    )
    current = _fingerprint(next_fingerprint, "nextFingerprint")
    if current == previous:
        raise ArchitectureVerificationError(
            "cannot rerun an unchanged FAIL fingerprint"
        )
    return current
