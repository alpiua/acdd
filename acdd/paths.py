"""Paths to bundled ACDD profiles, skills, and adapters."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

_PROFILE_ALIASES = {
    "task": "profiles/task/v1.yaml",
    "acdd/task/v1": "profiles/task/v1.yaml",
    "plan": "profiles/plan/v1.yaml",
    "acdd/plan/v1": "profiles/plan/v1.yaml",
}


def share_dir() -> Path:
    """Return the filesystem path to the installed share tree."""
    root = files("acdd.share")
    return Path(str(root))


def share_path(*parts: str) -> Path:
    path = share_dir().joinpath(*parts)
    if not path.exists():
        raise FileNotFoundError(f"bundled ACDD resource missing: {'/'.join(parts)}")
    return path


def resolve_profile(spec: str | Path) -> Path:
    """Resolve a profile path or a bundled alias (task, plan, acdd/task/v1, …)."""
    raw = Path(spec)
    if raw.is_file():
        return raw.resolve()
    key = str(spec).strip()
    relative = _PROFILE_ALIASES.get(key)
    if relative is None:
        raise FileNotFoundError(
            f"profile not found: {spec!r} (use a path or alias: {', '.join(sorted(_PROFILE_ALIASES))})"
        )
    return share_path(*relative.split("/"))
