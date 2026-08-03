from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class AdapterError(ValueError): ...


@dataclass(frozen=True)
class CheckBinding:
    cwd: str = "."
    argv: tuple[str, ...] = ()
    prompt_append: str | None = None
    timeout_seconds: int = 300


@dataclass(frozen=True)
class GateBinding:
    checks: dict[str, CheckBinding] = field(default_factory=dict)


@dataclass(frozen=True)
class Adapter:
    id: str
    role: str
    artifact_dir: str
    base_dir: Path
    gates: dict[str, GateBinding] = field(default_factory=dict)

    def resolve(self, value: str) -> Path:
        return (self.base_dir / value).resolve()

    def prompt_digest(self, binding: CheckBinding) -> str | None:
        if binding.prompt_append is None:
            return None
        path = self.resolve(binding.prompt_append)
        try:
            path.relative_to(self.base_dir)
        except ValueError as exc:
            raise AdapterError("promptAppend escapes adapter directory") from exc
        if not path.is_file():
            raise AdapterError(f"promptAppend is missing: {binding.prompt_append!r}")
        return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _mapping(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise AdapterError(f"{label} must be a mapping")
    return value


def _parse_check(gate_id: str, check_id: str, raw_check: object) -> CheckBinding:
    check = _mapping(raw_check, f"binding {gate_id}.{check_id}")
    if set(check) - {"cwd", "argv", "promptAppend", "timeoutSeconds"}:
        raise AdapterError(f"unsupported binding fields for {gate_id}.{check_id}")
    argv = check.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(arg, str) and arg for arg in argv)
    ):
        raise AdapterError(f"binding {gate_id}.{check_id} requires non-empty string argv")
    cwd = check.get("cwd", ".")
    if not isinstance(cwd, str):
        raise AdapterError(f"binding {gate_id}.{check_id} cwd must be a string")
    prompt_append = check.get("promptAppend")
    if prompt_append is not None and (not isinstance(prompt_append, str) or not prompt_append):
        raise AdapterError(f"binding {gate_id}.{check_id} promptAppend must be a non-empty string")
    timeout = check.get("timeoutSeconds", 300)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
        raise AdapterError(
            f"binding {gate_id}.{check_id} timeoutSeconds must be a positive integer"
        )
    return CheckBinding(
        cwd=cwd, argv=tuple(argv), prompt_append=prompt_append, timeout_seconds=timeout
    )


def load_adapter(path: Path) -> Adapter:
    path = path.resolve()
    data = _mapping(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, "adapter")
    unknown = set(data) - {"apiVersion", "id", "role", "artifactDir", "gates"}
    if unknown:
        raise AdapterError(f"unsupported adapter fields: {sorted(unknown)}")
    if data.get("apiVersion") != "acdd/adapter/v1":
        raise AdapterError("adapter apiVersion must be acdd/adapter/v1")
    artifact_dir = data.get("artifactDir", "artifacts")
    if not isinstance(artifact_dir, str):
        raise AdapterError("adapter artifactDir must be a string")
    for key in ("id", "role"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise AdapterError(f"adapter {key} is required")
    gates: dict[str, GateBinding] = {}
    for gate_id, raw_gate in _mapping(data.get("gates") or {}, "adapter gates").items():
        gate = _mapping(raw_gate, f"adapter gate {gate_id}")
        if set(gate) != {"checks"}:
            raise AdapterError(f"adapter gate {gate_id} must contain only checks")
        checks = {
            cid: _parse_check(gate_id, cid, raw)
            for cid, raw in _mapping(gate["checks"], f"checks for {gate_id}").items()
        }
        gates[gate_id] = GateBinding(checks=checks)
    return Adapter(
        id=data["id"],
        role=data["role"],
        artifact_dir=data.get("artifactDir", "artifacts"),
        base_dir=path.parent,
        gates=gates,
    )


def index_adapters(adapters: list[Adapter]) -> dict[str, Adapter]:
    indexed: dict[str, Adapter] = {}
    for adapter in adapters:
        if adapter.role in indexed:
            raise AdapterError(f"duplicate adapter role {adapter.role!r}")
        indexed[adapter.role] = adapter
    return indexed
