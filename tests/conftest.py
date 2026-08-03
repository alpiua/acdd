"""Conftest: make `acdd` importable and expose ROOT fixture."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def ROOT():
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def core(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "profile.yaml").write_text(
        """\
apiVersion: acdd/profile/v1
kind: profile
id: test/v1
gates:
  - id: build/v1
    owner: implementation
    checks:
      - {id: runtime-and-integration, evidenceKind: command, commandOutcome: success}
    invalidatesOn: [source]
    terminals: [pass, inapplicable]
    inapplicableReasonCodes: [build.no-runnable-source]
""",
        encoding="utf-8",
    )
    (tmp_path / "adapter.yaml").write_text(
        """\
apiVersion: acdd/adapter/v1
id: test-implementation
role: implementation
artifactDir: artifacts
gates:
  build/v1:
    checks:
      runtime-and-integration:
        cwd: .
        argv: [python3, -c, "print('green')"]
""",
        encoding="utf-8",
    )
    (tmp_path / "task.md").write_text(
        """\
---
title: T
planning_profile: test/v1
---
## Plan
```yaml
subtasks: []
```
## Inputs
```yaml
paths:
  - {type: source, path: src/app.py}
```
## Evidence

## Receipts
| gate | status | evidence | fingerprint | recordedAt |
| --- | --- | --- | --- | --- |
| build/v1 | pending | pending | pending | pending |
""",
        encoding="utf-8",
    )
    return tmp_path / "task.md", tmp_path / "profile.yaml", tmp_path / "adapter.yaml"
