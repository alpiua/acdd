#!/usr/bin/env python3
"""Validate repository-local Markdown links."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import unquote

LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
IGNORED_PARTS = {".git", "node_modules", "dist", "__pycache__"}


class LinkError(ValueError):
    """Raised when a local Markdown target is invalid."""


def _without_fences(text: str) -> str:
    output: list[str] = []
    active: tuple[str, int] | None = None
    for line in text.splitlines(keepends=True):
        match = FENCE_RE.match(line)
        if match is not None:
            marker = match.group(1)
            candidate = (marker[0], len(marker))
            if active is None:
                active = candidate
            elif candidate[0] == active[0] and candidate[1] >= active[1]:
                active = None
            output.append("\n")
            continue
        output.append(line if active is None else "\n")
    return "".join(output)


def _destination(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def validate_links(root: Path, paths: list[Path] | None = None) -> None:
    authority = root.resolve()
    markdown_paths = paths or [
        path
        for path in authority.rglob("*.md")
        if not any(part in IGNORED_PARTS for part in path.relative_to(authority).parts)
    ]
    violations: list[str] = []
    for source in sorted(path.resolve() for path in markdown_paths):
        if not source.is_relative_to(authority) or not source.is_file():
            violations.append(f"{source}: source is outside repository authority or missing")
            continue
        text = _without_fences(source.read_text(encoding="utf-8"))
        for match in LINK_RE.finditer(text):
            destination = unquote(_destination(match.group(1)))
            if (
                not destination
                or destination.startswith(("#", "http://", "https://", "mailto:"))
                or any(marker in destination for marker in ("<", "{"))
            ):
                continue
            raw_path = destination.split("#", 1)[0]
            if not raw_path:
                continue
            target = (source.parent / raw_path).resolve()
            if not target.is_relative_to(authority):
                violations.append(f"{source.relative_to(authority)}: link escapes repository: {destination}")
            elif not target.exists():
                violations.append(f"{source.relative_to(authority)}: missing target: {destination}")
    if violations:
        raise LinkError("\n".join(violations))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--path", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    try:
        validate_links(args.root, args.path or None)
    except (OSError, UnicodeError, LinkError) as exc:
        print(f"MARKDOWN LINKS INVALID: {exc}")
        return 1
    print(f"MARKDOWN LINKS VALID: {args.root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
