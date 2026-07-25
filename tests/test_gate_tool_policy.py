from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("gate_tool_policy", SCRIPTS / "gate_tool_policy.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_normalize_tool_aliases() -> None:
    assert MODULE.normalize_tool_name("bash_raw_cat") == "bash"
    assert MODULE.normalize_tool_name("lean_ctx_ctx_patch") == "edit"


def test_denied_tool_is_blocked_before_admit() -> None:
    decision = MODULE.evaluate_gate_tool_call(
        tool_name="bash",
        queued_gate="architecture/v1",
        admit=frozenset({"read", "grep"}),
        deny=frozenset({"bash"}),
    )
    assert decision.allowed is False
    assert decision.reason is not None
    assert "ToolDeniedForQueuedGate" in decision.reason


def test_undeclared_tool_is_blocked_when_admit_is_restricted() -> None:
    decision = MODULE.evaluate_gate_tool_call(
        tool_name="edit",
        queued_gate="architecture/v1",
        admit=frozenset({"read", "grep"}),
        deny=frozenset({"bash"}),
    )
    assert decision.allowed is False
    assert "not admitted" in (decision.reason or "")


def test_admitted_tool_passes() -> None:
    decision = MODULE.evaluate_gate_tool_call(
        tool_name="grep",
        queued_gate="architecture/v1",
        admit=frozenset({"read", "grep"}),
        deny=frozenset({"bash"}),
    )
    assert decision.allowed is True
