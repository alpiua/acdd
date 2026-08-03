from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

PENDING, PARTIAL, BLOCKED, PASS, INAPPLICABLE = (
    "pending",
    "partial",
    "blocked",
    "pass",
    "inapplicable",
)
STATUSES = {PENDING, PARTIAL, BLOCKED, PASS, INAPPLICABLE}
EVIDENCE_KINDS = {"command", "basis", "review", "bundle"}


class AcddError(ValueError):
    def __init__(self, message: str, *, invariant: int = 0):
        super().__init__(message)
        self.invariant = invariant


@dataclass(frozen=True)
class Check:
    id: str
    evidence_kind: str
    command_outcome: str


@dataclass(frozen=True)
class Gate:
    id: str
    owner: str
    checks: tuple[Check, ...]
    invalidates_on: tuple[str, ...]
    terminals: tuple[str, ...]
    inapplicable_reason_codes: tuple[str, ...] = ()
    review_dimensions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Subtask:
    id: str
    writes: tuple[str, ...]
    reads: tuple[str, ...]
    acceptance: str
    depends_on: tuple[str, ...] = ()
    supersedes: str | None = None

    def scope(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.writes) | set(self.reads)))


@dataclass
class Profile:
    id: str
    gates: list[Gate]


@dataclass(kw_only=True)
class Document:
    title: str
    inputs: list[dict]
    evidence: list[dict]
    receipts: list[dict]
    subtasks: list[Subtask]
    path: Path
    profile_id: str = ""


def _mapping(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise AcddError(f"{label} must be a mapping")
    return value


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise AcddError(f"{label} must be a list of non-empty strings")
    return tuple(value)


def _load_checks(gate_id: str, raw_checks: object) -> tuple[Check, ...]:
    checks, check_ids = [], set()
    for raw_check in raw_checks or []:
        check = _mapping(raw_check, f"check in {gate_id}")
        check_id, kind, outcome = (
            check.get("id"),
            check.get("evidenceKind"),
            check.get("commandOutcome", "success"),
        )
        if (
            not isinstance(check_id, str)
            or not check_id
            or check_id in check_ids
            or kind not in EVIDENCE_KINDS - {"bundle"}
            or outcome not in {"success", "expected-failure"}
        ):
            raise AcddError(f"invalid check in {gate_id}")
        check_ids.add(check_id)
        checks.append(Check(check_id, kind, outcome))
    return tuple(checks)


def load_profile(path: Path) -> Profile:
    data = _mapping(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, "profile")
    if data.get("apiVersion") != "acdd/profile/v1" or data.get("kind") != "profile":
        raise AcddError("profile must declare acdd/profile/v1 and kind: profile")
    gates, gate_ids = [], set()
    for raw in data.get("gates") or []:
        gate = _mapping(raw, "profile gate")
        gate_id, owner = gate.get("id"), gate.get("owner")
        if not isinstance(gate_id, str) or not gate_id or not isinstance(owner, str) or not owner:
            raise AcddError("every gate requires id and owner")
        if gate_id in gate_ids:
            raise AcddError(f"duplicate gate {gate_id!r}")
        gate_ids.add(gate_id)
        checks = _load_checks(gate_id, gate.get("checks"))
        terminals = tuple(gate.get("terminals") or (PASS,))
        if not terminals or any(status not in {PASS, INAPPLICABLE} for status in terminals):
            raise AcddError(f"invalid terminal statuses for {gate_id}")
        reasons = _string_list(
            gate.get("inapplicableReasonCodes"), f"{gate_id} inapplicableReasonCodes"
        )
        if INAPPLICABLE in terminals and not reasons:
            raise AcddError(f"{gate_id} permits inapplicable without reason codes")
        dimensions = _string_list(gate.get("reviewDimensions"), f"{gate_id} reviewDimensions")
        if dimensions and not any(check.evidence_kind == "review" for check in checks):
            raise AcddError(f"{gate_id} declares reviewDimensions without a review check")
        invalidates_on = _string_list(gate.get("invalidatesOn"), f"{gate_id} invalidatesOn")
        gates.append(Gate(gate_id, owner, checks, invalidates_on, terminals, reasons, dimensions))
    return Profile(id=str(data.get("id", "")), gates=gates)


_FM = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_SEC = re.compile(r"## ([\w-]+)\n(.*?)(?=\n## |\Z)", re.DOTALL)
_YAMLBLK = re.compile(r"```yaml\n(.*?)\n```", re.DOTALL)


def load_document(path: Path) -> Document:
    path = path.resolve()
    match = _FM.match(path.read_text(encoding="utf-8"))
    if not match:
        raise AcddError("document must start with YAML frontmatter (---)")
    frontmatter = _mapping(yaml.safe_load(match.group(1)) or {}, "frontmatter")
    sections = {name: content for name, content in _SEC.findall(match.group(2))}
    inputs, subtasks, evidence = [], [], []
    for block in _YAMLBLK.finditer(sections.get("Inputs", "")):
        for entry in _mapping(yaml.safe_load(block.group(1)) or {}, "Inputs").get("paths") or []:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("type"), str)
                or not isinstance(entry.get("path"), str)
                or not entry["path"]
            ):
                raise AcddError(f"invalid Inputs entry: {entry!r}")
            inputs.append(entry)
    for block in _YAMLBLK.finditer(sections.get("Plan", "")):
        for raw in _mapping(yaml.safe_load(block.group(1)) or {}, "Plan").get("subtasks") or []:
            task = _mapping(raw, "subtask")
            for key in ("writes", "reads", "dependsOn"):
                value = task.get(key) or []
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    raise AcddError(f"subtask {key} must be a list of strings")
            supersedes = task.get("supersedes")
            if supersedes is not None and (not isinstance(supersedes, str) or not supersedes):
                raise AcddError("subtask supersedes must be a non-empty string")
            subtasks.append(
                Subtask(
                    id=str(task.get("id", "")),
                    writes=tuple(task.get("writes") or ()),
                    reads=tuple(task.get("reads") or ()),
                    acceptance=str(task.get("acceptance", "")),
                    depends_on=tuple(task.get("dependsOn") or ()),
                    supersedes=supersedes,
                )
            )
    for block in _YAMLBLK.finditer(sections.get("Evidence", "")):
        parsed = yaml.safe_load(block.group(1))
        if isinstance(parsed, dict):
            evidence.append(parsed)
    receipts = []
    for line in sections.get("Receipts", "").splitlines():
        if not line.startswith("|") or "---" in line or line.lower().startswith("| gate"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) > 6:
            receipts.append(
                {
                    "gate": cells[0],
                    "status": "<overflow>",
                    "evidence": "",
                    "fingerprint": "",
                    "recordedAt": "",
                }
            )
        elif len(cells) >= 5:
            receipts.append(
                dict(
                    zip(("gate", "status", "evidence", "fingerprint", "recordedAt", "note"), cells)
                )
            )
    return Document(
        title=str(frontmatter.get("title", "")),
        inputs=inputs,
        evidence=evidence,
        receipts=receipts,
        subtasks=subtasks,
        path=path,
        profile_id=str(frontmatter.get("planning_profile", "")),
    )
