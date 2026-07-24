"""Typed, in-memory ACDD input and semantic fingerprinting."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
INPUT_TYPES = frozenset(
    {
        "source",
        "test",
        "configuration",
        "generated",
        "dependency",
        "environment",
        "accepted-review-findings",
    }
)
SYSTEM_INPUT_TYPES = frozenset(
    {"bound-document", "profile", "receipt-contract", "adapter"}
)
TASK_SEMANTIC_SECTIONS = (
    "Objective",
    "Coverage analysis (ACDD)",
    "Architecture coherence & blast radius (G0)",
    "Task execution contract (G0 output)",
    "G0 completeness barrier",
    "G0 decision registry",
    "Execution gates",
    "Runtime path (required)",
    "Surfaces",
    "Config surface",
    "Out of scope",
    "Handoff / blockers",
)
TASK_REQUIRED_SECTIONS = (
    "Objective",
    "Coverage analysis (ACDD)",
    "Architecture coherence & blast radius (G0)",
    "Task execution contract (G0 output)",
    "G0 decision registry",
    "Execution gates",
    "Surfaces",
    "Config surface",
    "Out of scope",
    "Handoff / blockers",
)
TASK_OPTIONAL_SEMANTIC_SECTIONS = (
    "Persisted contract propagation",
    "Recovered RED baseline",
    "RED definitions",
    "Caller and alternate-path matrix",
    "Runtime path",
)


class FingerprintError(ValueError):
    """The bound document or its declared inputs are invalid."""


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str


@dataclass(frozen=True)
class DeclaredInput:
    type: str
    path: str


@dataclass(frozen=True)
class SnapshotEntry:
    type: str
    path: str
    sha256: str


@dataclass(frozen=True)
class FingerprintResult:
    sha256: str
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True)
class SemanticFingerprint:
    sha256: str
    ids: tuple[str, ...]
    red_proof_sha256: str


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def markdown_sections(text: str) -> dict[str, str]:
    """Return level-two Markdown sections without interpreting fenced headings."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    fenced = False
    fence_marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        fence = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence:
            marker = fence.group(1)
            if not fenced:
                fenced, fence_marker = True, marker[0]
            elif marker[0] == fence_marker:
                fenced, fence_marker = False, ""
        if not fenced:
            heading = re.match(r"^##\s+(.+?)\s*$", line)
            if heading:
                current = heading.group(1).strip()
                if current in sections:
                    raise FingerprintError(
                        f"duplicate Markdown section {current!r}"
                    )
                sections[current] = []
                continue
        if current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def yaml_documents(section: str, label: str) -> tuple[object, ...]:
    blocks = re.findall(
        r"(?ms)^```ya?ml\s*\n(.*?)^```\s*$", section
    )
    if not blocks:
        raise FingerprintError(f"{label}: expected a fenced YAML block")
    documents: list[object] = []
    try:
        for block in blocks:
            documents.extend(
                value for value in yaml.safe_load_all(block) if value is not None
            )
    except yaml.YAMLError as exc:
        raise FingerprintError(f"{label}: invalid YAML: {exc}") from exc
    return tuple(documents)


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise FingerprintError(f"{label}: expected a string-keyed mapping")
    return {str(key): child for key, child in value.items()}


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FingerprintError(f"{label}: expected a non-empty string")
    return value.strip()


def _string_list(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise FingerprintError(f"{label}: expected a string list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise FingerprintError(f"{label}: expected a string list")
    result = [str(item).strip() for item in value]
    if len(result) != len(set(result)):
        raise FingerprintError(f"{label}: duplicate values are not allowed")
    return result


def parse_inputs(text: str) -> tuple[DeclaredInput, ...]:
    sections = markdown_sections(text)
    if "ACDD inputs" not in sections:
        raise FingerprintError("missing ## ACDD inputs")
    documents = yaml_documents(sections["ACDD inputs"], "ACDD inputs")
    if len(documents) != 1:
        raise FingerprintError("ACDD inputs: expected exactly one YAML document")
    root = _mapping(documents[0], "ACDD inputs")
    if root.get("apiVersion") != "acdd/inputs/v1" or root.get("kind") != "inputs":
        raise FingerprintError(
            "ACDD inputs: expected apiVersion=acdd/inputs/v1 kind=inputs"
        )
    raw_paths = root.get("paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        raise FingerprintError("ACDD inputs.paths: expected a non-empty list")
    inputs: list[DeclaredInput] = []
    identities: set[tuple[str, str]] = set()
    canonical_paths: set[str] = set()
    for index, raw in enumerate(raw_paths):
        item = _mapping(raw, f"ACDD inputs.paths[{index}]")
        if set(item) != {"type", "path"}:
            raise FingerprintError(
                f"ACDD inputs.paths[{index}]: only type and path are allowed"
            )
        input_type = _string(item.get("type"), f"ACDD inputs.paths[{index}].type")
        path = _string(item.get("path"), f"ACDD inputs.paths[{index}].path")
        if input_type not in INPUT_TYPES:
            raise FingerprintError(
                f"ACDD inputs.paths[{index}]: unknown type {input_type!r}"
            )
        if Path(path).is_absolute():
            raise FingerprintError(
                f"ACDD inputs.paths[{index}]: path must be workspace-relative"
            )
        normalized = Path(path).as_posix()
        identity = (input_type, normalized)
        if identity in identities or normalized in canonical_paths:
            raise FingerprintError(f"duplicate input path {normalized!r}")
        identities.add(identity)
        canonical_paths.add(normalized)
        inputs.append(DeclaredInput(input_type, normalized))
    return tuple(inputs)


def _adapter_authorities(
    adapters: tuple[Path, ...], workspace_root: Path
) -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {}
    for adapter_path in adapters:
        try:
            value: object = yaml.safe_load(adapter_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise FingerprintError(f"cannot load adapter {adapter_path}: {exc}") from exc
        adapter = _mapping(value, str(adapter_path))
        raw_authorities = adapter.get("inputAuthorities")
        if raw_authorities is None and adapter.get("role") == "audit":
            continue
        if not isinstance(raw_authorities, dict):
            raise FingerprintError(
                f"{adapter_path}: inputAuthorities must declare bound-document/input paths"
            )
        authorities = _mapping(raw_authorities, f"{adapter_path}:inputAuthorities")
        for input_type, raw_patterns in authorities.items():
            if input_type not in INPUT_TYPES | {"bound-document"}:
                raise FingerprintError(
                    f"{adapter_path}: unknown input authority {input_type!r}"
                )
            patterns = _string_list(
                raw_patterns, f"{adapter_path}:inputAuthorities.{input_type}"
            )
            for pattern in patterns:
                if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
                    raise FingerprintError(
                        f"{adapter_path}: input authority must be workspace-relative: {pattern}"
                    )
                result.setdefault(input_type, []).append(pattern)
    if not workspace_root.is_dir():
        raise FingerprintError(f"workspace root does not exist: {workspace_root}")
    return {key: tuple(values) for key, values in result.items()}


def _resolve_declared(
    declared: DeclaredInput, workspace_root: Path, authorities: dict[str, tuple[str, ...]]
) -> Path:
    root = workspace_root.resolve()
    path = (root / declared.path).resolve()
    if not path.is_relative_to(root):
        raise FingerprintError(f"input path escapes workspace root: {declared.path}")
    if not path.is_file():
        raise FingerprintError(f"missing declared input: {declared.path}")
    patterns = authorities.get(declared.type, ())
    if not patterns or not any(
        fnmatch.fnmatch(declared.path, pattern) for pattern in patterns
    ):
        raise FingerprintError(
            f"undeclared adapter authority for {declared.type} path {declared.path!r}"
        )
    return path


def _relative(path: Path, workspace_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(workspace_root.resolve()).as_posix()
    except ValueError:
        return f"external:{resolved.as_posix()}"


def _plan_contract_bytes(text: str) -> bytes:
    sections = markdown_sections(text)
    excluded = {
        "ACDD gate evidence",
        "ACDD plan receipts",
        "ACDD receipts",
        "ACDD contract changes",
        "ACDD contract fingerprint",
    }
    body = "\n".join(
        f"## {name}\n{value}"
        for name, value in sections.items()
        if name not in excluded
    )
    body = re.sub(r"(?m)^(\s*-\s*)\[[ xX]\]", r"\1[ ]", body)
    return re.sub(r"[ \t]+$", "", body, flags=re.MULTILINE).strip().encode("utf-8")


def fingerprint_inputs(
    *,
    document: Path,
    profile: Path,
    receipt_contract: Path,
    adapters: tuple[Path, ...],
    workspace_root: Path,
    include_types: frozenset[str],
) -> FingerprintResult:
    """Build a canonical snapshot in memory and return only its digest/diagnostics."""
    root = workspace_root.resolve()
    document_path = document.resolve()
    if not document_path.is_relative_to(root) or not document_path.is_file():
        raise FingerprintError("bound document is missing or escapes workspace root")
    authorities = _adapter_authorities(adapters, root)
    document_relative = _relative(document_path, root)
    if not any(
        fnmatch.fnmatch(document_relative, pattern)
        for pattern in authorities.get("bound-document", ())
    ):
        raise FingerprintError(
            f"bound document {document_relative!r} is outside adapter authority"
        )
    text = document_path.read_text(encoding="utf-8")
    declared = parse_inputs(text)
    entries: list[SnapshotEntry] = []
    for item in declared:
        path = _resolve_declared(item, root, authorities)
        if item.type in include_types:
            entries.append(
                SnapshotEntry(item.type, item.path, _sha256(path.read_bytes()))
            )
    if "/profiles/task/" in profile.resolve().as_posix():
        document_digest = semantic_task_fingerprint(text).sha256
    else:
        document_digest = _sha256(_plan_contract_bytes(text))
    entries.append(
        SnapshotEntry("bound-document", document_relative, document_digest)
    )
    system_paths = (
        ("profile", profile.resolve()),
        ("receipt-contract", receipt_contract.resolve()),
        *(("adapter", path.resolve()) for path in adapters),
    )
    for input_type, path in system_paths:
        if not path.is_file():
            raise FingerprintError(f"missing automatic input: {path}")
        entries.append(
            SnapshotEntry(input_type, _relative(path, root), _sha256(path.read_bytes()))
        )
    canonical_entries = [
        {"type": entry.type, "path": entry.path, "sha256": entry.sha256}
        for entry in sorted(entries, key=lambda item: (item.type, item.path))
    ]
    return FingerprintResult(
        sha256=_sha256(_canonical(canonical_entries)),
        diagnostics=(),
    )


def semantic_task_fingerprint(text: str) -> SemanticFingerprint:
    sections = markdown_sections(text)
    missing = [name for name in TASK_REQUIRED_SECTIONS if name not in sections]
    if missing:
        raise FingerprintError(
            f"semantic task contract missing sections: {', '.join(missing)}"
        )
    normalized: dict[str, str] = {}
    selected = [
        name
        for name in TASK_SEMANTIC_SECTIONS + TASK_OPTIONAL_SEMANTIC_SECTIONS
        if name in sections
    ]
    if not any(name in selected for name in ("Runtime path (required)", "Runtime path")):
        raise FingerprintError("semantic task contract missing runtime path")
    for name in selected:
        body = sections[name]
        if name == "Execution gates":
            body = re.sub(r"(?m)^(\s*-\s*)\[[ xX]\]", r"\1[ ]", body)
        normalized[name] = re.sub(r"[ \t]+$", "", body, flags=re.MULTILINE).strip()
    semantic_text = "\n".join(
        f"## {name}\n{normalized[name]}" for name in selected
    )
    ids = sorted(
        set(
            re.findall(
                r"\b(?:scope|contract|authority|lifecycle|decision|proof|red)"
                r"[._-][A-Za-z0-9._-]+\b",
                semantic_text,
            )
        )
    )
    red_lines = "\n".join(
        line
        for line in semantic_text.splitlines()
        if re.search(r"\b(?:scope|red|proof)[._-][A-Za-z0-9._-]+\b", line)
        or "Red + compositional test" in line
    )
    return SemanticFingerprint(
        sha256=_sha256(semantic_text.encode("utf-8")),
        ids=tuple(ids),
        red_proof_sha256=_sha256(red_lines.encode("utf-8")),
    )
