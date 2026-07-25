#!/usr/bin/env python3
"""Run adapter-supplied AST structural invariants for a gate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from structural_invariants import StructuralInvariantError, check_rules, load_contract
from validate_acdd import ContractError, _adapter_args, load_adapter, load_core, resolve_gate_execution

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = PLUGIN_ROOT / "contracts" / "structural-invariants" / "v1.yaml"


def _resolve_invariants_path(
    *,
    adapter_path: Path,
    procedure: dict[str, object],
    label: str,
    allowed_root: Path,
) -> Path | None:
    raw = procedure.get("structuralInvariants")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ContractError(f"{label}.structuralInvariants must be an adapter-relative path")
    from validate_acdd import _resolve

    return _resolve(adapter_path, raw, f"{label}.structuralInvariants", allowed_root=allowed_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--queued-gate", required=True)
    parser.add_argument("--adapter", action="append", default=[], dest="adapters")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.adapters:
            print("error: at least one --adapter ROLE=PATH is required", file=sys.stderr)
            return 2
        adapters = _adapter_args(args.adapters)
        profile = args.profile.resolve()
        workspace_root = args.workspace_root.resolve()
        core = load_core(profile)
        loaded = {
            role: load_adapter(path, role, core, allowed_root=workspace_root)
            for role, path in adapters.items()
        }
        executor, procedure = resolve_gate_execution(core, loaded, args.queued_gate)
        adapter_path = adapters[executor].resolve()
        invariants_path = _resolve_invariants_path(
            adapter_path=adapter_path,
            procedure=procedure,
            label=f"{adapter_path}:gateProcedures.{args.queued_gate}",
            allowed_root=workspace_root,
        )
        if invariants_path is None:
            print(f"NOOP: {args.queued_gate} declares no structuralInvariants", file=sys.stderr)
            return 0
        rules = load_contract(invariants_path, schema_path=SCHEMA)
        violations = check_rules(rules, workspace_root=workspace_root)
        payload = {
            "queuedGate": args.queued_gate,
            "contract": str(invariants_path),
            "violations": [
                {
                    "ruleId": item.rule_id,
                    "path": item.path,
                    "line": item.line,
                    "column": item.column,
                    "message": item.message,
                }
                for item in violations
            ],
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        if violations:
            for item in violations:
                print(
                    f"VIOLATION: {item.rule_id} {item.path}:{item.line}:{item.column} {item.message}",
                    file=sys.stderr,
                )
            return 2
        print(f"PASS: {len(rules)} structural invariants satisfied for {args.queued_gate}")
        return 0
    except (ContractError, StructuralInvariantError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
