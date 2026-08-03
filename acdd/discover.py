"""Adapter discovery scoped by document path."""

from __future__ import annotations

from pathlib import Path

from .model import AcddError


def adapter_search_roots(workspace: Path, document: Path) -> list[Path]:
    """Return roots whose `.acdd/` directories may supply adapters.

    - `projects/<name>/…` with local `.acdd` → that project only.
    - `projects/<name>/…` without `.acdd` → ACDD unused (error if invoked).
    - Else if `planner/.acdd` or `contextunity/.acdd` exist → those only (platform).
    - Else → whole workspace (single-repo / tests with root `.acdd`).
    """
    workspace = workspace.resolve()
    document = document.resolve()
    try:
        rel = document.relative_to(workspace)
    except ValueError:
        return [workspace]
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "projects":
        project = workspace / "projects" / parts[1]
        if (project / ".acdd").is_dir():
            return [project]
        raise AcddError(
            f"project {parts[1]!r} has no .acdd directory; ACDD is not used for this project"
        )
    platform = [workspace / "planner", workspace / "contextunity"]
    if any((root / ".acdd").is_dir() for root in platform):
        return [root for root in platform if (root / ".acdd").is_dir()]
    return [workspace]


def discover_adapter_paths(workspace: Path, document: Path) -> list[Path]:
    """List adapter YAML paths for the document's scope."""
    found: list[Path] = []
    for root in adapter_search_roots(workspace, document):
        if root == workspace.resolve() and not (
            (workspace / "planner" / ".acdd").is_dir()
            or (workspace / "contextunity" / ".acdd").is_dir()
        ):
            found.extend(_walk_discover(workspace))
            continue
        acdd = root / ".acdd"
        if not acdd.is_dir():
            continue
        for child in sorted(acdd.iterdir()):
            if child.is_symlink():
                continue
            if child.is_file() and child.suffix == ".yaml":
                found.append(child)
    return sorted(set(found))


def _walk_discover(workspace: Path) -> list[Path]:
    found, stack = [], [workspace]
    while stack:
        directory = stack.pop()
        try:
            children = sorted(directory.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and not child.is_symlink():
                if child.name == ".acdd" or (
                    not child.name.startswith(".") and child.name != "node_modules"
                ):
                    stack.append(child)
            elif (
                not child.is_symlink() and child.suffix == ".yaml" and child.parent.name == ".acdd"
            ):
                found.append(child)
    return found
