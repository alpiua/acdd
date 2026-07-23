#!/usr/bin/env python3
"""Compute a deterministic ACDD input-set fingerprint from a JSON manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "acdd/input-set/v1"
KINDS = frozenset(
    {
        "task",
        "source",
        "tests",
        "configuration",
        "generated-inputs",
        "dependencies",
        "environment",
        "accepted-review-findings",
    }
)
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ManifestError(ValueError):
    """Raised when an input manifest cannot support a current receipt."""


def canonical_manifest(value: object) -> dict[str, Any]:
    """Validate and sort one ``acdd/input-set/v1`` manifest."""
    if not isinstance(value, dict) or set(value) != {"schema", "inputs"}:
        raise ManifestError("manifest must contain exactly schema and inputs")
    if value.get("schema") != SCHEMA:
        raise ManifestError(f"manifest schema must be {SCHEMA}")
    raw_inputs = value.get("inputs")
    if not isinstance(raw_inputs, list) or not raw_inputs:
        raise ManifestError("manifest inputs must be a non-empty list")
    normalized: list[dict[str, str]] = []
    identities: set[tuple[str, str]] = set()
    for index, item in enumerate(raw_inputs):
        if not isinstance(item, dict) or set(item) != {"kind", "id", "sha256"}:
            raise ManifestError(f"inputs[{index}] must contain exactly kind, id, and sha256")
        kind = item.get("kind")
        identifier = item.get("id")
        digest = item.get("sha256")
        if kind not in KINDS:
            raise ManifestError(f"inputs[{index}] has unknown kind {kind!r}")
        if not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 4096:
            raise ManifestError(f"inputs[{index}].id must be a bounded non-empty string")
        if not isinstance(digest, str) or DIGEST_RE.fullmatch(digest) is None:
            raise ManifestError(f"inputs[{index}].sha256 must be sha256:<64 lowercase hex>")
        identity = (kind, identifier)
        if identity in identities:
            raise ManifestError(f"duplicate input identity {kind}:{identifier}")
        identities.add(identity)
        normalized.append({"kind": kind, "id": identifier, "sha256": digest})
    present = {item["kind"] for item in normalized}
    if present != KINDS:
        raise ManifestError(f"manifest kinds mismatch: missing={sorted(KINDS - present)} extra={sorted(present - KINDS)}")
    normalized.sort(key=lambda item: (item["kind"], item["id"]))
    return {"schema": SCHEMA, "inputs": normalized}


def fingerprint(value: object) -> str:
    """Return ``sha256:<hex>`` for the canonical manifest bytes."""
    encoded = json.dumps(
        canonical_manifest(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        value = json.loads(args.manifest.read_text(encoding="utf-8"))
        print(fingerprint(value))
    except (OSError, json.JSONDecodeError, ManifestError) as exc:
        print(f"ACDD INPUT MANIFEST INVALID: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
