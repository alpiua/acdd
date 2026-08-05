#!/usr/bin/env python3
"""Fail-closed Markdown section checks for ACDD gate bindings.

Stops section bodies at the next # or ## heading (### stays inside the body).
Heading titles are matched after strip(). Forbid patterns use re.MULTILINE.

Optional command after ``--`` runs only when all section checks pass (used to
fold matrix validation into executable-proof / expected-failure).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_HEADING = re.compile(r"^(#{1,2})[ \t]+(.+?)\s*$")


def extract_sections(text: str, names: list[str]) -> dict[str, str]:
    wanted = {name.strip() for name in names}
    bodies: dict[str, list[str]] = {}
    present: set[str] = set()
    current: str | None = None
    for line in text.splitlines(keepends=True):
        match = _HEADING.match(line.rstrip("\n"))
        if match:
            title = match.group(2).strip()
            if title in wanted:
                present.add(title)
                bodies.setdefault(title, [])
                current = title
            else:
                current = None
            continue
        if current is not None:
            bodies[current].append(line)
    missing = [name for name in names if name.strip() not in present]
    if missing:
        raise SystemExit(f"markdown_gate_check: missing headings: {missing!r}")
    return {name: "".join(bodies.get(name.strip(), [])) for name in names}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command: list[str] = []
    if "--" in argv:
        idx = argv.index("--")
        command = argv[idx + 1 :]
        argv = argv[:idx]
    parser = argparse.ArgumentParser(description="ACDD markdown gate check")
    parser.add_argument("document")
    parser.add_argument(
        "--require-section",
        action="append",
        default=[],
        dest="require_sections",
        help="Exact # / ## heading that must exist (repeatable)",
    )
    parser.add_argument(
        "--forbid-in-section",
        nargs=2,
        action="append",
        default=[],
        metavar=("SECTION", "PATTERN"),
        dest="forbid_in_section",
        help="Fail if PATTERN matches inside SECTION (re.MULTILINE)",
    )
    args = parser.parse_args(argv)
    path = Path(args.document)
    if not path.is_file():
        print(f"markdown_gate_check: document not found: {path}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")
    needed = list(args.require_sections) + [item[0] for item in args.forbid_in_section]
    sections = extract_sections(text, needed) if needed else {}
    for name in args.require_sections:
        body = sections[name]
        if not body.strip():
            print(f"markdown_gate_check: section {name!r} is empty", file=sys.stderr)
            return 1
    for section, pattern in args.forbid_in_section:
        try:
            compiled = re.compile(pattern, re.MULTILINE)
        except re.error as exc:
            print(f"markdown_gate_check: bad pattern {pattern!r}: {exc}", file=sys.stderr)
            return 2
        if compiled.search(sections[section]):
            print(
                f"markdown_gate_check: forbidden pattern {pattern!r} in section {section!r}",
                file=sys.stderr,
            )
            return 1
    if not command:
        return 0
    try:
        result = subprocess.run(command, check=False)
    except OSError as exc:
        print(f"markdown_gate_check: failed to execute {command[0]!r}: {exc}", file=sys.stderr)
        return 127
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
