from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ._doc import resolve_under

@dataclass(frozen=True)
class Fingerprint:
    sha256: str
    scope: tuple[str, ...]

def _hash_path(hasher, root: Path, relative: str, kind: str) -> None:
    path = resolve_under(root, relative, label="input")
    if not path.exists():
        hasher.update(f"MISSING:{kind}:{relative}".encode())
        return
    if path.is_symlink():
        raise ValueError(f"symlink inputs are not supported: {relative!r}")
    if path.is_file():
        hasher.update(f"FILE:{kind}:{relative}".encode())
        hasher.update(path.read_bytes())
        return
    if not path.is_dir():
        raise ValueError(f"unsupported input path: {relative!r}")
    hasher.update(f"DIR:{kind}:{relative}".encode())
    for child in sorted(path.rglob("*")):
        if child.is_symlink():
            raise ValueError(f"symlink inputs are not supported: {child.relative_to(root)!s}")
        if child.is_dir():
            continue
        rel = child.relative_to(root).as_posix()
        hasher.update(f"FILE:{kind}:{rel}".encode())
        hasher.update(child.read_bytes())

def fingerprint_gate(workspace_root: Path, inputs: list[dict], *, types: list[str],
                     files: list[str] | None = None, contract: dict | None = None) -> Fingerprint:
    root = workspace_root.resolve()
    for entry in inputs:
        if (not isinstance(entry, dict) or not isinstance(entry.get("type"), str)
                or not isinstance(entry.get("path"), str) or not entry["path"]):
            raise ValueError(f"invalid input entry: {entry!r}")
    selected = sorted((entry["type"], entry["path"]) for entry in inputs
                      if entry.get("type") in types and (files is None or entry.get("path") in files))
    hasher = hashlib.sha256()
    if contract is not None:
        hasher.update(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode())
    for kind, relative in selected:
        _hash_path(hasher, root, relative, kind)
    return Fingerprint(sha256=f"sha256:{hasher.hexdigest()}", scope=tuple(path for _, path in selected))

def _binding_contract(adapter, gate) -> dict:
    bindings = {}
    if adapter and gate.id in adapter.gates:
        bindings = {cid: {**asdict(b), "promptDigest": adapter.prompt_digest(b)}
                    for cid, b in adapter.gates[gate.id].checks.items()}
    adapter_part = {"id": adapter.id, "role": adapter.role, "artifactDir": adapter.artifact_dir,
                    "checks": bindings} if adapter else None
    return {"gate": asdict(gate), "adapter": adapter_part}

def fingerprint_for_gate(doc, gate, workspace_root: Path, adapter) -> str:
    relevant = sorted((entry["type"], entry["path"]) for entry in doc.inputs
                      if entry.get("type") in gate.invalidates_on)
    plan = [{"id": t.id, "writes": list(t.writes), "reads": list(t.reads),
             "acceptance": t.acceptance, "dependsOn": list(t.depends_on)} for t in doc.subtasks]
    return fingerprint_gate(workspace_root, doc.inputs, types=list(gate.invalidates_on),
                            contract={"gate": _binding_contract(adapter, gate),
                                      "inputs": relevant, "plan": plan}).sha256
