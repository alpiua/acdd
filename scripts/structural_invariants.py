"""Adapter-supplied AST structural invariant checks via ast-grep."""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

RULE_RE = re.compile(r"^(forbidden|required)$")
ID_RE = re.compile(r"^[a-z][a-z0-9._-]+$")


class StructuralInvariantError(ValueError):
    """Invalid structural invariant contract or scan failure."""


@dataclass(frozen=True)
class StructuralRule:
    id: str
    rule: str
    pattern: str
    paths: tuple[str, ...]
    language: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class StructuralViolation:
    rule_id: str
    path: str
    line: int
    column: int
    message: str


def load_schema(path: Path) -> dict[str, object]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise StructuralInvariantError(f"cannot load schema {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StructuralInvariantError("structural invariant schema must be a mapping")
    return value


def validate_contract(contract: dict[str, object], schema: dict[str, object]) -> list[StructuralRule]:
    if contract.get("apiVersion") != "acdd/structural-invariants/v1":
        raise StructuralInvariantError("unsupported structural invariants apiVersion")
    if contract.get("kind") != "structural-invariants":
        raise StructuralInvariantError("kind must be structural-invariants")
    raw_rules = contract.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise StructuralInvariantError("rules must be a non-empty list")
    max_rules = int(schema.get("maxRules", 64))
    if len(raw_rules) > max_rules:
        raise StructuralInvariantError(f"rules exceed maxRules={max_rules}")
    pattern_max = int(schema.get("patternMaxLength", 512))
    required_fields = set(_string_list(schema.get("requiredRuleFields"), "requiredRuleFields"))
    allowed_rules = set(_string_list(schema.get("allowedRules"), "allowedRules"))
    parsed: list[StructuralRule] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_rules):
        if not isinstance(raw, dict):
            raise StructuralInvariantError(f"rules[{index}] must be a mapping")
        keys = set(raw)
        if not required_fields <= keys:
            raise StructuralInvariantError(f"rules[{index}] missing required fields")
        unknown = keys - required_fields - {"language", "message"}
        if unknown:
            raise StructuralInvariantError(f"rules[{index}] has unknown fields {sorted(unknown)}")
        rule_id = _string(raw.get("id"), f"rules[{index}].id")
        if ID_RE.fullmatch(rule_id) is None:
            raise StructuralInvariantError(f"rules[{index}].id is invalid")
        if rule_id in seen:
            raise StructuralInvariantError(f"duplicate rule id {rule_id!r}")
        seen.add(rule_id)
        rule = _string(raw.get("rule"), f"rules[{index}].rule")
        if rule not in allowed_rules or RULE_RE.fullmatch(rule) is None:
            raise StructuralInvariantError(f"rules[{index}].rule must be one of {sorted(allowed_rules)}")
        pattern = _string(raw.get("pattern"), f"rules[{index}].pattern")
        if len(pattern) > pattern_max:
            raise StructuralInvariantError(f"rules[{index}].pattern exceeds {pattern_max} characters")
        paths = tuple(_string_list(raw.get("paths"), f"rules[{index}].paths"))
        language = raw.get("language")
        if language is not None:
            language = _string(language, f"rules[{index}].language")
        message = raw.get("message")
        if message is not None:
            message = _string(message, f"rules[{index}].message")
        parsed.append(
            StructuralRule(
                id=rule_id,
                rule=rule,
                pattern=pattern,
                paths=paths,
                language=language,
                message=message,
            )
        )
    return parsed


def load_contract(path: Path, *, schema_path: Path) -> list[StructuralRule]:
    try:
        contract = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise StructuralInvariantError(f"cannot load structural invariants {path}: {exc}") from exc
    if not isinstance(contract, dict):
        raise StructuralInvariantError("structural invariants must be a mapping")
    return validate_contract(contract, load_schema(schema_path))


def _scan_pattern(*, pattern: str, path: Path, language: str | None) -> list[tuple[str, int, int]]:
    command = ["sg", "run", "--pattern", pattern, "--json=stream"]
    if language:
        command.extend(["--lang", language])
    command.append(str(path))
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise StructuralInvariantError(f"ast-grep unavailable: {exc}") from exc
    if completed.returncode not in {0, 1}:
        detail = completed.stderr.strip() or completed.stdout.strip() or "ast-grep failed"
        raise StructuralInvariantError(detail)
    matches: list[tuple[str, int, int]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            continue
        file_path = payload.get("file") or payload.get("path")
        start = payload.get("start") or payload.get("range", {}).get("start", {})
        if not isinstance(file_path, str):
            continue
        line_no = int(start.get("line", 0)) + 1 if isinstance(start, dict) else 0
        column = int(start.get("column", 0)) + 1 if isinstance(start, dict) else 0
        matches.append((file_path, line_no, column))
    return matches


def _expand_paths(workspace_root: Path, patterns: tuple[str, ...]) -> list[Path]:
    result: list[Path] = []
    for pattern in patterns:
        if any(char in pattern for char in "*?[]"):
            result.extend(sorted(workspace_root.glob(pattern)))
        else:
            result.append(workspace_root / pattern)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in result:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def check_rules(
    rules: list[StructuralRule] | tuple[StructuralRule, ...],
    *,
    workspace_root: Path,
) -> list[StructuralViolation]:
    violations: list[StructuralViolation] = []
    for rule in rules:
        targets = [path for path in _expand_paths(workspace_root, rule.paths) if path.exists()]
        if not targets:
            if rule.rule == "required":
                violations.append(
                    StructuralViolation(
                        rule_id=rule.id,
                        path=str(workspace_root),
                        line=0,
                        column=0,
                        message=rule.message or f"required pattern not found under {rule.paths}",
                    )
                )
            continue
        matches: list[tuple[str, int, int]] = []
        for target in targets:
            if target.is_dir():
                for child in sorted(target.rglob("*")):
                    if child.is_file():
                        matches.extend(
                            _scan_pattern(pattern=rule.pattern, path=child, language=rule.language)
                        )
            else:
                matches.extend(
                    _scan_pattern(pattern=rule.pattern, path=target, language=rule.language)
                )
        if rule.rule == "forbidden" and matches:
            for file_path, line_no, column in matches:
                violations.append(
                    StructuralViolation(
                        rule_id=rule.id,
                        path=file_path,
                        line=line_no,
                        column=column,
                        message=rule.message or f"forbidden pattern matched in {file_path}",
                    )
                )
        if rule.rule == "required" and not matches:
            violations.append(
                StructuralViolation(
                    rule_id=rule.id,
                    path=str(targets[0]),
                    line=0,
                    column=0,
                    message=rule.message or f"required pattern not found under {rule.paths}",
                )
            )
    return violations


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StructuralInvariantError(f"{label}: expected non-empty string")
    return value.strip()


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise StructuralInvariantError(f"{label}: expected a non-empty string list")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise StructuralInvariantError(f"{label}[{index}]: expected non-empty string")
        result.append(item.strip())
    return result
