from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from ._doc import resolve_under
from .adapter import Adapter, AdapterError, index_adapters, load_adapter
from .model import AcddError, load_document, load_profile
from .record import finalize_gate, record_check, record_review
from .validate import validate

def _req(parser: argparse.ArgumentParser, *flags: str) -> None:
    for flag in flags:
        kwargs: dict = {"required": True}
        if flag == "--id":
            kwargs["dest"] = "evidence_id"
        parser.add_argument(flag, **kwargs)

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acdd", description="ACDD v2 — 5 gates, checks per profile, 11 invariants")
    commands = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("document")
    common.add_argument("profile")
    common.add_argument("--adapter", action="append", default=[], help="role=path (repeatable)")
    common.add_argument("--workspace-root", default=".")
    commands.add_parser("validate", parents=[common])
    fingerprint = commands.add_parser("fingerprint", parents=[common])
    _req(fingerprint, "--gate")
    record = commands.add_parser("record", parents=[common])
    _req(record, "--gate", "--check", "--id")
    record.add_argument("--classified-ref", action="append", default=[], help="path=role; required for basis evidence")
    finalize = commands.add_parser("finalize", parents=[common])
    _req(finalize, "--gate", "--id")
    finalize.add_argument("--status", default="pass")
    finalize.add_argument("--reason-code")
    review = commands.add_parser("review", parents=[common])
    _req(review, "--gate", "--check", "--id", "--transcript", "--author-uuid", "--reviewer-uuid")
    review.add_argument("--verdict", default="pass")
    return parser

def _load_confined(role: str | None, raw_path: str, *, workspace: Path) -> Adapter:
    try:
        resolved = resolve_under(workspace, raw_path, label="adapter")
    except ValueError as exc:
        raise AcddError(f"adapter path escapes workspace root: {raw_path!r}") from exc
    adapter = load_adapter(resolved)
    if role is not None and adapter.role != role:
        raise AcddError(f"adapter role {adapter.role!r} does not match {role!r}")
    return adapter

def _discover(workspace: Path) -> list[Path]:
    found, stack = [], [workspace]
    while stack:
        directory = stack.pop()
        try:
            children = sorted(directory.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and not child.is_symlink():
                if child.name == ".acdd2" or not child.name.startswith(".") and child.name != "node_modules":
                    stack.append(child)
            elif not child.is_symlink() and child.suffix == ".yaml" and child.parent.name == ".acdd2":
                found.append(child)
    return sorted(found)

def _adapters(items: list[str], workspace: Path) -> list[Adapter]:
    adapters: dict[str, Adapter] = {}
    for path in _discover(workspace):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict) or data.get("apiVersion") != "acdd/adapter/v1":
            continue
        adapter = load_adapter(path)
        if adapter.role in adapters:
            raise AcddError(f"duplicate adapter role {adapter.role!r}: {path} and "
                            f"{adapters[adapter.role].base_dir}")
        adapters[adapter.role] = adapter
    for item in items:
        if "=" not in item:
            raise AcddError("adapter must be role=path")
        role, raw_path = item.split("=", 1)
        adapters[role] = _load_confined(role, raw_path, workspace=workspace)
    return list(adapters.values())

def _owner(adapters, role):
    return adapters.get(role) or (_ for _ in ()).throw(AcddError(f"missing adapter for owner role {role!r}"))

def _gate(profile, gate_id):
    for gate in profile.gates:
        if gate.id == gate_id:
            return gate
    raise AcddError(f"unknown gate {gate_id!r}")

def _context(args):
    profile = load_profile(Path(args.profile).resolve())
    document = load_document(Path(args.document).resolve())
    workspace = Path(args.workspace_root).resolve()
    adapters = _adapters(args.adapter, workspace)
    return document, profile, index_adapters(adapters), workspace, adapters

def _gate_adapter(args, gate_id):
    document, profile, adapters, workspace, _ = _context(args)
    gate = _gate(profile, gate_id)
    return document, gate, adapters.get(gate.owner) or _owner(adapters, gate.owner), workspace

def cmd_validate(args) -> int:
    document, profile, _, workspace, adapters = _context(args)
    errors = validate(document, profile, adapters=adapters, workspace_root=workspace)
    if errors:
        for error in errors:
            print(f"ACDD INVALID [{error.invariant}]: {error}", file=sys.stderr)
        return 1
    print("ACDD VALID")
    return 0

def cmd_fingerprint(args) -> int:
    from .fingerprint import fingerprint_for_gate
    document, profile, adapters, workspace, _ = _context(args)
    gate = _gate(profile, args.gate)
    print(fingerprint_for_gate(document, gate, workspace, adapters.get(gate.owner)))
    return 0

def cmd_record(args) -> int:
    document, gate, adapter, workspace = _gate_adapter(args, args.gate)
    classified_refs = [{"path": p, "role": r} for item in args.classified_ref
                       for p, r in [item.split("=", 1)]
                       if "=" in item or (_ for _ in ()).throw(AcddError("classified-ref must be path=role"))]
    payload, succeeded = record_check(document=document, workspace_root=workspace, gate=gate,
                                      check_id=args.check, evidence_id=args.evidence_id,
                                      adapter=adapter, classified_refs=classified_refs)
    if payload:
        print(json.dumps(payload, sort_keys=True))
    return 0 if succeeded else 1

def cmd_finalize(args) -> int:
    document, gate, adapter, workspace = _gate_adapter(args, args.gate)
    payload = finalize_gate(document=document, workspace_root=workspace, gate=gate,
                            evidence_id=args.evidence_id, adapter=adapter,
                            status=args.status, reason_code=args.reason_code)
    print(json.dumps(payload, sort_keys=True))
    return 0

def cmd_review(args) -> int:
    document, gate, adapter, workspace = _gate_adapter(args, args.gate)
    payload = record_review(document=document, workspace_root=workspace, gate=gate, check_id=args.check,
                            evidence_id=args.evidence_id, adapter=adapter,
                            transcript=Path(args.transcript), author_uuid=args.author_uuid,
                            reviewer_uuid=args.reviewer_uuid, verdict=args.verdict)
    print(json.dumps(payload, sort_keys=True))
    return 0
_COMMANDS = {"validate": cmd_validate, "fingerprint": cmd_fingerprint, "record": cmd_record,
             "finalize": cmd_finalize, "review": cmd_review}

def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        return _COMMANDS[args.command](args)
    except (AcddError, AdapterError, ValueError) as error:
        print(f"ACDD ERROR: {error}", file=sys.stderr)
        return 2
if __name__ == "__main__":
    raise SystemExit(main())
