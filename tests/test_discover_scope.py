"""Adapter scope resolution tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from acdd.discover import adapter_search_roots, discover_adapter_paths
from acdd.model import AcddError


def test_platform_scope_uses_planner_and_contextunity(tmp_path: Path):
    (tmp_path / "planner" / ".acdd").mkdir(parents=True)
    (tmp_path / "contextunity" / ".acdd").mkdir(parents=True)
    (tmp_path / "projects" / "foo" / ".acdd").mkdir(parents=True)
    (tmp_path / "planner" / ".acdd" / "task.yaml").write_text(
        "apiVersion: acdd/adapter/v1\nid: t\nrole: task\ngates: {}\n", encoding="utf-8"
    )
    (tmp_path / "contextunity" / ".acdd" / "implementation.yaml").write_text(
        "apiVersion: acdd/adapter/v1\nid: i\nrole: implementation\ngates: {}\n",
        encoding="utf-8",
    )
    (tmp_path / "projects" / "foo" / ".acdd" / "task.yaml").write_text(
        "apiVersion: acdd/adapter/v1\nid: pt\nrole: task\ngates: {}\n", encoding="utf-8"
    )
    doc = tmp_path / "planner" / "tasks" / "a.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("x\n", encoding="utf-8")
    roots = adapter_search_roots(tmp_path, doc)
    assert set(roots) == {tmp_path / "planner", tmp_path / "contextunity"}
    paths = discover_adapter_paths(tmp_path, doc)
    assert all("projects" not in str(p) for p in paths)
    assert len(paths) == 2


def test_project_without_acdd_is_unused(tmp_path: Path):
    (tmp_path / "planner" / ".acdd").mkdir(parents=True)
    doc = tmp_path / "projects" / "foo" / "task.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("x\n", encoding="utf-8")
    with pytest.raises(AcddError, match="not used"):
        adapter_search_roots(tmp_path, doc)


def test_project_with_acdd_is_isolated(tmp_path: Path):
    (tmp_path / "planner" / ".acdd").mkdir(parents=True)
    (tmp_path / "planner" / ".acdd" / "task.yaml").write_text(
        "apiVersion: acdd/adapter/v1\nid: t\nrole: task\ngates: {}\n", encoding="utf-8"
    )
    proj = tmp_path / "projects" / "foo"
    (proj / ".acdd").mkdir(parents=True)
    (proj / ".acdd" / "task.yaml").write_text(
        "apiVersion: acdd/adapter/v1\nid: pt\nrole: task\ngates: {}\n", encoding="utf-8"
    )
    doc = proj / "task.md"
    doc.write_text("x\n", encoding="utf-8")
    assert adapter_search_roots(tmp_path, doc) == [proj]
    paths = discover_adapter_paths(tmp_path, doc)
    assert paths == [proj / ".acdd" / "task.yaml"]


def test_single_repo_fallback(tmp_path: Path):
    (tmp_path / ".acdd").mkdir()
    (tmp_path / ".acdd" / "task.yaml").write_text(
        "apiVersion: acdd/adapter/v1\nid: t\nrole: task\ngates: {}\n", encoding="utf-8"
    )
    doc = tmp_path / "task.md"
    doc.write_text("x\n", encoding="utf-8")
    assert adapter_search_roots(tmp_path, doc) == [tmp_path]
    assert discover_adapter_paths(tmp_path, doc) == [tmp_path / ".acdd" / "task.yaml"]
