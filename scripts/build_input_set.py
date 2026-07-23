#!/usr/bin/env python3
"""Build a reproducible ``acdd/input-set/v1`` manifest from explicit files.

The input spec names every invalidation component and the exact files that
contribute to it. Markdown receipt sections may be excluded by exact heading;
all other task-contract bytes remain fingerprint inputs. Git heads are typed
inputs, not arbitrary shell commands.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from fingerprint_inputs import KINDS, canonical_manifest, fingerprint

SPEC_SCHEMA = "acdd/input-spec/v1"
DETAIL_SCHEMA = "acdd/input-components/v1"
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class InputSpecError(ValueError):
    """Raised when an input spec is incomplete or not reproducible."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _resolve_inside(root: Path, raw_path: object, *, field: str) -> tuple[str, Path]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise InputSpecError(f"{field} must be a non-empty relative path")
    relative = Path(raw_path)
    if relative.is_absolute():
        raise InputSpecError(f"{field} must be relative to --root")
    root_resolved = root.resolve()
    resolved = (root_resolved / relative).resolve()
    if not resolved.is_relative_to(root_resolved):
        raise InputSpecError(f"{field} escapes --root")
    return relative.as_posix(), resolved


def _without_markdown_sections(
    content: bytes,
    section_names: tuple[str, ...],
    *,
    path: str,
) -> bytes:
    if not section_names:
        return content
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputSpecError(f"{path} must be UTF-8 to exclude Markdown sections") from exc

    targets = set(section_names)
    found: set[str] = set()
    excluded_level: int | None = None
    output: list[str] = []
    for line in text.splitlines(keepends=True):
        match = HEADING_RE.match(line.rstrip("\r\n"))
        if match is not None:
            level = len(match.group(1))
            name = match.group(2).strip()
            if excluded_level is not None and level <= excluded_level:
                excluded_level = None
            if name in targets:
                if name in found:
                    raise InputSpecError(f"{path} contains duplicate excluded section {name!r}")
                found.add(name)
                excluded_level = level
                continue
        if excluded_level is None:
            output.append(line)

    missing = targets - found
    if missing:
        raise InputSpecError(f"{path} is missing excluded Markdown sections: {sorted(missing)}")
    return "".join(output).encode("utf-8")



def _normalize_markdown_checkboxes(
    content: bytes,
    section_names: tuple[str, ...],
    *,
    path: str,
) -> bytes:
    """Normalize receipt-state checkboxes while preserving gate contract text."""
    if not section_names:
        return content
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputSpecError(f"{path} must be UTF-8 to normalize Markdown checkboxes") from exc

    targets = set(section_names)
    found: set[str] = set()
    active_level: int | None = None
    output: list[str] = []
    for line in text.splitlines(keepends=True):
        match = HEADING_RE.match(line.rstrip("\r\n"))
        if match is not None:
            level = len(match.group(1))
            name = match.group(2).strip()
            if active_level is not None and level <= active_level:
                active_level = None
            if name in targets:
                if name in found:
                    raise InputSpecError(f"{path} contains duplicate normalized section {name!r}")
                found.add(name)
                active_level = level
        if active_level is not None:
            line = re.sub(r"^(\s*-\s*\[)[ xX](\])", r"\1 \2", line)
        output.append(line)

    missing = targets - found
    if missing:
        raise InputSpecError(f"{path} is missing normalized Markdown sections: {sorted(missing)}")
    return "".join(output).encode("utf-8")


def _file_entry(root: Path, value: object, *, component_index: int, file_index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputSpecError(f"components[{component_index}].files[{file_index}] must be an object")
    allowed = {"path", "excludeMarkdownSections", "normalizeMarkdownCheckboxesInSections"}
    if not set(value).issubset(allowed) or "path" not in value:
        raise InputSpecError(
            f"components[{component_index}].files[{file_index}] supports only path, "
            "excludeMarkdownSections, and normalizeMarkdownCheckboxesInSections"
        )
    relative, path = _resolve_inside(
        root,
        value.get("path"),
        field=f"components[{component_index}].files[{file_index}].path",
    )
    if not path.is_file():
        raise InputSpecError(f"input file does not exist: {relative}")

    def section_names(field: str) -> tuple[str, ...]:
        raw_names = value.get(field, [])
        if not isinstance(raw_names, list) or any(
            not isinstance(item, str) or not item.strip() for item in raw_names
        ):
            raise InputSpecError(f"{relative} {field} must be non-empty strings")
        names = tuple(item.strip() for item in raw_names)
        if len(names) != len(set(names)):
            raise InputSpecError(f"{relative} has duplicate {field} entries")
        return names

    excluded = section_names("excludeMarkdownSections")
    normalized = section_names("normalizeMarkdownCheckboxesInSections")
    if set(excluded) & set(normalized):
        raise InputSpecError(f"{relative} cannot exclude and normalize the same Markdown section")
    content = _without_markdown_sections(path.read_bytes(), excluded, path=relative)
    content = _normalize_markdown_checkboxes(content, normalized, path=relative)
    entry: dict[str, Any] = {"type": "file", "path": relative, "sha256": _sha256(content)}
    if excluded:
        entry["excludedMarkdownSections"] = list(excluded)
    if normalized:
        entry["normalizedMarkdownCheckboxSections"] = list(normalized)
    return entry


def _git_head_entry(root: Path, raw_path: object, *, component_index: int, head_index: int) -> dict[str, str]:
    relative, path = _resolve_inside(
        root,
        raw_path,
        field=f"components[{component_index}].gitHeads[{head_index}]",
    )
    if not path.is_dir():
        raise InputSpecError(f"git-head root does not exist: {relative}")
    try:
        head = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InputSpecError(f"cannot resolve git HEAD for {relative}") from exc
    if re.fullmatch(r"[0-9a-f]{40,64}", head) is None:
        raise InputSpecError(f"invalid git HEAD for {relative}")
    return {"type": "git-head", "path": relative, "value": head}


def build_input_set(value: object, *, root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate one input spec and return its manifest plus component details."""
    if not isinstance(value, dict) or set(value) != {"schema", "components"}:
        raise InputSpecError("spec must contain exactly schema and components")
    if value.get("schema") != SPEC_SCHEMA:
        raise InputSpecError(f"spec schema must be {SPEC_SCHEMA}")
    raw_components = value.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise InputSpecError("components must be a non-empty list")

    components: list[dict[str, Any]] = []
    manifest_inputs: list[dict[str, str]] = []
    identities: set[tuple[str, str]] = set()
    kinds: set[str] = set()
    for component_index, raw_component in enumerate(raw_components):
        if not isinstance(raw_component, dict) or set(raw_component) != {
            "kind",
            "id",
            "files",
            "gitHeads",
        }:
            raise InputSpecError(
                f"components[{component_index}] must contain exactly kind, id, files, and gitHeads"
            )
        kind = raw_component.get("kind")
        identifier = raw_component.get("id")
        if kind not in KINDS:
            raise InputSpecError(f"components[{component_index}] has unknown kind {kind!r}")
        if not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 4096:
            raise InputSpecError(f"components[{component_index}].id must be bounded and non-empty")
        identity = (kind, identifier)
        if identity in identities:
            raise InputSpecError(f"duplicate component identity {kind}:{identifier}")
        identities.add(identity)
        if kind in kinds:
            raise InputSpecError(f"kind {kind!r} must have exactly one component")
        kinds.add(kind)

        raw_files = raw_component.get("files")
        raw_heads = raw_component.get("gitHeads")
        if not isinstance(raw_files, list) or not isinstance(raw_heads, list):
            raise InputSpecError(f"components[{component_index}] files and gitHeads must be lists")
        if not raw_files and not raw_heads:
            raise InputSpecError(f"components[{component_index}] has no reproducible inputs")
        entries = [
            _file_entry(root, item, component_index=component_index, file_index=file_index)
            for file_index, item in enumerate(raw_files)
        ]
        entries.extend(
            _git_head_entry(root, item, component_index=component_index, head_index=head_index)
            for head_index, item in enumerate(raw_heads)
        )
        entry_keys = [(entry["type"], entry["path"]) for entry in entries]
        if len(entry_keys) != len(set(entry_keys)):
            raise InputSpecError(f"components[{component_index}] has duplicate input paths")
        entries.sort(key=lambda item: (item["type"], item["path"]))
        component = {"kind": kind, "id": identifier, "entries": entries}
        component_digest = _sha256(_canonical_bytes(component))
        components.append({**component, "sha256": component_digest})
        manifest_inputs.append({"kind": kind, "id": identifier, "sha256": component_digest})

    if kinds != KINDS:
        raise InputSpecError(f"component kinds mismatch: missing={sorted(KINDS - kinds)}")
    components.sort(key=lambda item: (item["kind"], item["id"]))
    manifest = canonical_manifest({"schema": "acdd/input-set/v1", "inputs": manifest_inputs})
    details = {
        "schema": DETAIL_SCHEMA,
        "inputFingerprint": fingerprint(manifest),
        "components": components,
    }
    return manifest, details


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--details", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = json.loads(args.spec.read_text(encoding="utf-8"))
        manifest, details = build_input_set(value, root=args.root)
        args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        args.details.write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
        print(details["inputFingerprint"])
    except (OSError, json.JSONDecodeError, InputSpecError, ValueError) as exc:
        print(f"ACDD INPUT SPEC INVALID: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
