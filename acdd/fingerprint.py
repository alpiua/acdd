from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ._doc import extract_sections, resolve_under
from .adapter import Adapter
from .model import Gate, check_owner


@dataclass(frozen=True)
class Fingerprint:
    sha256: str
    scope: tuple[str, ...]


def _feed(hasher, tag: str, value: str | bytes) -> None:
    for part in (tag.encode(), value.encode() if isinstance(value, str) else value):
        hasher.update(len(part).to_bytes(8, "big"))
        hasher.update(part)


def _hash_path(hasher, root: Path, relative: str, kind: str) -> None:
    path = resolve_under(root, relative, label="input")
    identity = json.dumps([kind, relative], separators=(",", ":"))
    if not path.exists():
        _feed(hasher, "missing", identity)
        return
    if path.is_symlink():
        raise ValueError(f"symlink inputs are not supported: {relative!r}")
    if path.is_file():
        _feed(hasher, "file", identity)
        _feed(hasher, "contents", path.read_bytes())
        return
    if not path.is_dir():
        raise ValueError(f"unsupported input path: {relative!r}")
    _feed(hasher, "directory", identity)
    for child in sorted(path.rglob("*")):
        if child.is_symlink():
            raise ValueError(f"symlink inputs are not supported: {child.relative_to(root)!s}")
        if not child.is_dir():
            _hash_path(hasher, root, child.relative_to(root).as_posix(), kind)


def fingerprint_gate(
    workspace_root: Path,
    inputs: list[dict],
    *,
    types: list[str],
    files: list[str] | None = None,
    contract: dict | None = None,
) -> Fingerprint:
    root = workspace_root.resolve()
    for entry in inputs:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("type"), str)
            or not isinstance(entry.get("path"), str)
            or not entry["path"]
        ):
            raise ValueError(f"invalid input entry: {entry!r}")
    selected = sorted(
        (entry["type"], entry["path"])
        for entry in inputs
        if entry.get("type") in types and (files is None or entry.get("path") in files)
    )
    hasher = hashlib.sha256()
    _feed(hasher, "format", "acdd/fingerprint/1")
    if contract is not None:
        _feed(hasher, "contract", json.dumps(contract, sort_keys=True, separators=(",", ":")))
    for kind, relative in selected:
        _hash_path(hasher, root, relative, kind)
    return Fingerprint(
        sha256=f"sha256:{hasher.hexdigest()}", scope=tuple(path for _, path in selected)
    )


def _adapters_by_role(
    adapters: Adapter | list[Adapter] | dict[str, Adapter] | None,
) -> dict[str, Adapter]:
    if adapters is None:
        return {}
    if isinstance(adapters, Adapter):
        return {adapters.role: adapters}
    if isinstance(adapters, dict):
        return adapters
    indexed: dict[str, Adapter] = {}
    for adapter in adapters:
        if adapter.role in indexed:
            raise ValueError(f"duplicate adapter role {adapter.role!r}")
        indexed[adapter.role] = adapter
    return indexed


def _binding_contract(
    adapters_by_role: dict[str, Adapter], gate: Gate, *, document_path: Path | None = None
) -> dict:
    bindings: dict[str, dict] = {}
    for check in gate.checks:
        role = check_owner(gate, check)
        adapter = adapters_by_role.get(role)
        if (
            adapter is None
            or gate.id not in adapter.gates
            or check.id not in adapter.gates[gate.id].checks
        ):
            raise ValueError(
                f"missing adapter binding for {gate.id}.{check.id} (role {role!r})"
            )
        binding = adapter.gates[gate.id].checks[check.id]
        bindings[check.id] = {
            **asdict(binding),
            "promptDigest": adapter.prompt_digest(binding),
            "owner": role,
            "adapterId": adapter.id,
        }
    owner_adapter = adapters_by_role.get(gate.owner)
    contract_sections: tuple[str, ...] = ()
    section_digest = None
    if owner_adapter and gate.id in owner_adapter.gates:
        contract_sections = owner_adapter.gates[gate.id].contract_sections
        if contract_sections:
            if document_path is None:
                raise ValueError(f"{gate.id} declares contractSections without a document path")
            sections = extract_sections(document_path, contract_sections)
            hasher = hashlib.sha256()
            for name in contract_sections:
                _feed(hasher, "section", name)
                _feed(hasher, "body", sections[name])
            section_digest = f"sha256:{hasher.hexdigest()}"
    adapters_part = {
        role: {
            "id": adapter.id,
            "role": adapter.role,
            "artifactDir": adapter.artifact_dir,
        }
        for role, adapter in sorted(
            (
                (check_owner(gate, check), adapters_by_role[check_owner(gate, check)])
                for check in gate.checks
            ),
            key=lambda item: item[0],
        )
    }
    return {
        "gate": asdict(gate),
        "checks": bindings,
        "contractSections": list(contract_sections),
        "contractSectionsDigest": section_digest,
        "adapters": adapters_part,
    }


def _digest(format_id: str, value: object) -> str:
    hasher = hashlib.sha256()
    _feed(hasher, "format", format_id)
    _feed(hasher, "value", json.dumps(value, sort_keys=True, separators=(",", ":")))
    return f"sha256:{hasher.hexdigest()}"


def _subtask_data(task) -> dict:
    return {
        "id": task.id,
        "writes": list(task.writes),
        "reads": list(task.reads),
        "acceptance": task.acceptance,
        "dependsOn": list(task.depends_on),
        "supersedes": task.supersedes,
    }


def subtask_fingerprint(task) -> str:
    return _digest("acdd/subtask-contract/1", _subtask_data(task))


def subtask_contract_part(task, evidence_id: str, contract_fingerprint: str) -> dict:
    part = {
        "type": "subtask_contract",
        "id": evidence_id,
        "subtask": task.id,
        "supersedes": task.supersedes,
        "sourceFingerprint": subtask_fingerprint(task),
        "contractFingerprint": contract_fingerprint,
    }
    return {**part, "partSha256": subtask_contract_hash(part)}


def subtask_contract_hash(part: dict) -> str:
    return _digest(
        "acdd/subtask-contract-part/1",
        {key: value for key, value in part.items() if key != "partSha256"},
    )


def fingerprint_for_gate(
    doc,
    gate: Gate,
    workspace_root: Path,
    adapters: Adapter | list[Adapter] | dict[str, Adapter] | None = None,
) -> str:
    adapters_by_role = _adapters_by_role(adapters)
    relevant = sorted(
        (entry["type"], entry["path"])
        for entry in doc.inputs
        if entry.get("type") in gate.invalidates_on
    )
    return fingerprint_gate(
        workspace_root,
        doc.inputs,
        types=list(gate.invalidates_on),
        contract={
            "gate": _binding_contract(adapters_by_role, gate, document_path=doc.path),
            "inputs": relevant,
        },
    ).sha256
