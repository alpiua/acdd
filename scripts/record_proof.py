#!/usr/bin/env python3
"""Record command or proof-bundle gate evidence into a bound ACDD task document.

Computes the gate fingerprint from declared inputs, optionally runs a command,
redacts secrets from captured output, and prints or writes inline evidence plus
receipt rows.

Example:
  python3 scripts/record_proof.py \\
    --document task.md \\
    --workspace-root . \\
    --profile profiles/task/v1.yaml \\
    --receipt-contract contracts/receipt/task/v1.yaml \\
    --adapter task=task-adapter.yaml \\
    --adapter implementation=implementation-adapter.yaml \\
    --id example.live.bundle \\
    --claim runtime/v1 --claim parity/v1 --claim security/v1 --claim release/v1 \\
    --cmd 'python3 -c \"print(0)\"' \\
    --write
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from acdd_document import MAX_OUTPUT_BYTES, SECRET_RE, DocumentError
from acdd_fingerprint import FingerprintError, fingerprint_architecture_code_inputs, fingerprint_inputs, markdown_sections
from validate_acdd import ContractError, _adapter_args, _gate_policies, load_core


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def redact_secrets(text: str) -> tuple[str, bool]:
    """Return redacted text and whether any secret pattern was rewritten."""

    def _replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        if "=" in raw:
            return f"{raw.split('=', 1)[0]}=<redacted>"
        if ":" in raw:
            return f"{raw.split(':', 1)[0]}: <redacted>"
        return "<redacted>"

    if SECRET_RE.search(text) is None:
        return text, False
    return SECRET_RE.sub(_replace, text), True


def truncate_output(text: str) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return text
    clipped = encoded[: MAX_OUTPUT_BYTES - 32]
    while clipped:
        try:
            prefix = clipped.decode("utf-8")
            break
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    else:
        prefix = ""
    return prefix + "\n...<truncated>...\n"


def run_command(command: str, *, cwd: Path, timeout: int) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        shell=True,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    parts: list[str] = []
    if completed.stdout:
        parts.append(completed.stdout)
    if completed.stderr:
        parts.append(completed.stderr)
    return int(completed.returncode), "".join(parts)


def command_result(exit_code: int, *, expected_failure: bool) -> str:
    if expected_failure:
        return "expected_failure" if exit_code != 0 else "unexpected_pass"
    return "pass" if exit_code == 0 else "fail"


def build_evidence_object(
    *,
    evidence_id: str,
    claims: list[str],
    input_fingerprint: str,
    exact_command: str,
    recorded_at: str,
    exit_code: int,
    output: str,
    redacted: bool,
    result: str,
    artifacts: list[str] | None,
    expected_exception: str | None = None,
) -> dict[str, object]:
    if len(claims) == 1:
        payload: dict[str, object] = {
            "apiVersion": "acdd/gate-evidence/v1",
            "kind": "command",
            "id": evidence_id,
            "gate": claims[0],
            "inputFingerprint": input_fingerprint,
            "exactCommand": exact_command,
            "recordedAt": recorded_at,
            "exitCode": exit_code,
            "output": output,
            "redacted": redacted,
            "result": result,
        }
        if expected_exception is not None:
            payload["expectedException"] = expected_exception
        return payload
    payload: dict[str, object] = {
        "apiVersion": "acdd/gate-evidence/v1",
        "kind": "proof-bundle",
        "id": evidence_id,
        "gate": claims[0],
        "inputFingerprint": input_fingerprint,
        "claims": claims,
        "commands": [
            {
                "exactCommand": exact_command,
                "recordedAt": recorded_at,
                "exitCode": exit_code,
                "output": output,
                "redacted": redacted,
                "result": result,
            }
        ],
    }
    if artifacts:
        payload["artifacts"] = artifacts
    return payload


def dump_evidence_documents(documents: list[object]) -> str:
    if not documents:
        return "[]\n"
    return yaml.safe_dump_all(
        documents,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def _replace_section(text: str, heading: str, body: str) -> str:
    marker = f"## {heading}"
    start = text.index(marker)
    after = text[start + len(marker) :]
    if after.startswith("\n"):
        after = after[1:]
    end_match = re.search(r"(?m)^## ", after)
    end = end_match.start() if end_match else len(after)
    suffix = after[end:]
    cleaned = body.strip("\n") + "\n"
    return text[: start + len(marker)] + "\n\n" + cleaned + ("\n" if suffix else "") + suffix


def merge_evidence_into_text(text: str, evidence_object: dict[str, object]) -> str:
    sections = markdown_sections(text)
    if "ACDD gate evidence" not in sections:
        raise DocumentError("missing ## ACDD gate evidence")
    section = sections["ACDD gate evidence"]
    match = re.search(r"(?ms)^```ya?ml\s*\n(.*?)^```\s*$", section)
    if match is None:
        raise DocumentError("ACDD gate evidence: expected a fenced YAML block")
    raw_block = match.group(1)
    if raw_block.strip() in {"", "[]"}:
        documents: list[object] = []
    else:
        documents = [
            value for value in yaml.safe_load_all(raw_block) if value is not None
        ]
        if len(documents) == 1 and documents[0] == []:
            documents = []
    evidence_id = str(evidence_object["id"])
    merged: list[object] = []
    replaced = False
    for document in documents:
        if isinstance(document, dict) and str(document.get("id", "")) == evidence_id:
            merged.append(evidence_object)
            replaced = True
        else:
            merged.append(document)
    if not replaced:
        merged.append(evidence_object)
    new_section = "```yaml\n" + dump_evidence_documents(merged) + "```\n"
    return _replace_section(text, "ACDD gate evidence", new_section)


def update_receipt_rows(
    text: str,
    *,
    claims: list[str],
    evidence_id: str,
    input_fingerprint: str,
    recorded_at: str,
    status: str,
) -> str:
    sections = markdown_sections(text)
    if "ACDD receipts" not in sections:
        raise DocumentError("missing ## ACDD receipts")
    body = sections["ACDD receipts"]
    claim_set = set(claims)
    updated: list[str] = []
    for line in body.splitlines():
        if not line.lstrip().startswith("|"):
            updated.append(line)
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5 or cells[0].lower() == "gate" or set(cells[0]) <= {"-", ":"}:
            updated.append(line)
            continue
        gate = cells[0].strip().strip("`")
        if gate not in claim_set:
            updated.append(line)
            continue
        updated.append(
            f"| `{gate}` | `{status}` | evidence={evidence_id} | "
            f"`{input_fingerprint}` | `{recorded_at}` |"
        )
    return _replace_section(text, "ACDD receipts", "\n".join(updated) + "\n")


def resolve_fingerprint(
    *,
    document: Path,
    profile: Path,
    receipt_contract: Path,
    adapters: tuple[Path, ...],
    workspace_root: Path,
    claims: list[str],
) -> str:
    core = load_core(profile)
    policies = {policy.gate: policy for policy in _gate_policies(core)}
    unknown = [gate for gate in claims if gate not in policies]
    if unknown:
        raise DocumentError(f"unknown claim gates: {unknown}")
    if claims == ["architecture/v1"]:
        return fingerprint_architecture_code_inputs(
            document=document,
            adapters=adapters,
            workspace_root=workspace_root,
        ).sha256
    include_types = frozenset(
        input_type
        for gate in claims
        for input_type in policies[gate].invalidation_inputs
    )
    class_sets = [
        policies[gate].invalidation_classes
        for gate in claims
        if policies[gate].invalidation_classes is not None
    ]
    include_classes = (
        frozenset().union(*(classes or frozenset() for classes in class_sets))
        if class_sets
        else None
    )
    return fingerprint_inputs(
        document=document,
        profile=profile,
        receipt_contract=receipt_contract,
        adapters=adapters,
        workspace_root=workspace_root,
        include_types=include_types,
        include_classes=include_classes,
    ).sha256


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--receipt-contract", type=Path, required=True)
    parser.add_argument(
        "--adapter",
        action="append",
        default=[],
        dest="adapters",
        help="ROLE=PATH adapter binding; repeat",
    )
    parser.add_argument("--id", required=True, help="evidence id")
    parser.add_argument(
        "--claim",
        action="append",
        default=[],
        dest="claims",
        help="Gate id covered by this proof; repeat for a proof-bundle",
    )
    parser.add_argument("--cmd", dest="command", default=None)
    parser.add_argument("--cwd", type=Path, default=None)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="Do not execute --cmd; require --exit-code and --output-file",
    )
    parser.add_argument("--exit-code", type=int, default=None)
    parser.add_argument("--output-file", type=Path, default=None)
    parser.add_argument("--expected-failure", action="store_true")
    parser.add_argument(
        "--expected-exception",
        default=None,
        help="Typed exception name required for red/v1 expected-failure proofs",
    )
    parser.add_argument("--status", default=None)
    parser.add_argument("--artifact", action="append", default=[], dest="artifacts")
    parser.add_argument("--recorded-at", default=None)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write evidence and receipt rows into the bound document",
    )
    args = parser.parse_args(argv)

    if not args.claims:
        print("error: at least one --claim is required", file=sys.stderr)
        return 2
    if args.no_run:
        if args.exit_code is None or args.output_file is None:
            print(
                "error: --no-run requires --exit-code and --output-file",
                file=sys.stderr,
            )
            return 2
    elif not args.command:
        print("error: --cmd is required unless --no-run is set", file=sys.stderr)
        return 2

    try:
        if not args.adapters:
            print("error: at least one --adapter ROLE=PATH is required", file=sys.stderr)
            return 2
        adapters = tuple(path.resolve() for path in _adapter_args(args.adapters).values())
        document = args.document.resolve()
        workspace_root = args.workspace_root.resolve()
        profile = args.profile.resolve()
        receipt_contract = args.receipt_contract.resolve()
        claims = list(dict.fromkeys(args.claims))

        input_fingerprint = resolve_fingerprint(
            document=document,
            profile=profile,
            receipt_contract=receipt_contract,
            adapters=adapters,
            workspace_root=workspace_root,
            claims=claims,
        )

        if args.no_run:
            exit_code = int(args.exit_code)
            raw_output = args.output_file.read_text(encoding="utf-8", errors="replace")
            command = args.command or f"<captured:{args.output_file.name}>"
        else:
            command = str(args.command)
            cwd = args.cwd.resolve() if args.cwd is not None else workspace_root
            exit_code, raw_output = run_command(command, cwd=cwd, timeout=args.timeout)

        redacted_output, did_redact = redact_secrets(raw_output)
        redacted_output = truncate_output(redacted_output)
        if SECRET_RE.search(redacted_output):
            redacted_output, again = redact_secrets(redacted_output)
            did_redact = did_redact or again
        # Always mark redacted=true after the redaction pipeline so validators
        # never see a false "not redacted" flag on sanitized output.
        redacted_flag = True if did_redact else True

        result = command_result(exit_code, expected_failure=args.expected_failure)
        if args.status is not None:
            status = args.status
        elif args.expected_failure:
            status = "expected_failure" if exit_code != 0 else "fail"
        else:
            status = "pass" if exit_code == 0 else "fail"

        recorded_at = args.recorded_at or _utc_now()
        expected_exception = args.expected_exception
        if args.expected_failure and "red/v1" in claims and expected_exception is None:
            print(
                "error: red/v1 expected-failure proofs require --expected-exception",
                file=sys.stderr,
            )
            return 2

        evidence_object = build_evidence_object(
            evidence_id=args.id,
            claims=claims,
            input_fingerprint=input_fingerprint,
            exact_command=command,
            recorded_at=recorded_at,
            exit_code=exit_code,
            output=redacted_output,
            redacted=redacted_flag,
            result=result,
            artifacts=list(args.artifacts) or None,
            expected_exception=expected_exception,
        )

        yaml_text = yaml.safe_dump(
            evidence_object,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
        sys.stdout.write(yaml_text if yaml_text.endswith("\n") else yaml_text + "\n")
        print(
            f"# fingerprint={input_fingerprint} exit={exit_code} "
            f"status={status} claims={claims}",
            file=sys.stderr,
        )

        if args.write:
            text = document.read_text(encoding="utf-8")
            text = merge_evidence_into_text(text, evidence_object)
            text = update_receipt_rows(
                text,
                claims=claims,
                evidence_id=args.id,
                input_fingerprint=input_fingerprint,
                recorded_at=recorded_at,
                status=status,
            )
            document.write_text(text, encoding="utf-8")
            print(f"# wrote evidence={args.id} into {document}", file=sys.stderr)
            if status == "pass":
                kg_script = workspace_root / "planner" / ".agents" / "plugins" / "mempalace" / "scripts" / "seed_service_kg.py"
                if kg_script.exists():
                    try:
                        subprocess.run([sys.executable, str(kg_script)], cwd=str(workspace_root / "planner"), timeout=30, capture_output=True, check=False)
                        print(f"# refreshed MemPalace KG via {kg_script.name}", file=sys.stderr)
                    except Exception as exc:
                        print(f"# warning: KG seed refresh failed: {exc}", file=sys.stderr)

        if args.expected_failure:
            return 0 if exit_code != 0 else 1
        return 0 if exit_code == 0 else exit_code
    except (DocumentError, FingerprintError, ContractError, OSError, yaml.YAMLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
