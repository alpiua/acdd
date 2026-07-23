from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate_acdd.py"
SPEC = importlib.util.spec_from_file_location("validate_acdd", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


CORE_FILES = (
    "profiles/acdd/v1.yaml",
    "routing/acdd/v1.yaml",
    "contracts/acdd/v1.yaml",
    "contracts/adapter/v1.yaml",
    "contracts/receipt/v1.yaml",
)


def _copy_core(tmp_path: Path) -> Path:
    copied = tmp_path / "plugin"
    for relative in CORE_FILES:
        source = ROOT / relative
        target = copied / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return copied


def test_canonical_profile_is_self_consistent() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "acdd" / "v1.yaml")

    assert core.gate_ids == (
        "matrix/v1",
        "architecture/v1",
        "red/v1",
        "runtime/v1",
        "parity/v1",
        "security/v1",
        "release/v1",
        "review/v1",
        "handoff/v1",
    )
    assert set(core.routing["routes"]) == set(core.gate_ids)
    assert set(core.receipt_contract["terminalStatuses"]) == set(core.gate_ids)


def test_workspace_binding_and_skill_discovery_are_valid() -> None:
    workspace = ROOT.parents[1]
    core = MODULE.validate_binding(
        workspace / ".agents" / "acdd" / "binding.yaml",
        MODULE.load_core(ROOT / "profiles" / "acdd" / "v1.yaml"),
        workspace / ".pi" / "settings.json",
    )

    assert len(core.gate_ids) == 9


def test_closure_order_must_match_gate_order(tmp_path: Path) -> None:
    copied = _copy_core(tmp_path)
    profile_path = copied / "profiles" / "acdd" / "v1.yaml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8").replace(
            "requiredGates: [matrix/v1, architecture/v1, red/v1",
            "requiredGates: [architecture/v1, matrix/v1, red/v1",
        ),
        encoding="utf-8",
    )

    with pytest.raises(MODULE.ContractError, match="preserve profile gate order"):
        MODULE.load_core(profile_path)


def test_terminal_status_list_cannot_be_empty(tmp_path: Path) -> None:
    copied = _copy_core(tmp_path)
    receipt_path = copied / "contracts" / "receipt" / "v1.yaml"
    receipt_path.write_text(
        receipt_path.read_text(encoding="utf-8").replace("matrix/v1: [pass]", "matrix/v1: []"),
        encoding="utf-8",
    )

    with pytest.raises(MODULE.ContractError, match="non-empty-string list"):
        MODULE.load_core(copied / "profiles" / "acdd" / "v1.yaml")


def test_routing_must_point_back_to_selected_profile(tmp_path: Path) -> None:
    copied = _copy_core(tmp_path)
    routing_path = copied / "routing" / "acdd" / "v1.yaml"
    routing_path.write_text(
        routing_path.read_text(encoding="utf-8").replace(
            "profile: ../../profiles/acdd/v1.yaml",
            "profile: ../../contracts/acdd/v1.yaml",
        ),
        encoding="utf-8",
    )

    with pytest.raises(MODULE.ContractError, match="point back"):
        MODULE.load_core(copied / "profiles" / "acdd" / "v1.yaml")


def test_adapter_rejects_fields_outside_contract(tmp_path: Path) -> None:
    core = MODULE.load_core(ROOT / "profiles" / "acdd" / "v1.yaml")
    adapter = tmp_path / "adapter.yaml"
    adapter.write_text(
        """apiVersion: acdd/adapter/v1
kind: adapter
id: task/v1
role: task
provides: [task_read, task_write]
procedure: [Read the task.]
authority: {task: test}
constraints: [Do not invent evidence.]
extra: forbidden
""",
        encoding="utf-8",
    )

    with pytest.raises(MODULE.ContractError, match="undeclared fields"):
        MODULE.load_adapter(adapter, "task", core)


def test_resolve_rejects_absolute_and_authority_escape(tmp_path: Path) -> None:
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    owner = owner_root / "adapter.yaml"
    owner.write_text("owner", encoding="utf-8")
    outside = tmp_path / "outside.yaml"
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(MODULE.ContractError, match="relative path"):
        MODULE._resolve(owner, str(outside), "adapter.reference", allowed_root=owner_root)
    with pytest.raises(MODULE.ContractError, match="escapes authority root"):
        MODULE._resolve(owner, "../outside.yaml", "adapter.reference", allowed_root=owner_root)
