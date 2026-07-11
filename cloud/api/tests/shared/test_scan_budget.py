import pytest
import time_machine

from shared.scan_budget import ScanBudgetExceeded, assert_scan_allowed, increment_scan_count


@pytest.mark.parametrize(
    "scan_count,scans_enabled,should_raise",
    [
        (0, True, False),
        (399, True, False),
        (400, True, True),
        (10, False, True),
    ],
    ids=["under_cap", "just_under_cap", "at_cap", "disabled"],
)
def test_scan_budget_gate(dynamodb_table, scan_count, scans_enabled, should_raise, monkeypatch):
    monkeypatch.setenv("SPLITLEH_MAX_SCANS_PER_MONTH", "400")
    with time_machine.travel("2026-07-15", tick=False):
        dynamodb_table.put_item(
            Item={
                "PK": "SYSTEM#billing",
                "SK": "MONTH#2026-07",
                "scanCount": scan_count,
                "scansEnabled": scans_enabled,
            }
        )
        if should_raise:
            with pytest.raises(ScanBudgetExceeded):
                assert_scan_allowed()
        else:
            assert_scan_allowed()


def test_increment_scan_count(dynamodb_table, monkeypatch):
    monkeypatch.setenv("SPLITLEH_MAX_SCANS_PER_MONTH", "400")
    with time_machine.travel("2026-07-15", tick=False):
        increment_scan_count()
        row = dynamodb_table.get_item(
            Key={"PK": "SYSTEM#billing", "SK": "MONTH#2026-07"},
        )["Item"]
        assert row["scanCount"] == 1
