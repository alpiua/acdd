"""Evaluate ACDD adapter tool envelopes for a queued gate."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_TOOL_ALIASES: dict[str, str] = {
    "bash_raw_cat": "bash",
    "bash_raw_head": "bash",
    "bash_raw_tail": "bash",
    "lean_ctx_ctx_shell": "bash",
    "ctx_shell": "bash",
    "shell": "bash",
    "write": "edit",
    "lean_ctx_ctx_edit": "edit",
    "lean_ctx_ctx_patch": "edit",
    "ctx_edit": "edit",
    "ctx_patch": "edit",
}


@dataclass(frozen=True)
class GateToolDecision:
    allowed: bool
    reason: str | None = None
    normalized_tool: str | None = None


def normalize_tool_name(tool_name: str, aliases: Mapping[str, str] | None = None) -> str:
    mapping = {**DEFAULT_TOOL_ALIASES, **(aliases or {})}
    current = tool_name.strip()
    seen: set[str] = set()
    while current not in seen:
        seen.add(current)
        mapped = mapping.get(current)
        if mapped is None:
            return current
        current = mapped
    return current


def evaluate_gate_tool_call(
    *,
    tool_name: str,
    queued_gate: str,
    admit: frozenset[str],
    deny: frozenset[str],
    aliases: Mapping[str, str] | None = None,
) -> GateToolDecision:
    normalized = normalize_tool_name(tool_name, aliases)
    candidates = {tool_name, normalized}
    if candidates & deny:
        return GateToolDecision(
            allowed=False,
            normalized_tool=normalized,
            reason=f"ToolDeniedForQueuedGate: {tool_name} denied for {queued_gate}",
        )
    if admit and not (candidates & admit):
        return GateToolDecision(
            allowed=False,
            normalized_tool=normalized,
            reason=f"ToolDeniedForQueuedGate: {tool_name} not admitted for {queued_gate}",
        )
    return GateToolDecision(allowed=True, normalized_tool=normalized)


def load_aliases(procedure: Mapping[str, object]) -> dict[str, str]:
    raw = procedure.get("toolAliases")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("toolAliases must be a mapping")
    aliases: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str) or not key.strip() or not value.strip():
            raise ValueError("toolAliases keys and values must be non-empty strings")
        aliases[key.strip()] = value.strip()
    return aliases


def resolve_procedure_aliases(
    *,
    profile_path: Path,
    adapters: dict[str, Path],
    queued_gate: str,
) -> tuple[frozenset[str], frozenset[str], dict[str, str]]:
    from validate_acdd import ContractError, gate_tool_envelope, load_adapter, load_core, resolve_gate_execution

    core = load_core(profile_path)
    loaded = {
        role: load_adapter(path, role, core, allowed_root=profile_path.parents[2])
        for role, path in adapters.items()
    }
    executor, procedure = resolve_gate_execution(core, loaded, queued_gate)
    admit, deny = gate_tool_envelope(core, loaded, queued_gate)
    aliases = load_aliases(procedure)
    return admit, deny, aliases
