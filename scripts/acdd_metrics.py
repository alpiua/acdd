#!/usr/bin/env python3
"""Summarize current ACDD receipt status from selected Markdown paths."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

RECEIPTS_RE = re.compile(
    r"(?ms)^## ACDD receipts\s*$\n(.*?)(?=^## |\Z)"
)
STATUS_RE = re.compile(r"(?m)^status:\s*['\"]?([^'\"\s]+)")
COMPLETED_STATUSES = {"done", "complete", "completed"}


class MetricsError(ValueError):
    pass


def _documents(paths: list[Path]) -> list[Path]:
    documents: set[Path] = set()
    for path in paths:
        if path.is_file():
            documents.add(path)
        elif path.is_dir():
            documents.update(path.rglob("*.md"))
        else:
            raise MetricsError(f"missing path: {path}")
    return sorted(documents)


def _timestamp(raw: str, path: Path, gate: str) -> datetime | None:
    if raw == "pending":
        return None
    try:
        return datetime.strptime(raw.strip("'\""), "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise MetricsError(f"{path}: invalid recordedAt for {gate}: {raw}") from exc


def _task_status(text: str) -> str | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    match = STATUS_RE.search(text[4:end])
    return match.group(1).lower() if match else None


def summarize(paths: list[Path]) -> dict[str, object]:
    task_statuses: Counter[str] = Counter()
    gate_statuses: dict[str, Counter[str]] = defaultdict(Counter)
    blocked_gates: Counter[str] = Counter()
    completed_spans: list[float] = []
    matched_documents = 0
    receipt_rows = 0

    for path in _documents(paths):
        text = path.read_text(encoding="utf-8")
        section = RECEIPTS_RE.search(text)
        task_status = _task_status(text)
        if section is None or task_status is None:
            continue
        matched_documents += 1
        task_statuses[task_status] += 1
        timestamps: list[datetime] = []
        for line in section.group(1).splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [
                cell.strip().strip("`")
                for cell in line.strip().strip("|").split("|")
            ]
            if (
                len(cells) < 5
                or cells[0].lower() == "gate"
                or set(cells[0]) <= {"-", ":"}
            ):
                continue
            gate, receipt_status, _, _, recorded_at = cells[:5]
            receipt_rows += 1
            gate_statuses[gate][receipt_status] += 1
            if receipt_status == "blocked":
                blocked_gates[gate] += 1
            timestamp = _timestamp(recorded_at, path, gate)
            if timestamp is not None:
                timestamps.append(timestamp)
        if task_status in COMPLETED_STATUSES and len(timestamps) >= 2:
            completed_spans.append((max(timestamps) - min(timestamps)).total_seconds())

    return {
        "documents": matched_documents,
        "receiptRows": receipt_rows,
        "taskStatuses": dict(sorted(task_statuses.items())),
        "gateStatuses": {
            gate: dict(sorted(statuses.items()))
            for gate, statuses in sorted(gate_statuses.items())
        },
        "blockedGates": dict(sorted(blocked_gates.items())),
        "completedReceiptSpans": len(completed_spans),
        "averageCompletedReceiptSpanSeconds": (
            sum(completed_spans) / len(completed_spans) if completed_spans else None
        ),
    }


def _render(metrics: dict[str, object]) -> str:
    average = metrics["averageCompletedReceiptSpanSeconds"]
    lines = [
        f"documents: {metrics['documents']}",
        f"receipt rows: {metrics['receiptRows']}",
        "average completed receipt span: "
        + (f"{average:.1f}s" if isinstance(average, float) else "n/a"),
        "blocked gates:",
    ]
    blocked = metrics["blockedGates"]
    assert isinstance(blocked, dict)
    lines.extend(
        [f"  {gate}: {count}" for gate, count in blocked.items()]
        or ["  none"]
    )
    lines.append("gate statuses:")
    gate_statuses = metrics["gateStatuses"]
    assert isinstance(gate_statuses, dict)
    for gate, statuses in gate_statuses.items():
        assert isinstance(statuses, dict)
        values = ", ".join(f"{status}={count}" for status, count in statuses.items())
        lines.append(f"  {gate}: {values}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        metrics = summarize(args.paths)
    except (MetricsError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(metrics, indent=2, sort_keys=True) if args.as_json else _render(metrics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
