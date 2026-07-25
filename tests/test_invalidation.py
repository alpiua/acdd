from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


INV = _load("invalidation")

GATES = ("matrix/v1", "architecture/v1", "red/v1", "runtime/v1", "parity/v1", "security/v1", "release/v1", "review/v1", "handoff/v1")


def _policies() -> dict[str, object]:
    return {
        "matrix/v1": INV.InvalidationPolicy("matrix/v1", frozenset({"dependency"})),
        "architecture/v1": INV.InvalidationPolicy("architecture/v1", frozenset({"dependency"})),
        "red/v1": INV.InvalidationPolicy("red/v1", frozenset({"source"}), frozenset({"red"})),
        "runtime/v1": INV.InvalidationPolicy("runtime/v1", frozenset({"source"}), frozenset({"runtime", "docs"})),
        "parity/v1": INV.InvalidationPolicy("parity/v1", frozenset({"source"}), frozenset({"parity"})),
        "security/v1": INV.InvalidationPolicy("security/v1", frozenset({"source"}), frozenset({"security"})),
        "release/v1": INV.InvalidationPolicy("release/v1", frozenset({"source"})),
        "review/v1": INV.InvalidationPolicy("review/v1", frozenset({"source"})),
        "handoff/v1": INV.InvalidationPolicy("handoff/v1", frozenset({"source"})),
    }


def _graph() -> dict[str, tuple[str, ...]]:
    return {
        "matrix/v1": ("architecture/v1", "red/v1", "runtime/v1"),
        "architecture/v1": ("red/v1", "runtime/v1"),
        "red/v1": ("runtime/v1",),
        "runtime/v1": ("parity/v1", "security/v1", "release/v1"),
        "parity/v1": ("release/v1",),
        "security/v1": ("release/v1",),
        "release/v1": ("review/v1",),
        "review/v1": ("handoff/v1",),
        "handoff/v1": (),
    }


def test_graph_validates_and_rejects_unknown_or_cycle() -> None:
    graph = INV.validate_graph(_graph(), GATES)
    assert graph["runtime/v1"] == ("parity/v1", "security/v1", "release/v1")
    with pytest.raises(INV.InvalidationError, match="unknown successors"):
        INV.validate_graph({**_graph(), "runtime/v1": ("unknown/v1",)}, GATES)
    cyclic = dict(_graph())
    cyclic["handoff/v1"] = ("matrix/v1",)
    with pytest.raises(INV.InvalidationError, match="cycle"):
        INV.validate_graph(cyclic, GATES)


def test_class_change_targets_only_matching_gate_plus_successors() -> None:
    policies = _policies()
    changes = (INV.ChangedInput("source", "docs.py", frozenset({"parity"})),)
    roots = INV.impacted_gates(policies, changes)
    assert roots == {"parity/v1", "release/v1", "review/v1", "handoff/v1"}
    rerun = INV.invalidation_plan(
        policies=policies,
        graph=_graph(),
        changes=changes,
        gate_order=GATES,
    )
    assert rerun == ("parity/v1", "release/v1", "review/v1", "handoff/v1")


def test_unknown_class_fails_closed_to_all_gates() -> None:
    policies = _policies()
    roots = INV.impacted_gates(
        policies,
        (INV.ChangedInput("source", "unknown.py", None),),
    )
    assert roots == set(policies)
    rerun = INV.invalidation_plan(
        policies=policies,
        graph=_graph(),
        changes=(INV.ChangedInput("source", "unknown.py", None),),
        gate_order=GATES,
    )
    assert rerun == GATES


def test_unknown_input_type_fails_closed() -> None:
    policies = _policies()
    assert INV.impacted_gates(
        policies, (INV.ChangedInput("new-type", "x", frozenset({"x"})),)
    ) == set(policies)


def test_compute_cli_for_real_contract() -> None:
    import subprocess

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "compute_invalidation.py"),
            "--profile",
            str(ROOT / "profiles/task/v1.yaml"),
            "--receipt-contract",
            str(ROOT / "contracts/receipt/task/v1.yaml"),
            "--change",
            "source:docs.py:parity",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert '"rerunGates"' in completed.stdout
    assert "parity/v1" in completed.stdout
