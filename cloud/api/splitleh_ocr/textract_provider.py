"""Textract AnalyzeExpense provider."""

from __future__ import annotations

from typing import Any

import boto3


def analyze_expense(bucket: str, key: str) -> list[dict[str, Any]]:
    client = boto3.client("textract")
    resp = client.analyze_expense(
        Document={"S3Object": {"Bucket": bucket, "Name": key}},
    )
    return resp.get("ExpenseDocuments", [])
