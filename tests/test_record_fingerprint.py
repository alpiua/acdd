from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RECORD = _load("record_fingerprint")
FINGERPRINT = _load("acdd_fingerprint")

TASK = """\
## Objective

Deliver scope.example.

## Coverage analysis (ACDD)

contract.producer covers scope.example.

## Architecture coherence & blast radius (G0)

authority.tenant is unchanged.

## Task execution contract (G0 output)

lifecycle.read is bound.

## G0 decision registry

- [x] `decision.example` — resolved.

## Runtime path (required)

Caller reaches the production path.

## Execution gates

- [x] Red + compositional test for scope.example

## Surfaces

CLI only.

## Config surface

None.

## Out of scope

Nothing.

## ACDD contract fingerprint

```yaml
apiVersion: acdd/semantic-fingerprint/v1
kind: semantic-fingerprint
sha256: sha256:{stale}
ids: [stale.identifier]
redProofFingerprint: sha256:{stale}
redEvidenceIds: [example.red.one]
```

## Handoff / blockers

None.
""".format(stale="0" * 64)


def test_generated_block_matches_the_derived_fingerprint() -> None:
    expected = FINGERPRINT.semantic_task_fingerprint(TASK)
    block = RECORD._render(TASK, ("example.red.one",))
    assert f"sha256: {expected.sha256}" in block
    assert f"redProofFingerprint: {expected.red_proof_sha256}" in block
    assert f"ids: [{', '.join(expected.ids)}]" in block
    assert "redEvidenceIds: [example.red.one]" in block


def test_write_replaces_only_the_fingerprint_section(tmp_path: Path) -> None:
    document = tmp_path / "task.md"
    document.write_text(TASK, encoding="utf-8")

    argv = sys.argv
    sys.argv = ["record_fingerprint.py", "--document", str(document), "--write"]
    try:
        assert RECORD.main() == 0
    finally:
        sys.argv = argv

    updated = document.read_text(encoding="utf-8")
    expected = FINGERPRINT.semantic_task_fingerprint(TASK)
    assert f"sha256: {expected.sha256}" in updated
    assert "sha256:" + "0" * 64 not in updated
    # Authored red evidence ids are preserved; every other section is untouched.
    assert "redEvidenceIds: [example.red.one]" in updated
    for heading in ("## Objective", "## Execution gates", "## Handoff / blockers"):
        assert heading in updated
    assert updated.count("## ACDD contract fingerprint") == 1
    # A second run is a no-op, so the block is stable under repeated refresh.
    assert FINGERPRINT.semantic_task_fingerprint(updated).sha256 == expected.sha256


def test_missing_section_fails_closed(tmp_path: Path) -> None:
    document = tmp_path / "task.md"
    document.write_text(TASK.replace("## Out of scope\n\nNothing.\n\n", ""), encoding="utf-8")

    argv = sys.argv
    sys.argv = ["record_fingerprint.py", "--document", str(document), "--write"]
    try:
        assert RECORD.main() == 1
    finally:
        sys.argv = argv

    assert "sha256:" + "0" * 64 in document.read_text(encoding="utf-8")
