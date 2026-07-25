from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from structural_invariants import (  # noqa: E402
    StructuralInvariantError,
    check_rules,
    load_contract,
)


def test_example_release_invariants_load() -> None:
    contract_path = ROOT / "examples" / "codebase" / ".acdd" / "invariants" / "release.yaml"
    rules = load_contract(
        contract_path,
        schema_path=ROOT / "contracts" / "structural-invariants" / "v1.yaml",
    )
    assert len(rules) == 1
    assert rules[0].rule == "forbidden"


def test_forbidden_rule_reports_violation(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "bad.py").write_text("subprocess.run(['echo'])", encoding="utf-8")
    rules = load_contract(
        ROOT / "examples" / "codebase" / ".acdd" / "invariants" / "release.yaml",
        schema_path=ROOT / "contracts" / "structural-invariants" / "v1.yaml",
    )
    violations = check_rules(rules, workspace_root=tmp_path)
    assert violations
    assert violations[0].rule_id == "example.no-shell-in-docs"


def test_invalid_contract_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("apiVersion: wrong\nkind: structural-invariants\nrules: []\n", encoding="utf-8")
    with pytest.raises(StructuralInvariantError, match="apiVersion"):
        load_contract(
            bad,
            schema_path=ROOT / "contracts" / "structural-invariants" / "v1.yaml",
        )
