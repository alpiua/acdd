from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "check_markdown_links.py"
SPEC = importlib.util.spec_from_file_location("check_markdown_links", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_repository_markdown_links_are_valid() -> None:
    MODULE.validate_links(ROOT)


def test_missing_local_target_fails(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[missing](missing.md)\n", encoding="utf-8")
    with pytest.raises(MODULE.LinkError, match="missing target"):
        MODULE.validate_links(tmp_path)


def test_whitespace_only_destination_does_not_crash(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[empty](   )\n", encoding="utf-8")
    MODULE.validate_links(tmp_path)


def test_fenced_example_link_is_not_a_document_link(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("```md\n[example](missing.md)\n```\n", encoding="utf-8")
    MODULE.validate_links(tmp_path)
