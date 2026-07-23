from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "fingerprint_inputs.py"
SPEC = importlib.util.spec_from_file_location("fingerprint_inputs", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _manifest() -> dict[str, object]:
    return {
        "schema": "acdd/input-set/v1",
        "inputs": [
            {"kind": kind, "id": f"{kind}:fixture", "sha256": "sha256:" + character * 64}
            for kind, character in zip(sorted(MODULE.KINDS), "01234567", strict=True)
        ],
    }


def test_fingerprint_is_stable_across_input_order() -> None:
    manifest = _manifest()
    reversed_manifest = {"schema": manifest["schema"], "inputs": list(reversed(manifest["inputs"]))}

    assert MODULE.fingerprint(manifest) == MODULE.fingerprint(reversed_manifest)
    assert MODULE.DIGEST_RE.fullmatch(MODULE.fingerprint(manifest))


def test_fingerprint_requires_every_invalidation_kind() -> None:
    manifest = _manifest()
    manifest["inputs"] = manifest["inputs"][:-1]

    with pytest.raises(MODULE.ManifestError, match="kinds mismatch"):
        MODULE.fingerprint(manifest)


def test_fingerprint_rejects_duplicate_identity() -> None:
    manifest = _manifest()
    manifest["inputs"].append(dict(manifest["inputs"][0]))

    with pytest.raises(MODULE.ManifestError, match="duplicate input identity"):
        MODULE.fingerprint(manifest)
