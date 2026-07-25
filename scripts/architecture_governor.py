"""G0 architecture admission: baseline, unchanged-FAIL ban, attempt cap."""
from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from acdd_fingerprint import (
    DIGEST_RE,
    FingerprintError,
    markdown_sections,
    parse_inputs,
    yaml_documents,
)

DEFAULT_MAX_MATERIAL_ATTEMPTS = 3
IMPLEMENTATION_INPUT_TYPES = frozenset(
    {"source", "test", "configuration", "generated"}
)
UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class ArchitectureGovernorError(ValueError):
    """Architecture admission or retry governance failed."""


@dataclass(frozen=True)
class CandidatePath:
    path: str
    sha256: str


@dataclass(frozen=True)
class ArchitectureAttempt:
    input_fingerprint: str
    verdict: str
    recorded_at: str


@dataclass(frozen=True)
class ArchitectureAdmission:
    max_material_attempts: int
    candidate_set: tuple[CandidatePath, ...]
    attempts: tuple[ArchitectureAttempt, ...]


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _fingerprint(value: object, label: str) -> str:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        raise ArchitectureGovernorError(f"{label}: expected sha256:<64 lowercase hex>")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArchitectureGovernorError(f"{label}: expected a non-empty string")
    return value.strip()


def find_git_root(start: Path) -> Path | None:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for path in (current, *current.parents):
        if (path / ".git").exists():
            return path
    return None


def collect_dirty_paths(workspace_root: Path) -> tuple[str, ...]:
    """Return workspace-relative dirty paths, or () when Git is unavailable."""
    root = workspace_root.resolve()
    git_root = find_git_root(root)
    if git_root is None:
        return ()
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=str(git_root),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        # Pytest tmp dirs and broken worktrees should not hard-fail admission;
        # treat "not a git repository" as no observable dirty set.
        if "not a git repository" in detail.lower():
            return ()
        raise ArchitectureGovernorError(f"git status failed: {detail}")
    dirty: list[str] = []
    for line in completed.stdout.splitlines():
        if len(line) < 4:
            continue
        entry = line[3:].strip()
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1].strip()
        if not entry:
            continue
        abs_path = (git_root / entry).resolve()
        try:
            relative = abs_path.relative_to(root).as_posix()
        except ValueError:
            continue
        dirty.append(relative)
    return tuple(dict.fromkeys(dirty))


def declared_implementation_paths(text: str) -> frozenset[str]:
    try:
        return frozenset(
            item.path
            for item in parse_inputs(text)
            if item.type in IMPLEMENTATION_INPUT_TYPES
        )
    except FingerprintError as exc:
        raise ArchitectureGovernorError(str(exc)) from exc


def parse_architecture_admission(text: str) -> ArchitectureAdmission:
    """Parse optional ## ACDD architecture admission; defaults if absent."""
    sections = markdown_sections(text)
    if "ACDD architecture admission" not in sections:
        return ArchitectureAdmission(
            max_material_attempts=DEFAULT_MAX_MATERIAL_ATTEMPTS,
            candidate_set=(),
            attempts=(),
        )
    try:
        documents = yaml_documents(
            sections["ACDD architecture admission"],
            "ACDD architecture admission",
        )
    except FingerprintError as exc:
        raise ArchitectureGovernorError(str(exc)) from exc
    if len(documents) != 1:
        raise ArchitectureGovernorError(
            "ACDD architecture admission: expected exactly one YAML document"
        )
    raw = documents[0]
    if not isinstance(raw, dict):
        raise ArchitectureGovernorError(
            "ACDD architecture admission: expected a mapping"
        )
    if raw.get("apiVersion") != "acdd/architecture-admission/v1":
        raise ArchitectureGovernorError(
            "ACDD architecture admission: unsupported apiVersion"
        )
    if raw.get("kind") != "architecture-admission":
        raise ArchitectureGovernorError(
            "ACDD architecture admission: kind must be architecture-admission"
        )
    max_attempts = raw.get("maxMaterialAttempts", DEFAULT_MAX_MATERIAL_ATTEMPTS)
    if not isinstance(max_attempts, int) or max_attempts < 1:
        raise ArchitectureGovernorError(
            "maxMaterialAttempts must be a positive integer"
        )
    candidate_set: list[CandidatePath] = []
    raw_candidates = raw.get("candidateSet", [])
    if raw_candidates is None:
        raw_candidates = []
    if not isinstance(raw_candidates, list):
        raise ArchitectureGovernorError("candidateSet must be a list")
    seen_paths: set[str] = set()
    for index, item in enumerate(raw_candidates):
        if not isinstance(item, dict):
            raise ArchitectureGovernorError(
                f"candidateSet[{index}]: expected a mapping"
            )
        path = _string(item.get("path"), f"candidateSet[{index}].path")
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise ArchitectureGovernorError(
                f"candidateSet[{index}].path must be workspace-relative: {path}"
            )
        normalized = Path(path).as_posix()
        if normalized in seen_paths:
            raise ArchitectureGovernorError(
                f"candidateSet: duplicate path {normalized}"
            )
        seen_paths.add(normalized)
        digest = _fingerprint(
            item.get("sha256"), f"candidateSet[{index}].sha256"
        )
        candidate_set.append(CandidatePath(normalized, digest))
    attempts: list[ArchitectureAttempt] = []
    raw_attempts = raw.get("attempts", [])
    if raw_attempts is None:
        raw_attempts = []
    if not isinstance(raw_attempts, list):
        raise ArchitectureGovernorError("attempts must be a list")
    for index, item in enumerate(raw_attempts):
        if not isinstance(item, dict):
            raise ArchitectureGovernorError(f"attempts[{index}]: expected a mapping")
        fingerprint = _fingerprint(
            item.get("inputFingerprint"),
            f"attempts[{index}].inputFingerprint",
        )
        verdict = _string(item.get("verdict"), f"attempts[{index}].verdict").upper()
        if verdict not in {"PASS", "FAIL", "BLOCKED"}:
            raise ArchitectureGovernorError(
                f"attempts[{index}].verdict must be PASS, FAIL, or BLOCKED"
            )
        recorded_at = _string(
            item.get("recordedAt"), f"attempts[{index}].recordedAt"
        )
        if UTC_RE.fullmatch(recorded_at) is None:
            raise ArchitectureGovernorError(
                f"attempts[{index}].recordedAt: expected UTC YYYY-MM-DDTHH:MM:SSZ"
            )
        attempts.append(
            ArchitectureAttempt(fingerprint, verdict, recorded_at)
        )
    return ArchitectureAdmission(
        max_material_attempts=max_attempts,
        candidate_set=tuple(candidate_set),
        attempts=tuple(attempts),
    )


def validate_candidate_locks(
    candidate_set: tuple[CandidatePath, ...],
    *,
    workspace_root: Path,
) -> None:
    root = workspace_root.resolve()
    for item in candidate_set:
        path = (root / item.path).resolve()
        if not path.is_relative_to(root):
            raise ArchitectureGovernorError(
                f"candidate path escapes workspace: {item.path}"
            )
        if not path.is_file():
            raise ArchitectureGovernorError(
                f"candidate path missing: {item.path}"
            )
        current = _sha256_file(path)
        if current != item.sha256:
            raise ArchitectureGovernorError(
                f"candidate path stale lock: {item.path}"
            )


def validate_baseline(
    *,
    dirty_paths: tuple[str, ...] | list[str],
    declared_implementation_paths: frozenset[str] | set[str],
    candidate_set: tuple[CandidatePath, ...] | list[CandidatePath],
) -> None:
    """Require clean declared inputs, or an explicit candidate-set covering them.

    Unrelated dirty paths outside declared implementation inputs are ignored so
    preserved worktree noise does not block G0. Candidate bytes are admitted only
    as candidate-only pre-existing surfaces, never as verified implementation.
    """
    candidate_paths = {item.path for item in candidate_set}
    dirty = {Path(path).as_posix() for path in dirty_paths}
    declared = {Path(path).as_posix() for path in declared_implementation_paths}
    blocking = sorted(
        path
        for path in dirty
        if path in declared and path not in candidate_paths
    )
    if blocking:
        raise ArchitectureGovernorError(
            "dirty declared implementation inputs require clean baseline or "
            f"candidate-set coverage: {blocking}"
        )
    # Candidate paths should themselves be dirty or at least locked; lock check
    # is separate. Extra candidate entries for non-declared files are allowed
    # (pre-existing dirty that will enter the slice).


def material_fail_fingerprints(
    attempts: tuple[ArchitectureAttempt, ...] | list[ArchitectureAttempt],
) -> tuple[str, ...]:
    ordered: list[str] = []
    for attempt in attempts:
        if attempt.verdict != "FAIL":
            continue
        if attempt.input_fingerprint not in ordered:
            ordered.append(attempt.input_fingerprint)
    return tuple(ordered)


def validate_retry_admission(
    attempts: tuple[ArchitectureAttempt, ...] | list[ArchitectureAttempt],
    *,
    next_fingerprint: str,
    max_material_attempts: int = DEFAULT_MAX_MATERIAL_ATTEMPTS,
) -> None:
    """Refuse unchanged FAIL reruns and cap material FAIL fingerprints."""
    next_fp = _fingerprint(next_fingerprint, "nextFingerprint")
    if max_material_attempts < 1:
        raise ArchitectureGovernorError("maxMaterialAttempts must be >= 1")
    fails = material_fail_fingerprints(attempts)
    if attempts:
        last = attempts[-1]
        if last.verdict == "FAIL" and last.input_fingerprint == next_fp:
            raise ArchitectureGovernorError(
                "cannot rerun an unchanged FAIL fingerprint"
            )
    # New material fingerprint beyond the cap is blocked.
    if next_fp not in fails and len(fails) >= max_material_attempts:
        raise ArchitectureGovernorError(
            f"architecture attempt cap exceeded ({max_material_attempts} "
            "material FAIL fingerprints); record blocked and stop thrash"
        )


def validate_architecture_admission(
    *,
    text: str,
    workspace_root: Path,
    architecture_fingerprint: str,
    dirty_paths: tuple[str, ...] | None = None,
) -> ArchitectureAdmission:
    """Full G0 admission check for an architecture fingerprint under review."""
    admission = parse_architecture_admission(text)
    declared = declared_implementation_paths(text)
    dirty = (
        tuple(dirty_paths)
        if dirty_paths is not None
        else collect_dirty_paths(workspace_root)
    )
    validate_candidate_locks(admission.candidate_set, workspace_root=workspace_root)
    validate_baseline(
        dirty_paths=dirty,
        declared_implementation_paths=declared,
        candidate_set=admission.candidate_set,
    )
    validate_retry_admission(
        admission.attempts,
        next_fingerprint=architecture_fingerprint,
        max_material_attempts=admission.max_material_attempts,
    )
    return admission


def may_launch_architecture(
    *,
    text: str,
    workspace_root: Path,
    next_fingerprint: str,
    dirty_paths: tuple[str, ...] | None = None,
) -> tuple[bool, str]:
    """Return (ok, reason) for pre-launch checks without raising."""
    try:
        validate_architecture_admission(
            text=text,
            workspace_root=workspace_root,
            architecture_fingerprint=next_fingerprint,
            dirty_paths=dirty_paths,
        )
    except ArchitectureGovernorError as exc:
        return False, str(exc)
    return True, "admitted"
