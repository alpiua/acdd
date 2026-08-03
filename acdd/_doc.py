from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml

from .model import INAPPLICABLE, PASS, AcddError

RESERVED_EXITS = frozenset({124, 127})
TERMINAL_STATUSES = frozenset({PASS, INAPPLICABLE})


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def resolve_under(root: Path, relative: str, *, label: str = "path") -> Path:
    root = root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes workspace root: {relative!r}") from exc
    return candidate


def confined(root: Path, relative: str, label: str) -> Path:
    try:
        return resolve_under(root, relative, label=label)
    except ValueError as exc:
        raise AcddError(f"{label} path escapes workspace: {relative!r}") from exc


def relative_ref(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def read_jsonl(path: Path) -> list[dict] | None:
    try:
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError):
        return None
    return records if all(isinstance(record, dict) for record in records) else None


def terminal_matches(terminal: dict | None, evidence_id: str, gate_id: str, check_id: str) -> bool:
    return (
        bool(terminal)
        and terminal.get("evidenceId") == evidence_id
        and terminal.get("gate") == gate_id
        and terminal.get("check") == check_id
    )


def review_scope_ok(dimensions: tuple[str, ...], terminal: dict, records: list[dict]) -> bool:
    scope, performed, reviewed = (
        terminal.get("scope"),
        terminal.get("performedChecks"),
        terminal.get("reviewedSessionUuids"),
    )
    try:
        raws, sessions = records[:-1], [row["reviewerSessionUuid"] for row in records[:-1]]
        raw_ok = (
            bool(raws)
            and terminal.get("reviewerSessionUuid") in sessions
            and isinstance(reviewed, list)
            and set(reviewed) == set(sessions)
            and len(reviewed) == len(set(reviewed)) == len(sessions)
            and all(
                set(row) == {"type", "reviewerSessionUuid", "raw"}
                and row["type"] == "review_raw"
                and isinstance(row["reviewerSessionUuid"], str)
                and isinstance(row["raw"], str)
                and row["reviewerSessionUuid"] != terminal.get("authorSessionUuid")
                and uuid.UUID(row["reviewerSessionUuid"])
                for row in raws
            )
        )
    except (KeyError, TypeError, ValueError):
        raw_ok = False
    return (
        isinstance(scope, list)
        and scope
        and all(isinstance(item, str) and item for item in scope)
        and isinstance(performed, list)
        and all(isinstance(item, str) for item in performed)
        and set(dimensions).issubset(set(performed))
        and raw_ok
    )


def command_outcome_ok(check, terminal: dict) -> bool:
    code = terminal.get("exitCode")
    if not (
        terminal.get("type") == "command_run"
        and isinstance(code, int)
        and not isinstance(code, bool)
        and not terminal.get("timeout")
        and not terminal.get("executionError")
    ):
        return False
    if check.command_outcome == "success":
        return code == 0
    return check.command_outcome == "expected-failure" and code != 0 and code not in RESERVED_EXITS


def prior_nonterminal(receipts: list[dict], gate_id: str) -> str | None:
    for receipt in receipts:
        if receipt.get("gate") == gate_id:
            return None
        if receipt.get("status") not in TERMINAL_STATUSES:
            return str(receipt.get("gate"))
    return None


_HEADING = re.compile(r"^(#{1,2})[ \t]+(.+?)\s*$")


def extract_sections(path: Path, names: tuple[str, ...]) -> dict[str, str]:
    """Extract raw Markdown bodies for exact # / ## headings (not ###).

    Extraction stops at the next # or ## heading. Heading titles are matched
    after strip(). Missing names fail closed.
    """
    if not names:
        return {}
    wanted = {name.strip() for name in names}
    text = path.read_text(encoding="utf-8")
    bodies: dict[str, list[str]] = {}
    present: set[str] = set()
    current: str | None = None
    for line in text.splitlines(keepends=True):
        match = _HEADING.match(line.rstrip("\n"))
        if match:
            title = match.group(2).strip()
            if title in wanted:
                present.add(title)
                bodies.setdefault(title, [])
                current = title
            else:
                current = None
            continue
        if current is not None:
            bodies[current].append(line)
    missing = [name for name in names if name.strip() not in present]
    if missing:
        raise ValueError(f"contractSections missing headings: {missing!r}")
    return {name: "".join(bodies.get(name.strip(), [])) for name in names}


def append_evidence(doc_path: Path, payload: dict) -> None:
    text = doc_path.read_text(encoding="utf-8")
    block = (
        "```yaml\n"
        + yaml.safe_dump(payload, sort_keys=True, allow_unicode=True).rstrip()
        + "\n```\n"
    )
    match = re.search(r"^## Evidence\s*$", text, re.MULTILINE)
    if match:
        marker = match.group(0) + "\n"
        before, after = text.split(marker, 1)
        doc_path.write_text(before + marker + "\n" + block + after, encoding="utf-8")
        return
    receipts = "## Receipts\n"
    if receipts not in text:
        raise ValueError("document has no Evidence or Receipts section")
    before, after = text.split(receipts, 1)
    doc_path.write_text(
        before + "## Evidence\n" + "\n" + block + "\n" + receipts + after, encoding="utf-8"
    )


def upsert_receipt(
    *,
    doc_path: Path,
    gate_id: str,
    status: str,
    evidence_ref: str,
    fingerprint: str,
    recorded_at: str,
) -> None:
    lines = doc_path.read_text(encoding="utf-8").splitlines()
    row = f"| {gate_id} | {status} | {evidence_ref} | {fingerprint} | {recorded_at} |"
    for index, line in enumerate(lines):
        if line.startswith(f"| {gate_id} |"):
            lines[index] = row
            doc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    try:
        section = lines.index("## Receipts")
    except ValueError as exc:
        raise ValueError("document has no Receipts section") from exc
    insert_at = section + 1
    while insert_at < len(lines) and (
        not lines[insert_at].startswith("|")
        or "---" in lines[insert_at]
        or "gate" in lines[insert_at].lower()
    ):
        insert_at += 1
    lines.insert(insert_at, row)
    doc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
