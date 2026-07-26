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


_DISCOVERY_CAPABILITIES = {
    "exactText": "source_map",
    "structural": "structural_search",
    "dependency": "impact",
}


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
    if set(methods) != set(_DISCOVERY_CAPABILITIES):
        raise ArchitectureVerificationError(
            f"{label}.methods must contain exactText, structural, and dependency"
        )
    for method, required_capability in _DISCOVERY_CAPABILITIES.items():
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
        "verdictOwner": "coordinator",
    }.items():
        if coordinator.get(field) != expected:
            raise ArchitectureVerificationError(
                f"schema.coordinatorPolicy.{field} must be {expected!r}"
            )
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
    for index, raw in enumerate(inspectors):
        inspector = _mapping(raw, f"contract.inspectors[{index}]")
        inspector_id = inspector.get("id")
        if not isinstance(inspector_id, str) or not inspector_id.strip():
            raise ArchitectureVerificationError(
                f"contract.inspectors[{index}].id must be a non-empty string"
            )
        ids.append(inspector_id)
        _strings(inspector.get("covers"), f"contract.inspectors[{index}].covers")
        _strings(
            inspector.get("authority"), f"contract.inspectors[{index}].authority"
        )
    if len(ids) != len(set(ids)):
        raise ArchitectureVerificationError("contract inspector ids must be unique")
    inspector_map = {str(item["id"]): item for item in inspectors}
    for inspector_id in ("contract", "persistence"):
        inspector = inspector_map.get(inspector_id)
        if inspector is None or "persisted-contracts" not in inspector.get("covers", []):
            raise ArchitectureVerificationError(
                f"contract {inspector_id} inspector must cover persisted-contracts"
            )
    if contract.get("inspectorPolicy") != schema.get("inspectorPolicy"):
        raise ArchitectureVerificationError("contract inspectorPolicy must preserve the schema")
    if contract.get("coordinatorPolicy") != schema.get("coordinatorPolicy"):
        raise ArchitectureVerificationError("contract coordinatorPolicy must preserve the schema")
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
) -> dict[str, Any]:
    validate_contract(contract, schema)
    missing_result = set(schema["resultRequiredFields"]) - set(result)
    if missing_result:
        raise ArchitectureVerificationError(
            f"result misses required fields {sorted(missing_result)}"
        )
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
    forbidden = set(schema["partitionForbiddenFields"])
    for index, raw in enumerate(partitions):
        partition = _mapping(raw, f"result.partitions[{index}]")
        missing_partition = set(schema["partitionRequiredFields"]) - set(partition)
        if missing_partition:
            raise ArchitectureVerificationError(
                f"result.partitions[{index}] misses {sorted(missing_partition)}"
            )
        blocked = forbidden & set(partition)
        if blocked:
            raise ArchitectureVerificationError(
                f"result partition cannot contain {sorted(blocked)}"
            )
        partition_id = partition.get("id")
        if not isinstance(partition_id, str):
            raise ArchitectureVerificationError(
                f"result.partitions[{index}].id must be a string"
            )
        actual_ids.append(partition_id)
        if _fingerprint(
            partition.get("inputFingerprint"),
            f"result.partitions[{index}].inputFingerprint",
        ) != fingerprint:
            raise ArchitectureVerificationError(
                "every partition must use the shared input fingerprint"
            )
        status = partition.get("status")
        if status not in {"pass", "fail"}:
            raise ArchitectureVerificationError(
                f"result.partitions[{index}].status must be pass or fail"
            )
        statuses.append(str(status))
        _strings(partition.get("evidence"), f"result.partitions[{index}].evidence")
        _validate_discovery(
            partition.get("discovery"), f"result.partitions[{index}].discovery"
        )
        findings = partition.get("findings")
        if not isinstance(findings, list) or not all(
            isinstance(item, str) and item.strip() for item in findings
        ):
            raise ArchitectureVerificationError(
                f"result.partitions[{index}].findings must be a string list"
            )
        if status == "pass" and findings:
            raise ArchitectureVerificationError(
                f"result.partitions[{index}] cannot pass with findings"
            )
        mappings = partition.get("persistedContractMappings")
        if not isinstance(mappings, list) or not all(
            isinstance(item, str) and item.strip() for item in mappings
        ):
            raise ArchitectureVerificationError(
                f"result.partitions[{index}].persistedContractMappings must be a string list"
            )
        if len(mappings) != len(set(mappings)):
            raise ArchitectureVerificationError(
                f"result.partitions[{index}].persistedContractMappings cannot contain duplicates"
            )
        if not set(mappings) <= expected_domains:
            raise ArchitectureVerificationError(
                f"result.partitions[{index}] maps unknown persisted contracts"
            )
        partition_value_domains[partition_id] = set(mappings)
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
    for partition_id in ("contract", "persistence"):
        if partition_value_domains.get(partition_id) != expected_domains:
            raise ArchitectureVerificationError(
                f"{partition_id} partition must map every persisted persisted contract"
            )
    if verdict == "PASS" and any(status != "pass" for status in statuses):
        raise ArchitectureVerificationError(
            "coordinator cannot PASS unless every partition passes"
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
