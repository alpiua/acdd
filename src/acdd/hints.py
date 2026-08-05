"""Agent-facing CLI hints (non-fatal; do not change exit codes)."""

from __future__ import annotations

from collections.abc import Sequence

CONTRACT_GATE = "contract/v1"

FREEZE_WARNING = """\
ACDD FREEZE — contract/v1 is pass
FORBIDDEN: edit frozen Plan parts, Task execution contract section, adapter promptAppend.
ONLY: acdd contract-subtask (addition|supersedes) → re-run contract-verify → matching authorityDigest.
NEVER: acdd reopen; silent rewrite of parts / receipt / hashed freeze surface.
`acdd validate` repeats this while Contract stays pass."""


def contract_is_pass(receipts: Sequence[dict]) -> bool:
    return any(
        isinstance(item, dict)
        and item.get("gate") == CONTRACT_GATE
        and item.get("status") == "pass"
        for item in receipts
    )


def freeze_warning_for_receipts(receipts: Sequence[dict]) -> str | None:
    return FREEZE_WARNING if contract_is_pass(receipts) else None


def print_freeze_warning(receipts: Sequence[dict], *, file=None) -> None:
    text = freeze_warning_for_receipts(receipts)
    if text:
        print(text, file=file)
