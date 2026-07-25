#!/usr/bin/env python3
"""Compute the targeted ACDD gate rerun set for typed input changes.

Input syntax: ``--change TYPE:PATH[:CLASS[,CLASS...]]``. Omit classes to fail
closed and invalidate all policies that include the type.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from invalidation import (
    ChangedInput,
    InvalidationError,
    invalidation_plan,
    load_graph,
    policy_map_from_contract,
)
from validate_acdd import ContractError, load_core


def parse_change(raw: str) -> ChangedInput:
    parts = raw.split(":", 2)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise InvalidationError(
            f"invalid --change {raw!r}; expected TYPE:PATH[:CLASS[,CLASS...]]"
        )
    classes = None
    if len(parts) == 3:
        values = [value for value in parts[2].split(",") if value]
        if not values:
            raise InvalidationError(f"invalid --change classes: {raw!r}")
        classes = frozenset(values)
    return ChangedInput(parts[0], parts[1], classes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--receipt-contract", type=Path, required=True)
    parser.add_argument("--change", action="append", required=True)
    args = parser.parse_args(argv)
    try:
        core = load_core(args.profile.resolve())
        gate_order = core.gate_ids
        policies = policy_map_from_contract(args.receipt_contract.resolve(), gate_order)
        graph = load_graph(args.receipt_contract.resolve(), gate_order)
        changes = [parse_change(raw) for raw in args.change]
        rerun = invalidation_plan(
            policies=policies,
            graph=graph,
            changes=changes,
            gate_order=gate_order,
        )
        print(
            json.dumps(
                {
                    "changes": [
                        {
                            "type": change.type,
                            "path": change.path,
                            "classes": sorted(change.classes)
                            if change.classes is not None
                            else None,
                        }
                        for change in changes
                    ],
                    "rerunGates": list(rerun),
                    "unknownOrUnscopedFailClosed": any(
                        change.classes is None for change in changes
                    ),
                },
                indent=2,
            )
        )
        return 0
    except (InvalidationError, ContractError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
