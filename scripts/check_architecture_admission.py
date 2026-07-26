#!/usr/bin/env python3
"""Pre-launch G0 architecture admission check.

Exit 0 when the next architecture fingerprint is admitted; exit 2 when blocked.
Prints a one-line status plus structured details on stderr.

Example:
  python3 scripts/check_architecture_admission.py \\
    --document task.md \\
    --workspace-root . \\
    --profile profiles/task/v1.yaml \\
    --receipt-contract contracts/receipt/task/v1.yaml \\
    --adapter task=task-adapter.yaml \\
    --adapter implementation=implementation-adapter.yaml
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from architecture_governor import (
    ArchitectureGovernorError,
    collect_dirty_paths,
    declared_implementation_paths,
    material_fail_fingerprints,
    may_launch_architecture,
    parse_architecture_admission,
)
from acdd_fingerprint import FingerprintError, fingerprint_architecture_candidate
from validate_acdd import ContractError, _adapter_args


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--receipt-contract", type=Path, required=True)
    parser.add_argument("--adapter", action="append", default=[], dest="adapters")
    parser.add_argument(
        "--fingerprint",
        default=None,
        help="Override next fingerprint (default: compute architecture/v1 fingerprint)",
    )
    args = parser.parse_args(argv)
    try:
        if not args.adapters:
            print("error: at least one --adapter ROLE=PATH is required", file=sys.stderr)
            return 2
        adapters = tuple(path.resolve() for path in _adapter_args(args.adapters).values())
        document = args.document.resolve()
        workspace_root = args.workspace_root.resolve()
        profile = args.profile.resolve()
        receipt_contract = args.receipt_contract.resolve()
        text = document.read_text(encoding="utf-8")
        admission = parse_architecture_admission(text)
        dirty = collect_dirty_paths(workspace_root)
        declared = sorted(declared_implementation_paths(text))
        if args.fingerprint:
            next_fp = args.fingerprint
        else:
            next_fp = fingerprint_architecture_candidate(
                document=document,
                adapters=adapters,
                workspace_root=workspace_root,
            ).sha256
        ok, reason = may_launch_architecture(
            text=text,
            workspace_root=workspace_root,
            next_fingerprint=next_fp,
            dirty_paths=dirty,
        )
        payload = {
            "admitted": ok,
            "reason": reason,
            "nextFingerprint": next_fp,
            "maxMaterialAttempts": admission.max_material_attempts,
            "materialFailFingerprints": list(
                material_fail_fingerprints(admission.attempts)
            ),
            "candidatePaths": [item.path for item in admission.candidate_set],
            "dirtyPaths": list(dirty),
            "declaredImplementationPaths": declared,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        if ok:
            print(f"ADMITTED: {reason}", file=sys.stderr)
            return 0
        print(f"BLOCKED: {reason}", file=sys.stderr)
        return 2
    except (ArchitectureGovernorError, FingerprintError, ContractError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
