from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "check_simple_plan", SCRIPTS / "check_simple_plan.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_examples_are_valid() -> None:
    MODULE.validate_plan(ROOT / "PLAN.md", strict=True)
    MODULE.validate_plan(ROOT / "examples" / "simple-plan" / "PLAN.md", strict=True)


def test_wrong_owner_kind_fails(tmp_path: Path) -> None:
    plan = tmp_path / "PLAN.md"
    plan.write_text(
        (ROOT / "PLAN.md")
        .read_text(encoding="utf-8")
        .replace("owner_kind: milestone", "owner_kind: roadmap", 1),
        encoding="utf-8",
    )
    with pytest.raises(MODULE.PlanError, match="owner_kind"):
        MODULE.validate_plan(plan, strict=False)


def test_forward_prerequisite_fails(tmp_path: Path) -> None:
    plan = tmp_path / "PLAN.md"
    plan.write_text(
        (ROOT / "PLAN.md")
        .read_text(encoding="utf-8")
        .replace("- **Prerequisites:** none", "- **Prerequisites:** ACDD-2", 1),
        encoding="utf-8",
    )
    with pytest.raises(MODULE.PlanError, match="earlier tasks"):
        MODULE.validate_plan(plan, strict=False)


def test_persisted_receipt_reference_fails(tmp_path: Path) -> None:
    plan = tmp_path / "PLAN.md"
    plan.write_text(
        (ROOT / "PLAN.md")
        .read_text(encoding="utf-8")
        .replace("| pending | pending | pending |", "| blocked | manifest=x | pending |", 1),
        encoding="utf-8",
    )
    with pytest.raises(MODULE.PlanError, match="legacy manifest"):
        MODULE.validate_plan(plan, strict=True)


def test_planning_requires_todo_tasks(tmp_path: Path) -> None:
    plan = tmp_path / "PLAN.md"
    plan.write_text(
        (ROOT / "PLAN.md")
        .read_text(encoding="utf-8")
        .replace("- **Status:** todo", "- **Status:** in_progress", 1),
        encoding="utf-8",
    )
    with pytest.raises(MODULE.PlanError, match="remain todo"):
        MODULE.validate_plan(plan, strict=True)
