"""Monthly scan budget gate - hard $10/month cap via scan counter."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from shared.dynamodb import now_iso

MAX_SCANS_PER_MONTH = int(os.environ.get("SPLITLEH_MAX_SCANS_PER_MONTH", "400"))
MONTHLY_BUDGET_USD = float(os.environ.get("SPLITLEH_MONTHLY_BUDGET_USD", "10"))


class ScanBudgetExceeded(Exception):
    pass


def _month_key() -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"MONTH#{month}"


def _billing_key() -> dict[str, str]:
    return {"PK": "SYSTEM#billing", "SK": _month_key()}


def get_monthly_billing_row() -> dict:
    table = boto3.resource("dynamodb").Table(os.environ["SPLITLEH_SESSIONS_TABLE"])
    resp = table.get_item(Key=_billing_key())
    return resp.get("Item") or {
        "PK": "SYSTEM#billing",
        "SK": _month_key(),
        "scanCount": 0,
        "scansEnabled": True,
    }


def set_scans_enabled(enabled: bool) -> None:
    table = boto3.resource("dynamodb").Table(os.environ["SPLITLEH_SESSIONS_TABLE"])
    table.update_item(
        Key=_billing_key(),
        UpdateExpression="SET scansEnabled = :e, updatedAt = :t",
        ExpressionAttributeValues={":e": enabled, ":t": now_iso()},
    )


def assert_scan_allowed() -> None:
    row = get_monthly_billing_row()
    if not row.get("scansEnabled", True):
        raise ScanBudgetExceeded(
            "Scanning paused - monthly limit reached. "
            "Try again next month or use SplitLeh Lite (free, on-device OCR)."
        )
    if int(row.get("scanCount", 0)) >= MAX_SCANS_PER_MONTH:
        set_scans_enabled(False)
        raise ScanBudgetExceeded(
            f"Monthly scan limit reached (${MONTHLY_BUDGET_USD:.0f} cap). "
            "Try again next month or use SplitLeh Lite (free, on-device OCR)."
        )


def increment_scan_count() -> None:
    """Atomically increment the scan counter. Raises ScanBudgetExceeded if at limit."""
    table_resource = boto3.resource("dynamodb").Table(os.environ["SPLITLEH_SESSIONS_TABLE"])
    try:
        table_resource.update_item(
            Key=_billing_key(),
            UpdateExpression=(
                "SET scanCount = if_not_exists(scanCount, :zero) + :one, "
                "scansEnabled = if_not_exists(scansEnabled, :true), "
                "updatedAt = :t"
            ),
            ConditionExpression=(
                "(attribute_not_exists(scansEnabled) OR scansEnabled = :true)"
                " AND (attribute_not_exists(scanCount) OR scanCount < :max)"
            ),
            ExpressionAttributeValues={
                ":zero": 0,
                ":one": 1,
                ":true": True,
                ":max": MAX_SCANS_PER_MONTH,
                ":t": now_iso(),
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            set_scans_enabled(False)
            raise ScanBudgetExceeded(
                f"Monthly scan limit reached (${MONTHLY_BUDGET_USD:.0f} cap). "
                "Try again next month or use SplitLeh Lite (free, on-device OCR)."
            ) from exc
        raise
