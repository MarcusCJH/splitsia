"""Shared DynamoDB utilities."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

TABLE_NAME = os.environ.get("SPLITLEH_SESSIONS_TABLE", "splitleh_sessions_dev")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_dynamo(value: Any) -> Any:
    """Recursively convert floats for boto3 DynamoDB writes."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [to_dynamo(v) for v in value]
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items()}
    return value
