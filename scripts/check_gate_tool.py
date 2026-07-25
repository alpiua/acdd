#!/usr/bin/env python3
"""Fail closed when a tool is outside the queued gate's adapter envelope."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gate_tool_policy import evaluate_gate_tool_call, resolve_procedure_aliases
from validate_acdd import ContractError, _adapter_args


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--queued-gate", required=True)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--adapter", action="append", default=[], dest="adapters")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.adapters:
            print("error: at least one --adapter ROLE=PATH is required", file=sys.stderr)
            return 2
        adapters = _adapter_args(args.adapters)
        admit, deny, aliases = resolve_procedure_aliases(
            profile_path=args.profile.resolve(),
            adapters=adapters,
            queued_gate=args.queued_gate,
        )
        decision = evaluate_gate_tool_call(
            tool_name=args.tool,
            queued_gate=args.queued_gate,
            admit=admit,
            deny=deny,
            aliases=aliases,
        )
        payload = {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "normalizedTool": decision.normalized_tool,
            "queuedGate": args.queued_gate,
            "tool": args.tool,
            "admit": sorted(admit),
            "deny": sorted(deny),
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        if decision.allowed:
            if not args.json:
                print(f"ALLOWED: {args.tool} for {args.queued_gate}")
            return 0
        print(decision.reason or "ToolDeniedForQueuedGate", file=sys.stderr)
        return 403
    except (ContractError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
