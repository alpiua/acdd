#!/usr/bin/env python3
"""Validate the portable ACDD profile and an optional workspace binding.

Examples:
  python3 scripts/validate_acdd.py
  python3 scripts/validate_acdd.py --binding ../../.agents/acdd/binding.yaml \
      --settings ../../.pi/settings.json

The validator is read-only and fails closed on unknown gates, capabilities,
adapter roles, duplicate skills, unresolved owner paths, or uncovered routes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = PLUGIN_ROOT / "profiles" / "acdd" / "v1.yaml"


@dataclass(frozen=True)
class CoreContract:
    profile_path: Path
    profile: dict[str, Any]
    routing: dict[str, Any]
    capabilities: dict[str, Any]
    adapter_contract: dict[str, Any]
    receipt_contract: dict[str, Any]
    gate_ids: tuple[str, ...]


class ContractError(ValueError):
    """Raised when a declared ACDD contract cannot be trusted."""


def _mapping(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{path}: expected a YAML mapping")
    return value


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


def _expect(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise ContractError(f"{label}: expected {expected!r}, found {value!r}")


def _string_list(value: object, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise ContractError(f"{label}: expected a non-empty-string list")
    if len(value) != len(set(value)):
        raise ContractError(f"{label}: duplicate values are not allowed")
    return list(value)


def load_core(profile_path: Path = DEFAULT_PROFILE) -> CoreContract:
    profile_path = profile_path.resolve()
    if len(profile_path.parents) < 3:
        raise ContractError(f"{profile_path}: cannot establish canonical plugin authority root")
    authority_root = profile_path.parents[2]
    profile = _mapping(profile_path)
    _expect(profile.get("apiVersion"), "acdd/v1", f"{profile_path}:apiVersion")
    _expect(profile.get("kind"), "delivery-profile", f"{profile_path}:kind")

    routing_path = _resolve(
        profile_path, profile.get("routing"), "profile.routing", allowed_root=authority_root
    )
    capabilities_path = _resolve(
        profile_path, profile.get("capabilityContract"), "profile.capabilityContract", allowed_root=authority_root
    )
    adapter_contract_path = _resolve(
        profile_path, profile.get("adapterContract"), "profile.adapterContract", allowed_root=authority_root
    )
    receipt_contract_path = _resolve(
        profile_path, profile.get("receiptContract"), "profile.receiptContract", allowed_root=authority_root
    )
    routing = _mapping(routing_path)
    capabilities = _mapping(capabilities_path)
    adapter_contract = _mapping(adapter_contract_path)
    receipt_contract = _mapping(receipt_contract_path)

    _expect(profile.get("id"), "acdd/v1", f"{profile_path}:id")
    _expect(routing.get("apiVersion"), "acdd/v1", f"{routing_path}:apiVersion")
    _expect(routing.get("kind"), "gate-routing", f"{routing_path}:kind")
    _expect(capabilities.get("apiVersion"), "acdd/v1", f"{capabilities_path}:apiVersion")
    _expect(capabilities.get("kind"), "capability-contract", f"{capabilities_path}:kind")
    _expect(adapter_contract.get("apiVersion"), "acdd/adapter/v1", f"{adapter_contract_path}:apiVersion")
    _expect(adapter_contract.get("kind"), "adapter-contract", f"{adapter_contract_path}:kind")
    _expect(receipt_contract.get("apiVersion"), "acdd/receipt/v1", f"{receipt_contract_path}:apiVersion")
    _expect(receipt_contract.get("kind"), "receipt-contract", f"{receipt_contract_path}:kind")
    if _resolve(
        routing_path, routing.get("profile"), "routing.profile", allowed_root=authority_root
    ) != profile_path:
        raise ContractError("routing.profile must point back to the selected profile")

    capability_entries = capabilities.get("capabilities")
    if not isinstance(capability_entries, dict) or not capability_entries:
        raise ContractError("capability contract declares no capabilities")
    for capability, entry in capability_entries.items():
        if not isinstance(capability, str) or not capability.strip() or not isinstance(entry, dict):
            raise ContractError("capability contract entries must be named mappings")
        if not isinstance(entry.get("purpose"), str) or not entry["purpose"].strip():
            raise ContractError(f"capability {capability}: purpose is required")
        if entry.get("providedBy") not in {"task-adapter", "implementation-adapter", "review-adapter"}:
            raise ContractError(f"capability {capability}: unknown providedBy {entry.get('providedBy')!r}")

    required_adapter_fields = _string_list(adapter_contract.get("required"), "adapter-contract.required")
    optional_adapter_fields = _string_list(adapter_contract.get("optional"), "adapter-contract.optional")
    if set(required_adapter_fields) & set(optional_adapter_fields):
        raise ContractError("adapter contract required and optional fields overlap")
    role_contracts = adapter_contract.get("roles")
    if not isinstance(role_contracts, dict) or set(role_contracts) != {"task", "implementation", "review"}:
        raise ContractError("adapter contract must define task, implementation, and review roles")
    role_capabilities = {
        role: set(_string_list(values, f"adapter-contract.roles.{role}"))
        for role, values in role_contracts.items()
    }
    if set().union(*role_capabilities.values()) != set(capability_entries):
        raise ContractError("adapter role capabilities must cover the capability contract exactly")

    expected_receipt_fields = ["gate", "status", "evidence", "inputFingerprint", "recordedAt"]
    if _string_list(receipt_contract.get("requiredFields"), "receipt.requiredFields") != expected_receipt_fields:
        raise ContractError(f"receipt.requiredFields must be {expected_receipt_fields}")
    pending_status = receipt_contract.get("pendingStatus")
    blocking_status = receipt_contract.get("blockingStatus")
    if not isinstance(pending_status, str) or not pending_status.strip():
        raise ContractError("receipt.pendingStatus is required")
    if not isinstance(blocking_status, str) or not blocking_status.strip() or blocking_status == pending_status:
        raise ContractError("receipt.blockingStatus must be distinct from pendingStatus")
    for key, sample in (
        ("fingerprintPattern", "sha256:" + "0" * 64),
        ("recordedAtPattern", "2026-01-01T00:00:00Z"),
    ):
        raw_pattern = receipt_contract.get(key)
        if not isinstance(raw_pattern, str) or not raw_pattern:
            raise ContractError(f"receipt.{key} is required")
        try:
            pattern = re.compile(raw_pattern)
        except re.error as exc:
            raise ContractError(f"receipt.{key} is invalid: {exc}") from exc
        if pattern.fullmatch(sample) is None:
            raise ContractError(f"receipt.{key} rejects the canonical sample")
    required_invalidations = {
        "task", "source", "tests", "configuration", "generated-inputs",
        "dependencies", "environment", "accepted-review-findings",
    }
    invalidations = set(_string_list(receipt_contract.get("invalidationInputs"), "receipt.invalidationInputs"))
    if invalidations != required_invalidations:
        raise ContractError("receipt invalidationInputs must cover every canonical invalidation input")

    gates = profile.get("gates")
    if not isinstance(gates, list) or not gates:
        raise ContractError("profile.gates: expected a non-empty list")
    gate_ids: list[str] = []
    queues: list[int] = []
    known_capabilities = set(capability_entries)
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            raise ContractError(f"profile.gates[{index}]: expected a mapping")
        gate_id = gate.get("id")
        queue = gate.get("queue")
        if not isinstance(gate_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]*/v\d+", gate_id):
            raise ContractError(f"profile.gates[{index}].id: invalid {gate_id!r}")
        if not isinstance(queue, int):
            raise ContractError(f"{gate_id}.queue: expected integer")
        gate_ids.append(gate_id)
        queues.append(queue)
        unknown = set(_string_list(gate.get("capabilities"), f"{gate_id}.capabilities")) - known_capabilities
        if unknown:
            raise ContractError(f"{gate_id}: unknown capabilities {sorted(unknown)}")
        guidance = gate.get("guidance")
        if not isinstance(guidance, dict) or not guidance.get("skill") or not guidance.get("prompt"):
            raise ContractError(f"{gate_id}.guidance: skill and prompt are required")
    if len(gate_ids) != len(set(gate_ids)):
        raise ContractError("profile.gates: duplicate gate id")
    if queues != sorted(queues) or len(queues) != len(set(queues)):
        raise ContractError(f"profile.gates: queues must be unique and ordered, found {queues}")

    closure = profile.get("closure")
    if not isinstance(closure, dict) or closure.get("generatedRequiredGates") is not True:
        raise ContractError("closure.generatedRequiredGates must be true")
    required_gates = _string_list(closure.get("requiredGates"), "closure.requiredGates")
    if required_gates != gate_ids:
        raise ContractError("closure.requiredGates must exactly preserve profile gate order")
    routes = routing.get("routes")
    if not isinstance(routes, dict) or set(routes) != set(gate_ids):
        raise ContractError("routing.routes must contain exactly the profile gates")
    terminal_statuses = receipt_contract.get("terminalStatuses")
    if not isinstance(terminal_statuses, dict) or set(terminal_statuses) != set(gate_ids):
        raise ContractError("receipt terminalStatuses must contain exactly the profile gates")
    known_roles = set(role_contracts)
    for gate_id in gate_ids:
        route = routes[gate_id]
        if not isinstance(route, dict):
            raise ContractError(f"routing {gate_id}: expected a mapping")
        route_roles = set(_string_list(route.get("adapters"), f"routing {gate_id}.adapters"))
        if route_roles - known_roles:
            raise ContractError(f"routing {gate_id}: unknown roles {sorted(route_roles - known_roles)}")
        if not isinstance(route.get("receipt"), str) or not route["receipt"].strip():
            raise ContractError(f"routing {gate_id}.receipt: required")
        statuses = _string_list(terminal_statuses[gate_id], f"receipt {gate_id}.terminalStatuses")
        expected_statuses = ["expected_failure", "inapplicable"] if gate_id == "red/v1" else ["pass"]
        if statuses != expected_statuses:
            raise ContractError(f"receipt {gate_id}.terminalStatuses must be {expected_statuses}")
        if pending_status in statuses or blocking_status in statuses:
            raise ContractError(f"receipt {gate_id}: pending/blocking status cannot be terminal")

    return CoreContract(
        profile_path=profile_path,
        profile=profile,
        routing=routing,
        capabilities=capabilities,
        adapter_contract=adapter_contract,
        receipt_contract=receipt_contract,
        gate_ids=tuple(gate_ids),
    )


def _declared_path(raw: str) -> bool:
    return (
        not any(character.isspace() for character in raw)
        and not raw.startswith(("http://", "https://"))
        and ("/" in raw or raw.endswith((".md", ".yaml", ".yml", ".py", ".json", ".txt")))
    )


def _validate_declared_paths(
    value: object, owner: Path, label: str, *, allowed_root: Path
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_declared_paths(child, owner, f"{label}.{key}", allowed_root=allowed_root)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_declared_paths(child, owner, f"{label}[{index}]", allowed_root=allowed_root)
    elif isinstance(value, str) and _declared_path(value):
        if any(marker in value for marker in ("*", "{", "<")):
            return
        _resolve(owner, value, label, allowed_root=allowed_root)


def load_adapter(
    path: Path, expected_role: str, core: CoreContract, *, allowed_root: Path | None = None
) -> dict[str, Any]:
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
    adapter_id = adapter.get("id")
    if not isinstance(adapter_id, str) or re.fullmatch(r"[a-z0-9][a-z0-9._/-]*/v\d+", adapter_id) is None:
        raise ContractError(f"{path}: invalid adapter id {adapter_id!r}")
    if not isinstance(adapter.get("authority"), dict) or not adapter["authority"]:
        raise ContractError(f"{path}: authority must be a non-empty mapping")
    _string_list(adapter.get("constraints"), f"{path}:constraints")
    provides = set(_string_list(adapter.get("provides"), f"{path}:provides"))
    known_capabilities = set(core.capabilities["capabilities"])
    unknown = provides - known_capabilities
    if unknown:
        raise ContractError(f"{path}: unknown capabilities {sorted(unknown)}")
    role_contract = set(core.adapter_contract.get("roles", {}).get(expected_role, []))
    if provides != role_contract:
        raise ContractError(
            f"{path}: role {expected_role} must provide exactly {sorted(role_contract)}, found {sorted(provides)}"
        )
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
    gate_procedures = adapter.get("gateProcedures", {})
    if not isinstance(gate_procedures, dict):
        raise ContractError(f"{path}: gateProcedures must be a mapping")
    unknown_gates = set(gate_procedures) - set(core.gate_ids)
    if unknown_gates:
        raise ContractError(f"{path}: gateProcedures has unknown gates {sorted(unknown_gates)}")
    return adapter


def _skill_names(settings_path: Path) -> dict[str, list[Path]]:
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load settings {settings_path}: {exc}") from exc
    roots = settings.get("skills")
    if not isinstance(roots, list):
        raise ContractError(f"{settings_path}: skills must be a list")
    result: dict[str, list[Path]] = {}
    for raw in roots:
        root = _resolve(
            settings_path,
            raw,
            f"{settings_path}:skills",
            allowed_root=settings_path.resolve().parent.parent,
        )
        for skill_path in root.rglob("SKILL.md"):
            text = skill_path.read_text(encoding="utf-8", errors="replace")
            match = re.search(r"^name:\s*[\"']?([^\"'\n]+)", text, re.MULTILINE)
            if match:
                result.setdefault(match.group(1).strip(), []).append(skill_path.resolve())
    return result


def validate_binding(
    binding_path: Path,
    core: CoreContract | None = None,
    settings_path: Path | None = None,
) -> CoreContract:
    binding_path = binding_path.resolve()
    if binding_path.parent.name != "acdd" or binding_path.parent.parent.name != ".agents":
        raise ContractError("binding must live under the workspace .agents/acdd authority")
    workspace_root = binding_path.parents[2]
    binding = _mapping(binding_path)
    _expect(binding.get("apiVersion"), "acdd/binding/v1", f"{binding_path}:apiVersion")
    _expect(binding.get("kind"), "binding", f"{binding_path}:kind")
    if set(binding) != {"apiVersion", "kind", "profile", "adapters", "rules"}:
        raise ContractError(f"{binding_path}: binding fields do not match acdd/binding/v1")
    _string_list(binding.get("rules"), "binding.rules")
    selected_profile = _resolve(
        binding_path, binding.get("profile"), "binding.profile", allowed_root=workspace_root
    )
    loaded = load_core(selected_profile)
    if core is not None and loaded.profile_path != core.profile_path:
        raise ContractError("binding selects a different profile than the requested core")
    core = loaded

    adapters = binding.get("adapters")
    if not isinstance(adapters, dict) or set(adapters) != {"task", "implementation", "review"}:
        raise ContractError("binding.adapters must contain task, implementation, and review")
    adapter_paths = {
        "task": _resolve(
            binding_path, adapters.get("task"), "binding.adapters.task", allowed_root=workspace_root
        ),
        "implementation": _resolve(
            binding_path,
            adapters.get("implementation"),
            "binding.adapters.implementation",
            allowed_root=workspace_root,
        ),
    }
    loaded_adapters = {
        role: load_adapter(path, role, core, allowed_root=workspace_root)
        for role, path in adapter_paths.items()
    }
    review = adapters.get("review")
    if not isinstance(review, dict) or set(review) != {"default", "hosts"}:
        raise ContractError("binding.adapters.review must contain default and hosts")
    review_candidates: dict[str, Path] = {
        "default": _resolve(
            binding_path,
            review.get("default"),
            "binding.adapters.review.default",
            allowed_root=workspace_root,
        )
    }
    hosts = review.get("hosts", {})
    if not isinstance(hosts, dict):
        raise ContractError("binding.adapters.review.hosts: expected a mapping")
    for host, raw in hosts.items():
        review_candidates[str(host)] = _resolve(
            binding_path,
            raw,
            f"binding.adapters.review.hosts.{host}",
            allowed_root=workspace_root,
        )
    loaded_reviews = {
        name: load_adapter(path, "review", core, allowed_root=workspace_root)
        for name, path in review_candidates.items()
    }

    for gate in core.profile["gates"]:
        gate_id = gate["id"]
        route_roles = core.routing["routes"][gate_id]["adapters"]
        required = set(gate["capabilities"])
        base_provided: set[str] = set()
        for role in route_roles:
            if role == "review":
                continue
            if role not in loaded_adapters:
                raise ContractError(f"{gate_id}: route names unavailable role {role!r}")
            base_provided.update(loaded_adapters[role]["provides"])
        if "review" in route_roles:
            for name, adapter in loaded_reviews.items():
                missing = required - base_provided - set(adapter["provides"])
                if missing:
                    raise ContractError(
                        f"{gate_id}: review candidate {name!r} misses {sorted(missing)}"
                    )
        else:
            missing = required - base_provided
            if missing:
                raise ContractError(f"{gate_id}: selected adapters miss {sorted(missing)}")

    if settings_path is not None:
        skills = _skill_names(settings_path.resolve())
        for gate in core.profile["gates"]:
            name = gate["guidance"]["skill"]
            matches = skills.get(name, [])
            if len(matches) != 1:
                raise ContractError(
                    f"{gate['id']}: guidance skill {name!r} resolves {len(matches)} times: {matches}"
                )
    return core


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--settings", type=Path)
    args = parser.parse_args(argv)
    try:
        core = load_core(args.profile)
        if args.binding:
            core = validate_binding(args.binding, core, args.settings)
        elif args.settings:
            raise ContractError("--settings requires --binding")
    except ContractError as exc:
        print(f"ACDD INVALID: {exc}", file=sys.stderr)
        return 1
    print(
        "ACDD VALID: "
        f"profile={core.profile.get('id')} gates={len(core.gate_ids)} "
        f"capabilities={len(core.capabilities.get('capabilities', {}))} "
        f"binding={'yes' if args.binding else 'no'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
