"""Validate persisted contract propagation and bounded discovery closure."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acdd_fingerprint import FingerprintError, markdown_sections, yaml_documents

SECTION = "Persisted contract propagation"
API_VERSION = "acdd/persisted-contracts/v2"
KIND = "persisted-contracts"
ALLOWED_CHANGES = {"unchanged", "new", "changed", "removed"}
ALLOWED_IMPACTS = {
    "none",
    "compatible-expansion",
    "restriction",
    "reinterpretation",
    "removal",
}
ALLOWED_ROLES = {
    "producer",
    "writer",
    "schema",
    "migration",
    "reader",
    "public-type",
    "proof",
    "unrelated",
}
REQUIRED_ROLES = {"producer", "writer", "schema", "reader", "public-type", "proof"}
ALLOWED_STRATEGIES = {"not-required", "backfill", "compatibility-bridge", "preflight-reject"}
TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".json",
    ".kt",
    ".md",
    ".php",
    ".proto",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
SKIP_DIR_NAMES = {
    ".git",
    ".pi",
    ".mypy_cache",
    ".pi-subagents",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "vendor",
}
CODE_ROOT_NAMES = frozenset({"services", "packages", "extensions", "tests"})
MAX_DISCOVERY_FILES = 20_000
MAX_DISCOVERY_MATCHES = 256
MAX_FILE_BYTES = 2 * 1024 * 1024


class ValueDomainError(ValueError):
    """The persisted-contract contract is incomplete or stale."""


@dataclass(frozen=True)
class ValueDomain:
    id: str
    change: str
    compatibility_impact: str
    paths: frozenset[str]
    proof_ids: frozenset[str]


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueDomainError(f"{label}: expected a string-keyed mapping")
    return dict(value)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueDomainError(f"{label}: expected a non-empty string")
    return value.strip()


def _strings(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueDomainError(f"{label}: expected a string list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueDomainError(f"{label}: expected a string list")
    result = [str(item).strip() for item in value]
    if len(result) != len(set(result)):
        raise ValueDomainError(f"{label}: duplicate values are not allowed")
    return result


def _contract_value(value: object, label: str, *, allow_none: bool = False) -> object:
    if value is None:
        if allow_none:
            return None
        raise ValueDomainError(f"{label}: persisted contract cannot be null")
    if isinstance(value, str):
        if not value.strip():
            raise ValueDomainError(f"{label}: string contract cannot be empty")
        return value
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, list):
        if not value:
            raise ValueDomainError(f"{label}: list contract cannot be empty")
        return [
            _contract_value(item, f"{label}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict) and value and all(
        isinstance(key, str) and key.strip() for key in value
    ):
        return {
            key: _contract_value(item, f"{label}.{key}")
            for key, item in value.items()
        }
    raise ValueDomainError(f"{label}: expected a bounded YAML scalar, list, or mapping")


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing or unknown:
        raise ValueDomainError(
            f"{label}: missing={sorted(missing)} unknown={sorted(unknown)}"
        )


def _relative_file(workspace_root: Path, raw: str, label: str) -> Path:
    root = workspace_root.resolve()
    target = (root / raw).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueDomainError(f"{label}: missing or escaping file {raw!r}")
    return target


def _relative_root(workspace_root: Path, raw: str, label: str) -> Path:
    root = workspace_root.resolve()
    target = (root / raw).resolve()
    if not target.is_relative_to(root) or not target.is_dir():
        raise ValueDomainError(f"{label}: missing or escaping root {raw!r}")
    return target


def _discover(
    workspace_root: Path,
    *,
    roots: list[str],
    terms: list[str],
    label: str,
) -> set[str]:
    workspace = workspace_root.resolve()
    found: set[str] = set()
    inspected_paths: set[Path] = set()
    encoded_terms = tuple(term.encode("utf-8") for term in terms)
    for root_name in roots:
        root = _relative_root(workspace, root_name, f"{label}.roots")
        scan_roots = (
            (root,)
            if root.name in CODE_ROOT_NAMES
            else tuple(
                root / name
                for name in sorted(CODE_ROOT_NAMES)
                if (root / name).is_dir()
            )
        )
        for scan_root in scan_roots:
            for path in sorted(scan_root.rglob("*")):
                relative_to_workspace = path.relative_to(workspace)
                if any(part in SKIP_DIR_NAMES for part in relative_to_workspace.parts):
                    continue
                if (
                    path in inspected_paths
                    or not path.is_file()
                    or path.suffix.lower() not in TEXT_SUFFIXES
                ):
                    continue
                inspected_paths.add(path)
                if len(inspected_paths) > MAX_DISCOVERY_FILES:
                    raise ValueDomainError(
                        f"{label}: discovery exceeds {MAX_DISCOVERY_FILES} bounded text files; refine roots"
                    )
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
                data = path.read_bytes()
                if any(term in data for term in encoded_terms):
                    found.add(path.relative_to(workspace).as_posix())
                    if len(found) > MAX_DISCOVERY_MATCHES:
                        raise ValueDomainError(
                            f"{label}: discovery exceeds {MAX_DISCOVERY_MATCHES} matching files; use more precise terms or roots"
                        )
    return found


def parse_value_domains(
    text: str,
    *,
    workspace_root: Path,
    declared_paths: frozenset[str],
    semantic_ids: frozenset[str],
) -> tuple[ValueDomain, ...]:
    """Parse and validate the optional persisted-contract matrix."""
    sections = markdown_sections(text)
    if SECTION not in sections:
        return ()
    try:
        documents = yaml_documents(sections[SECTION], SECTION)
    except FingerprintError as exc:
        raise ValueDomainError(str(exc)) from exc
    if len(documents) != 1:
        raise ValueDomainError(f"{SECTION}: expected one YAML document")
    root = _mapping(documents[0], SECTION)
    _exact_keys(root, {"apiVersion", "kind", "domains"}, SECTION)
    if root.get("apiVersion") != API_VERSION or root.get("kind") != KIND:
        raise ValueDomainError(f"{SECTION}: unsupported contract")
    raw_domains = root.get("domains")
    if not isinstance(raw_domains, list) or not raw_domains:
        raise ValueDomainError(f"{SECTION}: domains must be non-empty")

    domains: list[ValueDomain] = []
    seen_ids: set[str] = set()
    for index, raw_domain in enumerate(raw_domains):
        label = f"{SECTION}.domains[{index}]"
        domain = _mapping(raw_domain, label)
        _exact_keys(
            domain,
            {
                "id",
                "field",
                "contractKind",
                "change",
                "compatibilityImpact",
                "beforeContract",
                "afterContract",
                "discovery",
                "compatibility",
                "proofIds",
            },
            label,
        )
        domain_id = _string(domain.get("id"), f"{label}.id")
        if domain_id in seen_ids:
            raise ValueDomainError(f"{label}: duplicate id {domain_id!r}")
        seen_ids.add(domain_id)
        _string(domain.get("field"), f"{label}.field")
        _string(domain.get("contractKind"), f"{label}.contractKind")
        change = _string(domain.get("change"), f"{label}.change")
        if change not in ALLOWED_CHANGES:
            raise ValueDomainError(f"{label}.change: unsupported value {change!r}")
        compatibility_impact = _string(
            domain.get("compatibilityImpact"), f"{label}.compatibilityImpact"
        )
        if compatibility_impact not in ALLOWED_IMPACTS:
            raise ValueDomainError(
                f"{label}.compatibilityImpact: unsupported value {compatibility_impact!r}"
            )
        before = _contract_value(
            domain.get("beforeContract"),
            f"{label}.beforeContract",
            allow_none=change == "new",
        )
        after = _contract_value(
            domain.get("afterContract"),
            f"{label}.afterContract",
            allow_none=change == "removed",
        )
        expected_impacts = {
            "unchanged": {"none"},
            "new": {"none"},
            "changed": {"compatible-expansion", "restriction", "reinterpretation"},
            "removed": {"removal"},
        }
        if compatibility_impact not in expected_impacts[change]:
            raise ValueDomainError(
                f"{label}: change {change!r} contradicts compatibility impact {compatibility_impact!r}"
            )
        if change == "new" and before is not None:
            raise ValueDomainError(f"{label}: new contract requires null beforeContract")
        if change == "removed" and after is not None:
            raise ValueDomainError(f"{label}: removed contract requires null afterContract")
        if change == "unchanged" and before != after:
            raise ValueDomainError(f"{label}: unchanged contract must preserve its definition")
        if change == "changed" and before == after:
            raise ValueDomainError(f"{label}: changed contract must alter its definition")

        discovery = _mapping(domain.get("discovery"), f"{label}.discovery")
        _exact_keys(discovery, {"roots", "terms", "files"}, f"{label}.discovery")
        roots = _strings(discovery.get("roots"), f"{label}.discovery.roots")
        terms = _strings(discovery.get("terms"), f"{label}.discovery.terms")
        raw_files = discovery.get("files")
        if not isinstance(raw_files, list) or not raw_files:
            raise ValueDomainError(f"{label}.discovery.files: expected a non-empty list")
        dispositions: dict[str, set[str]] = {}
        for file_index, raw_file in enumerate(raw_files):
            file_label = f"{label}.discovery.files[{file_index}]"
            item = _mapping(raw_file, file_label)
            required = {"path", "roles"}
            optional = {"rationale"}
            missing = required - set(item)
            unknown = set(item) - required - optional
            if missing or unknown:
                raise ValueDomainError(
                    f"{file_label}: missing={sorted(missing)} unknown={sorted(unknown)}"
                )
            path = _string(item.get("path"), f"{file_label}.path")
            _relative_file(workspace_root, path, file_label)
            if path in dispositions:
                raise ValueDomainError(f"{file_label}: duplicate path {path!r}")
            roles = set(_strings(item.get("roles"), f"{file_label}.roles"))
            if not roles <= ALLOWED_ROLES:
                raise ValueDomainError(
                    f"{file_label}: unknown roles {sorted(roles - ALLOWED_ROLES)}"
                )
            if "unrelated" in roles:
                if len(roles) != 1 or "rationale" not in item:
                    raise ValueDomainError(
                        f"{file_label}: unrelated requires one explicit rationale"
                    )
                _string(item.get("rationale"), f"{file_label}.rationale")
            elif "rationale" in item:
                raise ValueDomainError(
                    f"{file_label}: rationale is allowed only for unrelated disposition"
                )
            dispositions[path] = roles

        discovered = _discover(workspace_root, roots=roots, terms=terms, label=label)
        declared_discovery = set(dispositions)
        if discovered != declared_discovery:
            raise ValueDomainError(
                f"{label}: discovery closure mismatch "
                f"missing={sorted(discovered - declared_discovery)} "
                f"stale={sorted(declared_discovery - discovered)}"
            )
        owned_paths = {
            path for path, roles in dispositions.items() if roles != {"unrelated"}
        }
        undeclared = owned_paths - declared_paths
        if undeclared:
            raise ValueDomainError(
                f"{label}: persisted-contract paths are absent from ACDD inputs {sorted(undeclared)}"
            )
        covered_roles = {
            role
            for roles in dispositions.values()
            for role in roles
            if role != "unrelated"
        }
        missing_roles = REQUIRED_ROLES - covered_roles
        if missing_roles:
            raise ValueDomainError(
                f"{label}: propagation chain misses roles {sorted(missing_roles)}"
            )

        compatibility = _mapping(domain.get("compatibility"), f"{label}.compatibility")
        _exact_keys(
            compatibility,
            {"strategy", "compatibilityPaths", "proofIds"},
            f"{label}.compatibility",
        )
        strategy = _string(
            compatibility.get("strategy"), f"{label}.compatibility.strategy"
        )
        if strategy not in ALLOWED_STRATEGIES:
            raise ValueDomainError(
                f"{label}.compatibility.strategy: unsupported value {strategy!r}"
            )
        compatibility_paths = set(
            _strings(
                compatibility.get("compatibilityPaths"),
                f"{label}.compatibility.compatibilityPaths",
                allow_empty=strategy == "not-required",
            )
        )
        compatibility_proofs = set(
            _strings(
                compatibility.get("proofIds"),
                f"{label}.compatibility.proofIds",
                allow_empty=strategy == "not-required",
            )
        )
        breaking_impacts = {"restriction", "reinterpretation", "removal"}
        if compatibility_impact in breaking_impacts:
            if strategy == "not-required":
                raise ValueDomainError(
                    f"{label}: compatibility-breaking persisted contract change requires backfill, compatibility bridge, or preflight rejection"
                )
            if not compatibility_paths or not compatibility_proofs:
                raise ValueDomainError(
                    f"{label}: compatibility-breaking persisted contract change requires compatibility paths and executable proofs"
                )
            if not compatibility_paths <= owned_paths:
                raise ValueDomainError(
                    f"{label}: compatibility paths lack an owned pipeline disposition"
                )
        proof_ids = set(_strings(domain.get("proofIds"), f"{label}.proofIds"))
        all_proofs = proof_ids | compatibility_proofs
        missing_proofs = all_proofs - semantic_ids
        if missing_proofs:
            raise ValueDomainError(
                f"{label}: proof IDs are absent from the semantic task {sorted(missing_proofs)}"
            )
        domains.append(
            ValueDomain(
                id=domain_id,
                change=change,
                compatibility_impact=compatibility_impact,
                paths=frozenset(owned_paths | compatibility_paths),
                proof_ids=frozenset(all_proofs),
            )
        )
    return tuple(domains)


__all__ = [
    "SECTION",
    "ValueDomain",
    "ValueDomainError",
    "parse_value_domains",
]
