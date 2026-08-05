"""Freeze-warning helper for agents after contract/v1 pass."""

from __future__ import annotations

from acdd.hints import FREEZE_WARNING, freeze_warning_for_receipts


def test_freeze_warning_only_when_contract_pass() -> None:
    assert freeze_warning_for_receipts([{"gate": "contract/v1", "status": "pending"}]) is None
    assert freeze_warning_for_receipts([{"gate": "build/v1", "status": "pass"}]) is None
    assert (
        freeze_warning_for_receipts([{"gate": "contract/v1", "status": "pass"}]) == FREEZE_WARNING
    )
    assert (
        freeze_warning_for_receipts(
            [
                {"gate": "design/v1", "status": "pass"},
                {"gate": "contract/v1", "status": "pass"},
                {"gate": "build/v1", "status": "pending"},
            ]
        )
        == FREEZE_WARNING
    )
