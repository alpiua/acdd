"""Contract authority — lean anti-cheat hooks (digest, classify, write-set, pre-contract)."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal

from .fingerprint import _digest, subtask_fingerprint
from .model import AcddError, Gate, Subtask

ChangeClass = Literal["additive", "material"]

_REPAIR_ID = re.compile(r"(?i)(repair|fix|amend)")
_PRODUCT_INPUT_TYPES = frozenset(
    {"source", "configuration", "generated", "dependency", "proto", "migration"}
)
_REOPEN_WRITES = Path(".acdd") / "artifacts" / "contract-reopen-writes.json"


def _path_overlap(left: str, right: str) -> bool:
    a, b = left.rstrip("/"), right.rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def active_subtasks(subtasks: Sequence[Subtask]) -> tuple[Subtask, ...]:
    superseded = {task.supersedes for task in subtasks if task.supersedes}
    return tuple(task for task in subtasks if task.id not in superseded)


def write_union(subtasks: Sequence[Subtask]) -> tuple[str, ...]:
    return tuple(sorted({path.rstrip("/") for task in subtasks for path in task.writes}))


def authority_digest(subtasks: Sequence[Subtask]) -> str:
    """Digest of current (non-superseded) Plan subtasks — Contract authority."""
    current = active_subtasks(subtasks)
    return _digest(
        "acdd/contract-authority/1",
        [subtask_fingerprint(task) for task in sorted(current, key=lambda item: item.id)],
    )


def classify_contract_change(
    subtask: Subtask, *, contracted_active: Sequence[Subtask]
) -> ChangeClass:
    """Material = supersede, repair-named id, or write overlap with contracted active."""
    if subtask.supersedes or _REPAIR_ID.search(subtask.id):
        return "material"
    for other in contracted_active:
        if other.id == subtask.id:
            continue
        if any(_path_overlap(left, right) for left in subtask.writes for right in other.writes):
            return "material"
    return "additive"


def gate_requires_authority_verify(gate: Gate | None) -> bool:
    return bool(gate and any(check.evidence_kind == "review" for check in gate.checks))


def review_check_ids(gate: Gate) -> frozenset[str]:
    return frozenset(check.id for check in gate.checks if check.evidence_kind == "review")


def matching_authority_verify(*, digest: str, evidence: Sequence[dict], gate: Gate) -> bool:
    if not gate_requires_authority_verify(gate):
        return True
    checks = review_check_ids(gate)
    return any(
        item.get("gate") == gate.id
        and item.get("kind") == "review"
        and item.get("check") in checks
        and item.get("verdict") == "pass"
        and item.get("authorityDigest") == digest
        for item in evidence
    )


def assert_changed_paths_allowed(changed: Iterable[str], *, allowed_writes: Sequence[str]) -> None:
    """Fail if any changed path escapes the union of active subtask writes."""
    allowed = tuple(write.rstrip("/") for write in allowed_writes)
    for path in changed:
        normalized = path.rstrip("/")
        if not normalized:
            continue
        if any(
            normalized == write
            or normalized.startswith(write + "/")
            or write.startswith(normalized + "/")
            for write in allowed
        ):
            continue
        raise AcddError(
            f"invariant 6 (bounded): changed path {path!r} is outside active subtask writes",
            invariant=6,
        )


def git_dirty_paths(workspace: Path, *, required: bool) -> list[str]:
    """Porcelain dirty paths (tracked + untracked). Empty if no repo and not required."""
    try:
        probe = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except OSError as exc:
        if required:
            raise AcddError(f"git unavailable for write-set check: {exc}") from exc
        return []
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        if required:
            raise AcddError("build write-set requires a git worktree or explicit --changed paths")
        return []
    result = subprocess.run(
        ["git", "-C", str(workspace), "status", "--porcelain", "-uall"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        if required:
            raise AcddError("git status failed; provide --changed or fix the worktree")
        return []
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        rest = line[3:].strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        paths.append(rest.strip('"'))
    return paths


def filter_paths_under_inputs(changed: Iterable[str], *, inputs: Sequence[dict]) -> list[str]:
    roots = tuple(
        entry["path"].rstrip("/")
        for entry in inputs
        if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"]
    )
    matched: list[str] = []
    for path in changed:
        normalized = path.rstrip("/")
        if not normalized:
            continue
        if any(
            normalized == root
            or normalized.startswith(root + "/")
            or root.startswith(normalized + "/")
            for root in roots
        ):
            matched.append(path)
    return matched


def resolve_build_changed_paths(
    workspace: Path,
    changed_paths: Sequence[str] | None,
    *,
    inputs: Sequence[dict],
) -> list[str]:
    raw = list(changed_paths) if changed_paths else git_dirty_paths(workspace, required=True)
    return filter_paths_under_inputs(raw, inputs=inputs)


def assert_precontract_clean(
    *,
    document_path: Path,
    inputs: Sequence[dict],
    receipts: Sequence[dict],
    workspace: Path,
    dirty_paths: Sequence[str] | None = None,
) -> None:
    """Reject dirty product Inputs before contract/v1 PASS (tests allowed for RED proof)."""
    receipt = next((item for item in receipts if item.get("gate") == "contract/v1"), None)
    if receipt is None or receipt.get("status") == "pass":
        return
    dirty = (
        list(dirty_paths) if dirty_paths is not None else git_dirty_paths(workspace, required=False)
    )
    if not dirty:
        return
    roots = tuple(
        entry["path"].rstrip("/")
        for entry in inputs
        if isinstance(entry, dict)
        and entry.get("type") in _PRODUCT_INPUT_TYPES
        and isinstance(entry.get("path"), str)
        and entry["path"]
    )
    doc_rel = document_path.name
    blocked: list[str] = []
    for path in dirty:
        normalized = path.rstrip("/")
        if (
            not normalized
            or normalized == doc_rel
            or normalized.startswith(".acdd/")
            or "/.acdd/" in f"/{normalized}/"
        ):
            continue
        if any(
            normalized == root
            or normalized.startswith(root + "/")
            or root.startswith(normalized + "/")
            for root in roots
        ):
            blocked.append(path)
    if blocked:
        raise AcddError(
            f"invariant 6 (bounded): product paths changed before contract/v1 pass: {blocked}",
            invariant=6,
        )


def reopen_writes_path(workspace: Path) -> Path:
    return workspace.resolve() / _REOPEN_WRITES


def write_reopen_writes_snapshot(workspace: Path, subtasks: Sequence[Subtask]) -> Path:
    path = reopen_writes_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"writes": list(write_union(active_subtasks(subtasks)))}
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path


def assert_writes_not_shrunk(
    prior_writes: Sequence[str],
    new_writes: Sequence[str],
    *,
    allow_scope_reduction: bool,
) -> None:
    if allow_scope_reduction or not prior_writes:
        return
    missing = [
        old for old in prior_writes if not any(_path_overlap(old, new) for new in new_writes)
    ]
    if missing:
        raise AcddError(
            "invariant 6 (bounded): contract change shrank writes "
            f"{missing!r}; pass --allow-scope-reduction after an explicit product decision",
            invariant=6,
        )


def consume_reopen_writes_snapshot(
    workspace: Path,
    new_writes: Sequence[str],
    *,
    allow_scope_reduction: bool,
) -> None:
    path = reopen_writes_path(workspace)
    if not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AcddError("contract reopen writes snapshot is malformed") from exc
    prior = payload.get("writes") if isinstance(payload, dict) else None
    if not isinstance(prior, list) or any(not isinstance(item, str) for item in prior):
        raise AcddError("contract reopen writes snapshot is malformed")
    assert_writes_not_shrunk(prior, new_writes, allow_scope_reduction=allow_scope_reduction)
    path.unlink()
