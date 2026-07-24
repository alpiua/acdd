#!/usr/bin/env python3
"""Validate one explicit ACDD profile and its runtime-supplied adapters."""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from acdd_document import DocumentError, GatePolicy, validate_document
from architecture_verification import (
    ArchitectureVerificationError,
    load_yaml as load_architecture_verification_yaml,
    validate_contract as validate_architecture_verification_contract,
    validate_schema as validate_architecture_verification_schema,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = PLUGIN_ROOT / "profiles" / "task" / "v1.yaml"
PROFILE_KINDS = {"acdd/task/v1": "delivery-profile", "acdd/plan/v1": "planning-profile"}


@dataclass(frozen=True)
class GateContract:
    id: str
    capabilities: frozenset[str]
    guidance_skill: str


@dataclass(frozen=True)
class CoreContract:
    profile_path: Path
    profile: dict[str, object]
    routing: dict[str, object]
    capabilities: dict[str, object]
    adapter_contract: dict[str, object]
    receipt_contract: dict[str, object]
    receipt_contract_path: Path
    gates: tuple[GateContract, ...]
    routes: dict[str, tuple[str, ...]]
    route_executors: dict[str, str]
    architecture_verification_schema: dict[str, object] | None
    architecture_verification_schema_path: Path | None
    role_capabilities: dict[str, frozenset[str]]
    routed_roles: tuple[str, ...]

    @property
    def gate_ids(self) -> tuple[str, ...]:
        return tuple(gate.id for gate in self.gates)


class ContractError(ValueError):
    pass


def _mapping(path: Path) -> dict[str, object]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{path}: expected a YAML mapping")
    return value


def _expect(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise ContractError(f"{label}: expected {expected!r}, found {value!r}")


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
        raise ContractError(f"{label}: expected a non-empty-string list")
    if len(value) != len(set(value)):
        raise ContractError(f"{label}: duplicate values are not allowed")
    return list(value)


def _write_patterns(value: object, label: str) -> list[str]:
    patterns = _string_list(value, label)
    for pattern in patterns:
        path = PurePosixPath(pattern)
        if (
            pattern.startswith("/")
            or "\\" in pattern
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ContractError(
                f"{label}: patterns must be normalized workspace-relative paths"
            )
    return patterns


def _contract_write_policy(value: object, label: str) -> dict[str, object]:
    required = {"defaultAllow", "protectedDeny", "overrideAuthorization"}
    if not isinstance(value, dict) or set(value) != required:
        raise ContractError(f"{label} must contain exactly {sorted(required)}")
    default_allow = _write_patterns(value.get("defaultAllow"), f"{label}.defaultAllow")
    protected_deny = _write_patterns(
        value.get("protectedDeny"), f"{label}.protectedDeny"
    )
    if value.get("overrideAuthorization") != "explicit-user-request":
        raise ContractError(
            f"{label}.overrideAuthorization must be 'explicit-user-request'"
        )
    return {
        "defaultAllow": default_allow,
        "protectedDeny": protected_deny,
        "overrideAuthorization": "explicit-user-request",
    }


def _adapter_write_policy(
    value: object, core: CoreContract, label: str
) -> dict[str, object]:
    contract = _contract_write_policy(
        core.adapter_contract.get("writePolicy"), "adapter-contract.writePolicy"
    )
    if value is None:
        return {
            "allow": contract["defaultAllow"],
            "deny": [],
            "protectedAllow": [],
            "authorization": None,
        }
    allowed_fields = {"allow", "deny", "protectedAllow", "authorization"}
    if not isinstance(value, dict) or not value or set(value) - allowed_fields:
        raise ContractError(
            f"{label} must be a non-empty mapping containing only {sorted(allowed_fields)}"
        )
    allow = (
        _write_patterns(value["allow"], f"{label}.allow")
        if "allow" in value
        else list(contract["defaultAllow"])
    )
    deny = (
        _write_patterns(value["deny"], f"{label}.deny")
        if "deny" in value
        else []
    )
    protected_allow = (
        _write_patterns(value["protectedAllow"], f"{label}.protectedAllow")
        if "protectedAllow" in value
        else []
    )
    if set(allow) & set(deny):
        raise ContractError(f"{label}: allow and deny patterns overlap")
    authorization = value.get("authorization")
    if protected_allow:
        if authorization != contract["overrideAuthorization"]:
            raise ContractError(
                f"{label}.authorization must be 'explicit-user-request' "
                "when protectedAllow is declared"
            )
        broad = set(protected_allow) & set(contract["protectedDeny"])
        if broad:
            raise ContractError(
                f"{label}.protectedAllow must be narrower than protected defaults: "
                f"{sorted(broad)}"
            )
    elif authorization is not None:
        raise ContractError(
            f"{label}.authorization requires a non-empty protectedAllow"
        )
    return {
        "allow": allow,
        "deny": deny,
        "protectedAllow": protected_allow,
        "authorization": authorization,
    }


def _write_path(raw: str, label: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ContractError(f"{label}: expected a non-empty workspace-relative path")
    path = PurePosixPath(raw)
    if (
        raw.startswith("/")
        or "\\" in raw
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(marker in raw for marker in ("*", "?", "[", "]"))
    ):
        raise ContractError(f"{label}: expected one normalized concrete path")
    return path.as_posix()


def validate_adapter_write_path(
    core: CoreContract,
    adapter: dict[str, object],
    raw_path: str,
    *,
    explicit_user_request: bool = False,
) -> str:
    """Validate one concrete write against the adapter and core protection policy."""
    path = _write_path(raw_path, "write path")
    contract = _contract_write_policy(
        core.adapter_contract.get("writePolicy"), "adapter-contract.writePolicy"
    )
    policy = _adapter_write_policy(
        adapter.get("writePolicy"), core, "adapter.writePolicy"
    )
    protected = any(
        fnmatch.fnmatchcase(path, pattern)
        for pattern in contract["protectedDeny"]
    )
    protected_allowed = any(
        fnmatch.fnmatchcase(path, pattern)
        for pattern in policy["protectedAllow"]
    )
    if protected and not (explicit_user_request and protected_allowed):
        raise ContractError(
            f"write path {path!r} is protected; require a scoped protectedAllow "
            "and an explicit user request"
        )
    if any(fnmatch.fnmatchcase(path, pattern) for pattern in policy["deny"]):
        raise ContractError(f"write path {path!r} is denied by adapter.writePolicy")
    if not any(fnmatch.fnmatchcase(path, pattern) for pattern in policy["allow"]):
        raise ContractError(f"write path {path!r} is outside adapter.writePolicy.allow")
    return path


def _resolve(owner: Path, raw: object, label: str, *, allowed_root: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip() or Path(raw).is_absolute():
        raise ContractError(f"{label}: expected a non-empty relative path")
    root = allowed_root.resolve()
    path = (owner.parent / raw).resolve()
    if not path.is_relative_to(root):
        raise ContractError(f"{label}: path escapes authority root {root}")
    if not path.exists():
        raise ContractError(f"{label}: missing {raw!r} -> {path}")
    return path


def _workspace_path(raw: Path, workspace_root: Path, label: str) -> Path:
    root = workspace_root.resolve()
    path = raw.resolve()
    if not path.is_relative_to(root):
        raise ContractError(f"{label}: path escapes workspace root {root}")
    if not path.is_file():
        raise ContractError(f"{label}: missing {raw}")
    return path


def load_core(profile_path: Path = DEFAULT_PROFILE) -> CoreContract:
    profile_path = profile_path.resolve()
    authority_root = profile_path.parents[2]
    profile = _mapping(profile_path)
    api_version = profile.get("apiVersion")
    if not isinstance(api_version, str) or api_version not in PROFILE_KINDS:
        raise ContractError(f"{profile_path}: unsupported profile apiVersion {api_version!r}")
    _expect(profile.get("id"), api_version, f"{profile_path}:id")
    _expect(profile.get("kind"), PROFILE_KINDS[api_version], f"{profile_path}:kind")
    linked = {
        key: _resolve(profile_path, profile.get(key), f"profile.{key}", allowed_root=authority_root)
        for key in ("routing", "capabilityContract", "adapterContract", "receiptContract")
    }
    routing = _mapping(linked["routing"])
    capabilities = _mapping(linked["capabilityContract"])
    adapter_contract = _mapping(linked["adapterContract"])
    receipt = _mapping(linked["receiptContract"])
    _expect(routing.get("apiVersion"), api_version, "routing.apiVersion")
    _expect(routing.get("kind"), "gate-routing", "routing.kind")
    _expect(capabilities.get("apiVersion"), api_version, "capabilityContract.apiVersion")
    _expect(capabilities.get("kind"), "capability-contract", "capabilityContract.kind")
    _expect(adapter_contract.get("apiVersion"), "acdd/adapter/v1", "adapterContract.apiVersion")
    _expect(adapter_contract.get("kind"), "adapter-contract", "adapterContract.kind")
    _contract_write_policy(
        adapter_contract.get("writePolicy"), "adapter-contract.writePolicy"
    )
    _expect(receipt.get("apiVersion"), "acdd/receipt/v1", "receiptContract.apiVersion")
    _expect(receipt.get("kind"), "receipt-contract", "receiptContract.kind")
    if _resolve(linked["routing"], routing.get("profile"), "routing.profile", allowed_root=authority_root) != profile_path:
        raise ContractError("routing.profile must point back to the selected profile")
    architecture_schema_path: Path | None = None
    architecture_schema: dict[str, object] | None = None
    raw_architecture_schema = routing.get("architectureVerificationSchema")
    if api_version == "acdd/task/v1":
        architecture_schema_path = _resolve(
            linked["routing"],
            raw_architecture_schema,
            "routing.architectureVerificationSchema",
            allowed_root=authority_root,
        )
        architecture_schema = _mapping(architecture_schema_path)
        try:
            validate_architecture_verification_schema(architecture_schema)
        except ArchitectureVerificationError as exc:
            raise ContractError(str(exc)) from exc
    elif raw_architecture_schema is not None:
        raise ContractError("plan routing must not declare an architecture verification schema")

    entries = capabilities.get("capabilities")
    if not isinstance(entries, dict) or not entries:
        raise ContractError("capability contract declares no capabilities")
    for name, entry in entries.items():
        if not isinstance(name, str) or not isinstance(entry, dict) or not str(entry.get("purpose", "")).strip():
            raise ContractError("capability entries require a name and purpose")
        if entry.get("providedBy") not in {"task-adapter", "implementation-adapter", "plan-adapter"}:
            raise ContractError(f"capability {name}: unknown providedBy {entry.get('providedBy')!r}")

    required = set(_string_list(adapter_contract.get("required"), "adapter-contract.required"))
    optional = set(_string_list(adapter_contract.get("optional"), "adapter-contract.optional"))
    if required & optional:
        raise ContractError("adapter contract required and optional fields overlap")
    role_contracts = adapter_contract.get("roles")
    if not isinstance(role_contracts, dict):
        raise ContractError("adapter contract roles must be a mapping")

    gates = profile.get("gates")
    if not isinstance(gates, list) or not gates:
        raise ContractError("profile.gates: expected a non-empty list")
    gate_ids: list[str] = []
    parsed_gates: list[GateContract] = []
    queues: list[int] = []
    known_capabilities = set(entries)
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            raise ContractError(f"profile.gates[{index}]: expected a mapping")
        gate_id, queue = gate.get("id"), gate.get("queue")
        if not isinstance(gate_id, str) or re.fullmatch(r"[a-z][a-z0-9-]*/v\d+", gate_id) is None:
            raise ContractError(f"profile.gates[{index}].id: invalid {gate_id!r}")
        if not isinstance(queue, int):
            raise ContractError(f"{gate_id}.queue: expected integer")
        gate_ids.append(gate_id)
        queues.append(queue)
        gate_capabilities = frozenset(_string_list(gate.get("capabilities"), f"{gate_id}.capabilities"))
        unknown = gate_capabilities - known_capabilities
        if unknown:
            raise ContractError(f"{gate_id}: unknown capabilities {sorted(unknown)}")
        guidance = gate.get("guidance")
        if not isinstance(guidance, dict):
            raise ContractError(f"{gate_id}.guidance: skill and prompt are required")
        guidance_skill, guidance_prompt = guidance.get("skill"), guidance.get("prompt")
        if not isinstance(guidance_skill, str) or not guidance_skill.strip() or not isinstance(guidance_prompt, str) or not guidance_prompt.strip():
            raise ContractError(f"{gate_id}.guidance: skill and prompt are required")
        parsed_gates.append(GateContract(gate_id, gate_capabilities, guidance_skill))
    if len(gate_ids) != len(set(gate_ids)):
        raise ContractError("profile.gates: duplicate gate id")
    if queues != sorted(queues) or len(queues) != len(set(queues)):
        raise ContractError("profile.gates: queues must be unique and ordered")
    closure = profile.get("closure")
    if not isinstance(closure, dict) or closure.get("generatedRequiredGates") is not True:
        raise ContractError("closure.generatedRequiredGates must be true")
    if _string_list(closure.get("requiredGates"), "closure.requiredGates") != gate_ids:
        raise ContractError("closure.requiredGates must exactly preserve profile gate order")

    routes = routing.get("routes")
    if not isinstance(routes, dict) or set(routes) != set(gate_ids):
        raise ContractError("routing.routes must contain exactly the profile gates")
    routed_roles: set[str] = set()
    parsed_routes: dict[str, tuple[str, ...]] = {}
    route_executors: dict[str, str] = {}
    for gate_id in gate_ids:
        route = routes[gate_id]
        if not isinstance(route, dict) or not str(route.get("receipt", "")).strip():
            raise ContractError(f"routing {gate_id}: receipt is required")
        role_list = _string_list(route.get("adapters"), f"routing {gate_id}.adapters")
        roles = set(role_list)
        unknown = roles - set(role_contracts)
        if unknown:
            raise ContractError(f"routing {gate_id}: unknown roles {sorted(unknown)}")
        executor = route.get("executorAdapter")
        if not isinstance(executor, str) or executor not in roles:
            raise ContractError(
                f"routing {gate_id}: executorAdapter must name one routed adapter"
            )
        route_executors[gate_id] = executor
        routed_roles.update(roles)
        parsed_routes[gate_id] = tuple(role_list)
    role_capabilities = {
        str(role): frozenset(_string_list(value, f"adapter-contract.roles.{role}"))
        for role, value in role_contracts.items()
        if isinstance(role, str)
    }
    if set().union(*(role_capabilities[role] for role in routed_roles)) != known_capabilities:
        raise ContractError("routed adapter roles must cover the capability contract exactly")

    expected_fields = ["gate", "status", "evidence", "inputFingerprint", "recordedAt"]
    if _string_list(receipt.get("requiredFields"), "receipt.requiredFields") != expected_fields:
        raise ContractError(f"receipt.requiredFields must be {expected_fields}")
    pending, blocking = receipt.get("pendingStatus"), receipt.get("blockingStatus")
    if not isinstance(pending, str) or not isinstance(blocking, str) or not pending or not blocking or pending == blocking:
        raise ContractError("receipt pending and blocking statuses must be distinct")
    for key, sample in (("fingerprintPattern", "sha256:" + "0" * 64), ("recordedAtPattern", "2026-01-01T00:00:00Z")):
        try:
            pattern = re.compile(str(receipt.get(key, "")))
        except re.error as exc:
            raise ContractError(f"receipt.{key} is invalid: {exc}") from exc
        if pattern.fullmatch(sample) is None:
            raise ContractError(f"receipt.{key} rejects the canonical sample")
    expected_invalidations = {
        "source",
        "test",
        "configuration",
        "generated",
        "dependency",
        "environment",
        "accepted-review-findings",
    }
    if set(_string_list(receipt.get("invalidationInputs"), "receipt.invalidationInputs")) != expected_invalidations:
        raise ContractError("receipt invalidationInputs do not match the selected profile")
    gate_policies = receipt.get("gatePolicies")
    if not isinstance(gate_policies, dict) or set(gate_policies) != set(gate_ids):
        raise ContractError("receipt gatePolicies must contain exactly the profile gates")
    expected_modes = (
        {"matrix/v1": "basis", "architecture/v1": "basis", "red/v1": "snapshot"}
        if api_version == "acdd/task/v1"
        else {
            "intent/v1": "basis",
            "evidence/v1": "basis",
            "architecture/v1": "basis",
            "plan-shape/v1": "basis",
            "roadmap-shape/v1": "basis",
            "milestone-shape/v1": "basis",
            "decomposition/v1": "basis",
        }
    )
    for gate_id in gate_ids:
        policy = gate_policies[gate_id]
        required_policy_fields = {"evidenceMode", "invalidationInputs"}
        allowed_policy_fields = required_policy_fields
        if not isinstance(policy, dict) or not required_policy_fields <= set(policy) or set(policy) - allowed_policy_fields:
            raise ContractError(f"receipt {gate_id}.gatePolicy has invalid fields")
        mode = policy.get("evidenceMode")
        if mode not in {"basis", "snapshot", "live"}:
            raise ContractError(f"receipt {gate_id}.evidenceMode is invalid")
        expected_mode = expected_modes.get(gate_id, "live")
        if mode != expected_mode:
            raise ContractError(f"receipt {gate_id}.evidenceMode must be {expected_mode}")
        policy_inputs = set(_string_list(policy.get("invalidationInputs"), f"receipt {gate_id}.invalidationInputs"))
        if not policy_inputs or not policy_inputs <= expected_invalidations:
            raise ContractError(f"receipt {gate_id}.invalidationInputs must be a non-empty canonical subset")
        if mode == "live" and policy_inputs != expected_invalidations:
            raise ContractError(f"receipt {gate_id}.live invalidationInputs must include every canonical input")
    terminal = receipt.get("terminalStatuses")
    if not isinstance(terminal, dict) or set(terminal) != set(gate_ids):
        raise ContractError("receipt terminalStatuses must contain exactly the profile gates")
    for gate_id in gate_ids:
        statuses = _string_list(terminal[gate_id], f"receipt {gate_id}.terminalStatuses")
        if api_version == "acdd/task/v1":
            expected = ["expected_failure", "inapplicable"] if gate_id == "red/v1" else ["pass"]
        else:
            expected = ["pass", "inapplicable"] if gate_id in {"roadmap-shape/v1", "milestone-shape/v1"} else ["pass"]
        if statuses != expected:
            raise ContractError(f"receipt {gate_id}.terminalStatuses must be {expected}")
        if pending in statuses or blocking in statuses:
            raise ContractError(f"receipt {gate_id}: pending/blocking cannot be terminal")
    return CoreContract(
        profile_path=profile_path,
        profile=profile,
        routing=routing,
        capabilities=capabilities,
        adapter_contract=adapter_contract,
        receipt_contract=receipt,
        receipt_contract_path=linked["receiptContract"],
        gates=tuple(parsed_gates),
        routes=parsed_routes,
        route_executors=route_executors,
        architecture_verification_schema=architecture_schema,
        architecture_verification_schema_path=architecture_schema_path,
        role_capabilities=role_capabilities,
        routed_roles=tuple(sorted(routed_roles)),
    )


def _declared_path(raw: str) -> bool:
    return not any(c.isspace() for c in raw) and not raw.startswith(("http://", "https://")) and ("/" in raw or raw.endswith((".md", ".yaml", ".yml", ".py", ".json", ".txt")))


def _validate_declared_paths(value: object, owner: Path, label: str, *, allowed_root: Path) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_declared_paths(child, owner, f"{label}.{key}", allowed_root=allowed_root)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_declared_paths(child, owner, f"{label}[{index}]", allowed_root=allowed_root)
    elif isinstance(value, str) and _declared_path(value) and not any(marker in value for marker in ("*", "{", "<")):
        _resolve(owner, value, label, allowed_root=allowed_root)


def _validate_external_mappings(value: object, label: str) -> None:
    if not isinstance(value, dict) or not value:
        raise ContractError(f"{label} must be a non-empty mapping")
    for provider, mapping in value.items():
        if not isinstance(provider, str) or not provider.strip():
            raise ContractError(f"{label} provider names must be non-empty strings")
        if not isinstance(mapping, dict) or not mapping:
            raise ContractError(f"{label}.{provider} must be a non-empty mapping")
        canonical_kinds = {"roadmap", "phase", "milestone", "task", "plan"}
        if set(mapping) != canonical_kinds:
            raise ContractError(
                f"{label}.{provider} must map exactly canonical owner kinds {sorted(canonical_kinds)}"
            )
        for canonical_kind, external_kind in mapping.items():
            if not isinstance(canonical_kind, str) or not canonical_kind.strip():
                raise ContractError(f"{label}.{provider} canonical kinds must be non-empty strings")
            if not isinstance(external_kind, str) or not external_kind.strip():
                raise ContractError(f"{label}.{provider}.{canonical_kind} must be a non-empty string")



_ARCHITECTURE_DISCOVERY_CAPABILITIES = {
    "exactText": "source_map",
    "structural": "structural_search",
    "dependency": "impact",
}


def _validate_discovery_bindings(value: object, label: str) -> None:
    if not isinstance(value, dict) or set(value) != set(
        _ARCHITECTURE_DISCOVERY_CAPABILITIES
    ):
        raise ContractError(
            f"{label} must bind exactText, structural, and dependency capabilities"
        )
    for method, capability in _ARCHITECTURE_DISCOVERY_CAPABILITIES.items():
        binding = value.get(method)
        if not isinstance(binding, dict) or set(binding) != {"capability", "tools"}:
            raise ContractError(
                f"{label}.{method} must contain capability and tools only"
            )
        if binding.get("capability") != capability:
            raise ContractError(
                f"{label}.{method}.capability must be {capability!r}"
            )
        _string_list(binding.get("tools"), f"{label}.{method}.tools")


def _validate_launcher_binding(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {
        "kind",
        "target",
        "arguments",
        "promptTransport",
    }:
        raise ContractError(
            f"{label} must contain kind, target, arguments, and promptTransport only"
        )
    kind = value.get("kind")
    if kind not in {"command", "tool"}:
        raise ContractError(f"{label}.kind must be 'command' or 'tool'")
    target = value.get("target")
    if not isinstance(target, str) or not target.strip():
        raise ContractError(f"{label}.target must be a non-empty executable or tool name")
    arguments = value.get("arguments")
    if not isinstance(arguments, list) or not all(
        isinstance(argument, str) and argument.strip() for argument in arguments
    ):
        raise ContractError(f"{label}.arguments must be a string list")
    expected_transport = "final-argument" if kind == "command" else "parameters"
    if value.get("promptTransport") != expected_transport:
        raise ContractError(
            f"{label}.promptTransport must be {expected_transport!r} for {kind!r}"
        )
    if kind == "command" and not arguments:
        raise ContractError(f"{label}.arguments must bind the command invocation")
    if kind == "tool" and arguments:
        raise ContractError(f"{label}.arguments must be empty for a tool launcher")
    return value


def _validate_executor_gate_procedures(
    value: object,
    core: CoreContract,
    role: str,
    owner: Path,
    allowed_root: Path,
    label: str,
) -> None:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be a mapping")
    required_gates = {
        gate.id
        for gate in core.gates
        if core.route_executors[gate.id] == role
        and {"independent_review", "review_execution"} <= gate.capabilities
    }
    missing = required_gates - set(value)
    if missing:
        raise ContractError(f"{label} missing executor-owned gates {sorted(missing)}")
    for gate_id in required_gates:
        procedure = value[gate_id]
        if not isinstance(procedure, dict) or not procedure:
            raise ContractError(f"{label}.{gate_id} must be a non-empty owner procedure")
        operation = procedure.get("operation")
        runtime = procedure.get("runtime")
        launcher = _validate_launcher_binding(
            procedure.get("launcher"),
            f"{label}.{gate_id}.launcher",
        )
        envelope = procedure.get("toolEnvelope")
        if not isinstance(operation, str) or not operation.strip():
            raise ContractError(f"{label}.{gate_id}.operation is required")
        if not isinstance(runtime, str) or not runtime.strip():
            raise ContractError(f"{label}.{gate_id}.runtime is required")
        if not isinstance(envelope, dict):
            raise ContractError(f"{label}.{gate_id}.toolEnvelope is required")
        admit = set(_string_list(envelope.get("admit"), f"{label}.{gate_id}.toolEnvelope.admit"))
        deny = set(_string_list(envelope.get("deny"), f"{label}.{gate_id}.toolEnvelope.deny"))
        if admit & deny:
            raise ContractError(f"{label}.{gate_id}.toolEnvelope overlaps admit and deny")
        if runtime in admit or runtime in deny:
            raise ContractError(
                f"{label}.{gate_id}.runtime is provenance, not a tool-envelope name"
            )
        launcher_kind = launcher["kind"]
        launcher_target = launcher["target"]
        if launcher_kind == "tool" and launcher_target not in admit:
            raise ContractError(
                f"{label}.{gate_id}.launcher tool {launcher_target!r} must be admitted"
            )
        if launcher_kind == "command" and launcher_target in admit | deny:
            raise ContractError(
                f"{label}.{gate_id}.launcher command {launcher_target!r} must not be represented as a child tool"
            )
        if gate_id == "architecture/v1":
            if runtime != "pi" or launcher_kind != "command":
                raise ContractError(
                    "architecture/v1 must use Pi runtime provenance with a concrete command launcher"
                )
            required_tools = {"read", "grep", "find", "ls", "mcp"}
            denied_tools = {"bash", "edit", "write", "pi_review_agents"}
            if not required_tools <= admit or not denied_tools <= deny:
                raise ContractError(
                    "architecture/v1 must admit read/grep/find/ls/mcp and deny bash/edit/write/pi_review_agents"
                )
            if core.profile.get("apiVersion") != "acdd/task/v1":
                continue
            if procedure.get("authoritativeSessions") != 1:
                raise ContractError("architecture/v1 requires one authoritative session")
            if procedure.get("reviewRoot") != "workspace" or procedure.get("commandCwd") != "implementation-repository":
                raise ContractError("architecture/v1 must use workspace review root and implementation repository command CWD")
            _validate_discovery_bindings(
                procedure.get("discoveryMethods"),
                f"{label}.{gate_id}.discoveryMethods",
            )
            model = procedure.get("model")
            if model != {
                "provider": "openai-codex",
                "modelId": "gpt-5.6-sol",
                "reasoning": "low",
            }:
                raise ContractError("architecture/v1 default model must be openai-codex/gpt-5.6-sol:low")
            contract_path = _resolve(
                owner,
                procedure.get("contract"),
                f"{label}.{gate_id}.contract",
                allowed_root=allowed_root,
            )
            if core.architecture_verification_schema is None:
                raise ContractError("task profile lacks architecture verification schema")
            try:
                validate_architecture_verification_contract(
                    load_architecture_verification_yaml(contract_path),
                    core.architecture_verification_schema,
                )
            except ArchitectureVerificationError as exc:
                raise ContractError(str(exc)) from exc
        elif gate_id == "review/v1":
            if (
                runtime != "pi-review-agents"
                or launcher_kind != "tool"
                or launcher_target != "pi_review_agents"
            ):
                raise ContractError(
                    "review/v1 must bind pi-review-agents provenance to the pi_review_agents tool"
                )
            if procedure.get("presentation") != "overview":
                raise ContractError("review/v1 presentation must be overview")


def load_adapter(path: Path, expected_role: str, core: CoreContract, *, allowed_root: Path | None = None) -> dict[str, object]:
    allowed_root = (allowed_root or path.parent).resolve()
    adapter = _mapping(path)
    _expect(adapter.get("apiVersion"), "acdd/adapter/v1", f"{path}:apiVersion")
    _expect(adapter.get("kind"), "adapter", f"{path}:kind")
    _expect(adapter.get("role"), expected_role, f"{path}:role")
    required = set(_string_list(core.adapter_contract.get("required"), "adapter-contract.required"))
    optional = set(_string_list(core.adapter_contract.get("optional"), "adapter-contract.optional"))
    missing = required - set(adapter)
    if missing:
        raise ContractError(f"{path}: missing required fields {sorted(missing)}")
    unknown_fields = set(adapter) - required - optional - {"apiVersion", "kind"}
    if unknown_fields:
        raise ContractError(f"{path}: undeclared fields {sorted(unknown_fields)}")
    if re.fullmatch(r"[a-z0-9][a-z0-9._/-]*/v\d+", str(adapter.get("id", ""))) is None:
        raise ContractError(f"{path}: invalid adapter id {adapter.get('id')!r}")
    if not isinstance(adapter.get("authority"), dict) or not adapter["authority"]:
        raise ContractError(f"{path}: authority must be a non-empty mapping")
    _string_list(adapter.get("constraints"), f"{path}:constraints")
    _adapter_write_policy(adapter.get("writePolicy"), core, f"{path}:writePolicy")
    provides = set(_string_list(adapter.get("provides"), f"{path}:provides"))
    expected = set(core.role_capabilities.get(expected_role, frozenset()))
    if provides != expected:
        raise ContractError(f"{path}: role {expected_role} must provide exactly {sorted(expected)}, found {sorted(provides)}")
    procedure = adapter.get("procedure")
    if isinstance(procedure, str):
        if not procedure.strip():
            raise ContractError(f"{path}:procedure must not be empty")
        if _declared_path(procedure):
            _resolve(path, procedure, f"{path}:procedure", allowed_root=allowed_root)
    elif isinstance(procedure, list):
        _string_list(procedure, f"{path}:procedure")
    else:
        raise ContractError(f"{path}:procedure must be a path or instruction list")
    for key in ("resources", "scripts", "skillExtensions", "gateProcedures"):
        if key in adapter:
            _validate_declared_paths(adapter[key], path, f"{path}:{key}", allowed_root=allowed_root)
    if "externalMappings" in adapter:
        _validate_external_mappings(adapter["externalMappings"], f"{path}:externalMappings")
    procedures = adapter.get("gateProcedures", {})
    if not isinstance(procedures, dict) or set(procedures) - set(core.gate_ids):
        raise ContractError(f"{path}: gateProcedures contains unknown gates")
    _validate_executor_gate_procedures(
        procedures,
        core,
        expected_role,
        path,
        allowed_root,
        f"{path}:gateProcedures",
    )
    return adapter


def resolve_gate_execution(
    core: CoreContract,
    loaded_adapters: dict[str, dict[str, object]],
    queued_gate: str,
) -> tuple[str, dict[str, object]]:
    if queued_gate not in core.route_executors:
        raise ContractError(f"unknown queued gate {queued_gate!r}")
    executor = core.route_executors[queued_gate]
    adapter = loaded_adapters.get(executor)
    if adapter is None:
        raise ContractError(f"queued gate {queued_gate}: missing executor adapter {executor}")
    procedures = adapter.get("gateProcedures", {})
    if not isinstance(procedures, dict):
        raise ContractError(f"queued gate {queued_gate}: executor procedures are invalid")
    raw = procedures.get(queued_gate)
    if raw is None:
        return executor, {"procedure": adapter.get("procedure")}
    if not isinstance(raw, dict) or not raw:
        raise ContractError(f"queued gate {queued_gate}: executor procedure is invalid")
    return executor, raw


def gate_tool_envelope(
    core: CoreContract,
    loaded_adapters: dict[str, dict[str, object]],
    queued_gate: str,
) -> tuple[frozenset[str], frozenset[str]]:
    _, procedure = resolve_gate_execution(core, loaded_adapters, queued_gate)
    envelope = procedure.get("toolEnvelope")
    if not isinstance(envelope, dict):
        return frozenset(), frozenset()
    return (
        frozenset(_string_list(envelope.get("admit"), f"{queued_gate}.toolEnvelope.admit")),
        frozenset(_string_list(envelope.get("deny"), f"{queued_gate}.toolEnvelope.deny")),
    )


def _skill_names(settings_path: Path, workspace_root: Path) -> dict[str, list[Path]]:
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load settings {settings_path}: {exc}") from exc
    roots = settings.get("skills")
    if not isinstance(roots, list):
        raise ContractError(f"{settings_path}: skills must be a list")
    result: dict[str, list[Path]] = {}
    for raw in roots:
        root = _resolve(settings_path, raw, f"{settings_path}:skills", allowed_root=workspace_root)
        for skill in root.rglob("SKILL.md"):
            match = re.search(r"^name:\s*[\"']?([^\"'\n]+)", skill.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
            if match:
                result.setdefault(match.group(1).strip(), []).append(skill.resolve())
    return result


def validate_runtime(core: CoreContract, workspace_root: Path, adapters: dict[str, Path], settings_path: Path | None = None) -> CoreContract:
    root = workspace_root.resolve()
    if not root.is_dir():
        raise ContractError(f"workspace root does not exist: {root}")
    expected_base = set(core.routed_roles)
    optional_roles = set(_string_list(core.adapter_contract.get("optionalRoles"), "adapter-contract.optionalRoles"))
    if not optional_roles <= set(core.role_capabilities):
        raise ContractError("adapter-contract.optionalRoles must name declared roles")
    if not expected_base <= set(adapters) or set(adapters) - expected_base - optional_roles:
        missing, unknown = expected_base - set(adapters), set(adapters) - expected_base - optional_roles
        raise ContractError(f"adapter roles mismatch: missing={sorted(missing)} unknown={sorted(unknown)}")
    paths = {role: _workspace_path(path, root, f"adapter {role}") for role, path in adapters.items()}
    if len(paths) != len(set(paths.values())):
        raise ContractError("duplicate adapter paths are not allowed")
    loaded = {role: load_adapter(path, role, core, allowed_root=root) for role, path in paths.items()}
    for gate in core.gates:
        provided: set[str] = set()
        for role in core.routes[gate.id]:
            adapter_provides = loaded[role].get("provides")
            provided.update(_string_list(adapter_provides, f"{role}.provides"))
        missing = gate.capabilities - provided
        if missing:
            raise ContractError(f"{gate.id}: selected adapters miss {sorted(missing)}")
    if settings_path is not None:
        settings = _workspace_path(settings_path, root, "settings")
        skills = _skill_names(settings, root)
        for gate in core.gates:
            matches = skills.get(gate.guidance_skill, [])
            if len(matches) != 1:
                raise ContractError(
                    f"{gate.id}: guidance skill {gate.guidance_skill!r} resolves {len(matches)} times: {matches}"
                )
    return core


def _gate_policies(core: CoreContract) -> tuple[GatePolicy, ...]:
    raw_policies = core.receipt_contract.get("gatePolicies")
    raw_terminal = core.receipt_contract.get("terminalStatuses")
    if not isinstance(raw_policies, dict) or not isinstance(raw_terminal, dict):
        raise ContractError("receipt gate policies or terminal statuses are invalid")
    policies: list[GatePolicy] = []
    for gate in core.gate_ids:
        raw_policy = raw_policies.get(gate)
        if not isinstance(raw_policy, dict):
            raise ContractError(f"receipt {gate}: missing gate policy")
        policies.append(
            GatePolicy(
                gate=gate,
                terminal_statuses=frozenset(
                    _string_list(raw_terminal.get(gate), f"receipt {gate}.terminalStatuses")
                ),
                invalidation_inputs=frozenset(
                    _string_list(
                        raw_policy.get("invalidationInputs"),
                        f"receipt {gate}.invalidationInputs",
                    )
                ),
            )
        )
    return tuple(policies)


def _impact_axes(
    core: CoreContract, adapters: dict[str, Path], workspace_root: Path
) -> frozenset[str]:
    axes: set[str] = set()
    for role in core.routed_roles:
        path = _workspace_path(adapters[role], workspace_root, f"adapter {role}")
        adapter = load_adapter(path, role, core, allowed_root=workspace_root)
        authority = adapter.get("authority")
        if not isinstance(authority, dict):
            continue
        impact = authority.get("impact")
        if not isinstance(impact, dict):
            continue
        domains = impact.get("domains")
        if domains is not None:
            axes.update(_string_list(domains, f"{path}:authority.impact.domains"))
    if not axes:
        raise ContractError("selected adapters declare no impact axes")
    return frozenset(axes)


def _adapter_args(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ContractError(f"--adapter expects ROLE=PATH, found {value!r}")
        role, raw = value.split("=", 1)
        if not role or not raw:
            raise ContractError(f"--adapter expects ROLE=PATH, found {value!r}")
        if role in result:
            raise ContractError(f"duplicate adapter role {role!r}")
        result[role] = Path(raw)
    return result


def _document_argument(raw: Path, workspace_root: Path) -> Path:
    if raw.is_absolute():
        return raw
    workspace_candidate = workspace_root.resolve() / raw
    if workspace_candidate.is_file():
        return workspace_candidate
    return raw


def _architecture_verification_contract(
    core: CoreContract,
    adapters: dict[str, Path],
    workspace_root: Path,
) -> dict[str, object] | None:
    if core.architecture_verification_schema is None:
        return None
    executor = core.route_executors.get("architecture/v1")
    if executor is None or executor not in adapters:
        raise ContractError("architecture/v1 executor adapter is unavailable")
    adapter_path = _workspace_path(
        adapters[executor], workspace_root, f"adapter {executor}"
    )
    adapter = load_adapter(adapter_path, executor, core, allowed_root=workspace_root)
    procedures = adapter.get("gateProcedures")
    if not isinstance(procedures, dict):
        raise ContractError("architecture/v1 executor has no gate procedures")
    procedure = procedures.get("architecture/v1")
    if not isinstance(procedure, dict):
        raise ContractError("architecture/v1 executor procedure is missing")
    contract_path = _resolve(
        adapter_path,
        procedure.get("contract"),
        "architecture/v1.contract",
        allowed_root=workspace_root,
    )
    try:
        contract = load_architecture_verification_yaml(contract_path)
        validate_architecture_verification_contract(
            contract, core.architecture_verification_schema
        )
    except ArchitectureVerificationError as exc:
        raise ContractError(str(exc)) from exc
    return contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--document", type=Path, required=True)
    parser.add_argument("--adapter", action="append", default=[], metavar="ROLE=PATH")
    parser.add_argument("--settings", type=Path)
    args = parser.parse_args(argv)
    try:
        core = load_core(args.profile)
        adapters = _adapter_args(args.adapter)
        validate_runtime(core, args.workspace_root, adapters, args.settings)
        validate_document(
            document=_workspace_path(
                _document_argument(args.document, args.workspace_root),
                args.workspace_root,
                "document",
            ),
            profile=core.profile_path,
            receipt_contract=core.receipt_contract_path,
            adapters=tuple(
                _workspace_path(adapters[role], args.workspace_root, f"adapter {role}")
                for role in sorted(adapters)
            ),
            workspace_root=args.workspace_root.resolve(),
            policies=_gate_policies(core),
            plan=core.profile.get("apiVersion") == "acdd/plan/v1",
            impact_axes=_impact_axes(core, adapters, args.workspace_root.resolve()),
            architecture_verification_schema=core.architecture_verification_schema,
            architecture_verification_contract=_architecture_verification_contract(
                core, adapters, args.workspace_root.resolve()
            ),
        )
    except (ContractError, DocumentError) as exc:
        print(f"ACDD INVALID: {exc}", file=sys.stderr)
        return 1
    print(
        f"ACDD VALID: profile={core.profile['id']} gates={len(core.gate_ids)} "
        f"adapters={','.join(sorted(adapters))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
