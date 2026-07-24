#!/usr/bin/env python3
"""Validate one acdd/plan/simple/v1 document shape."""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from acdd_document import DocumentError, parse_receipts
from acdd_fingerprint import FingerprintError, markdown_sections, parse_inputs

PROFILE = "acdd/plan/v1"
SHAPE = "acdd/plan/simple/v1"
FIELD_RE = re.compile(r"^- \*\*([^*]+):\*\*(?:\s*(.*))?$", re.MULTILINE)
TASK_HEADING_RE = re.compile(r"^### ([A-Z][A-Z0-9-]+) — (.+)$", re.MULTILINE)
REQUIRED_SECTIONS = (
    "Planning intent",
    "Planning-set manifest",
    "Evidence and contradictions",
    "Architecture coherence",
    "Impact",
    "Plan shape",
    "Roadmap shape",
    "Milestone shape",
    "Tasks",
    "Decomposition",
    "ACDD inputs",
    "ACDD gate evidence",
    "ACDD plan receipts",
    "Blockers",
    "Handoff",
)
REQUIRED_TASK_FIELDS = frozenset(
    {"Status", "Outcome", "Scope", "Prerequisites", "Acceptance", "Evidence"}
)


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class Task:
    identifier: str
    fields: dict[str, str]


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise PlanError(f"{label} must be a string-keyed mapping")
    return {str(key): child for key, child in value.items()}


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{label} must be a non-empty string")
    return value.strip()


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise PlanError(f"{label} must be a string list")
    return [str(item) for item in value]


def parse_document(path: Path) -> tuple[dict[str, object], str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise PlanError("plan must start with YAML frontmatter")
    try:
        raw_frontmatter, body = text[4:].split("\n---\n", 1)
        loaded: object = yaml.safe_load(raw_frontmatter)
    except (ValueError, yaml.YAMLError) as exc:
        raise PlanError("plan frontmatter is invalid or unterminated") from exc
    return _mapping(loaded, "frontmatter"), body, text


def _tasks(section: str) -> tuple[Task, ...]:
    matches = list(TASK_HEADING_RE.finditer(section))
    if not matches:
        raise PlanError("Tasks section requires embedded tasks")
    tasks: list[Task] = []
    for index, match in enumerate(matches):
        identifier = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        body = section[match.end() : end]
        rows = [(name.strip(), value.strip()) for name, value in FIELD_RE.findall(body)]
        names = [name for name, _ in rows]
        if len(names) != len(set(names)):
            raise PlanError(f"{identifier} has duplicate fields")
        fields = dict(rows)
        missing = REQUIRED_TASK_FIELDS - set(fields)
        unknown = set(fields) - REQUIRED_TASK_FIELDS
        if missing or unknown:
            raise PlanError(
                f"{identifier} fields invalid: missing={sorted(missing)} unknown={sorted(unknown)}"
            )
        if fields["Status"] != "todo":
            raise PlanError(f"{identifier} must remain todo during planning")
        for field in ("Outcome", "Scope"):
            _string(fields[field], f"{identifier}.{field}")
        for field in ("Acceptance", "Evidence"):
            if re.search(
                rf"(?m)^- \*\*{field}:\*\*\s*$\n(?:  - .+\n?)+", body
            ) is None:
                raise PlanError(f"{identifier}.{field} requires bullets")
        tasks.append(Task(identifier, fields))
    identifiers = [task.identifier for task in tasks]
    if len(identifiers) != len(set(identifiers)):
        raise PlanError("embedded task IDs must be unique")
    for index, task in enumerate(tasks):
        prerequisites = task.fields["Prerequisites"]
        if prerequisites == "none":
            continue
        refs = [item.strip() for item in prerequisites.split(",") if item.strip()]
        if not refs or any(ref not in identifiers[:index] for ref in refs):
            raise PlanError(
                f"{task.identifier} prerequisites must reference earlier tasks"
            )
    return tuple(tasks)


def validate_plan(path: Path, *, strict: bool) -> None:
    frontmatter, body, text = parse_document(path)
    if frontmatter.get("planning_profile") != PROFILE:
        raise PlanError(f"planning_profile must be {PROFILE}")
    if frontmatter.get("planning_shape") != SHAPE:
        raise PlanError(f"planning_shape must be {SHAPE}")
    if frontmatter.get("planning_mode") not in {"create", "improve"}:
        raise PlanError("planning_mode must be create or improve")
    if frontmatter.get("planning_status") != "planning":
        raise PlanError("simple-plan planning_status must be planning")
    for field in ("title", "area"):
        _string(frontmatter.get(field), field)
    binding = _mapping(frontmatter.get("plan_binding"), "plan_binding")
    if binding.get("owner_kind") != "milestone":
        raise PlanError("simple plan owner_kind must be milestone")
    if binding.get("owner_path") != path.name:
        raise PlanError(f"simple plan owner_path must be {path.name}")
    owner_ref = _string(binding.get("owner_ref"), "plan_binding.owner_ref")
    if _string_list(binding.get("spans_phases"), "plan_binding.spans_phases"):
        raise PlanError("simple plan spans_phases must be empty")
    sections = markdown_sections(body)
    missing = [name for name in REQUIRED_SECTIONS if not sections.get(name, "").strip()]
    if missing:
        raise PlanError(f"missing or empty sections: {missing}")
    milestone = re.search(
        r"(?im)^#{2,6}\s+Milestone:\s*(.+?)\s*$", body
    )
    if milestone is None or milestone.group(1).strip().casefold() != owner_ref.casefold():
        raise PlanError(
            "plan_binding.owner_ref must name the plan's milestone section"
        )
    planning_set = _mapping(frontmatter.get("planning_set"), "planning_set")
    if planning_set.get("primary") != path.name:
        raise PlanError(f"planning_set.primary must be {path.name}")
    for field in ("roadmap", "phases", "milestones", "task_drafts"):
        if _string_list(planning_set.get(field), f"planning_set.{field}"):
            raise PlanError(f"planning_set.{field} must be empty for simple plan")
    _tasks(sections["Tasks"])
    try:
        parse_inputs(text)
        receipts = parse_receipts(text, plan=True)
    except (FingerprintError, DocumentError) as exc:
        raise PlanError(str(exc)) from exc
    gates = tuple(receipt.gate for receipt in receipts)
    expected = (
        "intent/v1",
        "evidence/v1",
        "architecture/v1",
        "plan-shape/v1",
        "roadmap-shape/v1",
        "milestone-shape/v1",
        "decomposition/v1",
        "review/v1",
        "publish/v1",
        "handoff/v1",
    )
    if gates != expected:
        raise PlanError("receipt rows must exactly preserve plan gate order")
    roadmap = next(receipt for receipt in receipts if receipt.gate == "roadmap-shape/v1")
    if roadmap.status == "pass":
        raise PlanError("roadmap-shape/v1 cannot pass for a simple plan")
    first_nonterminal: str | None = None
    for receipt in receipts:
        terminal = {"pass"}
        if receipt.gate == "roadmap-shape/v1":
            terminal.add("inapplicable")
        if receipt.status not in terminal | {"pending", "blocked"}:
            raise PlanError(
                f"{receipt.gate} has invalid receipt status {receipt.status!r}"
            )
        if receipt.status not in terminal:
            first_nonterminal = first_nonterminal or receipt.gate
        elif first_nonterminal is not None:
            raise PlanError(
                f"{receipt.gate} is terminal after non-terminal predecessor {first_nonterminal}"
            )
    blockers = sections["Blockers"].strip()
    statuses = {receipt.gate: receipt.status for receipt in receipts}
    if strict and (
        statuses["publish/v1"] == "pass" or statuses["handoff/v1"] == "pass"
    ):
        if re.fullmatch(r"-\s+none\.?", blockers, re.IGNORECASE) is None:
            raise PlanError("publish and handoff require an empty blocker set")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        validate_plan(args.plan, strict=args.strict)
    except (OSError, PlanError) as exc:
        print(f"SIMPLE PLAN INVALID: {exc}")
        return 1
    print(f"SIMPLE PLAN VALID: {args.plan}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
