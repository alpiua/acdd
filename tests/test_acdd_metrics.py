from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "acdd_metrics.py"
SPEC = importlib.util.spec_from_file_location("acdd_metrics", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _task(status: str, runtime_status: str, start: str, end: str) -> str:
    return f"""---
status: {status}
---

## ACDD receipts

| Gate | Status | Evidence | Input fingerprint | Recorded at |
|---|---|---|---|---|
| matrix/v1 | pass | evidence=matrix | sha256:{'1' * 64} | {start} |
| runtime/v1 | {runtime_status} | evidence=runtime | sha256:{'2' * 64} | {end} |
"""


def test_summarize_current_statuses_and_completed_span(tmp_path: Path) -> None:
    (tmp_path / "done.md").write_text(
        _task("done", "pass", "2026-07-25T10:00:00Z", "2026-07-25T10:05:00Z"),
        encoding="utf-8",
    )
    (tmp_path / "blocked.md").write_text(
        _task(
            "in_progress",
            "blocked",
            "2026-07-25T11:00:00Z",
            "2026-07-25T11:01:00Z",
        ),
        encoding="utf-8",
    )
    (tmp_path / "notes.md").write_text(
        "# Reference\n\nstatus: reference\n\n## ACDD receipts\n",
        encoding="utf-8",
    )

    metrics = MODULE.summarize([tmp_path])

    assert metrics["documents"] == 2
    assert metrics["receiptRows"] == 4
    assert metrics["taskStatuses"] == {"done": 1, "in_progress": 1}
    assert metrics["gateStatuses"]["runtime/v1"] == {"blocked": 1, "pass": 1}
    assert metrics["blockedGates"] == {"runtime/v1": 1}
    assert metrics["completedReceiptSpans"] == 1
    assert metrics["averageCompletedReceiptSpanSeconds"] == 300.0
