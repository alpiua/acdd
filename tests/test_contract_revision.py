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


DOC = _load("acdd_document")


def test_absent_revision_defaults_to_current() -> None:
    assert (
        DOC._evidence_revision({}, active=True, label="e")
        == DOC.CURRENT_EVIDENCE_REVISION
    )


def test_task_in_delivery_cannot_declare_a_superseded_revision() -> None:
    """The escape hatch must not become a way to dodge a tightened contract."""
    with pytest.raises(DOC.DocumentError, match="must issue revision"):
        DOC._evidence_revision({"contractRevision": 1}, active=True, label="e")


def test_terminal_task_keeps_the_revision_it_was_issued_under() -> None:
    assert DOC._evidence_revision({"contractRevision": 1}, active=False, label="e") == 1


def test_unknown_and_non_integer_revisions_are_rejected() -> None:
    for value in (0, 3, 99):
        with pytest.raises(DOC.DocumentError, match="unsupported revision"):
            DOC._evidence_revision(
                {"contractRevision": value}, active=False, label="e"
            )
    for value in ("2", 2.0, True, None):
        with pytest.raises(DOC.DocumentError, match="expected an integer"):
            DOC._evidence_revision(
                {"contractRevision": value}, active=False, label="e"
            )


def test_revision_2_review_fields_are_required_by_the_current_revision() -> None:
    """Revision 1 exists only to stop retroactive invalidation of closed work.

    If these fields ever stop being required at the current revision, the escape
    hatch would silently become the default and new receipts could omit the
    persisted-contract and discovery axes.
    """
    assert DOC.REVISION_2_REVIEW_FIELDS == {
        "discoveryComplete",
        "persistedContractChange",
        "persistedContractMappings",
    }
    assert DOC.CURRENT_EVIDENCE_REVISION == 2
    assert DOC.SUPPORTED_EVIDENCE_REVISIONS == {1, 2}
