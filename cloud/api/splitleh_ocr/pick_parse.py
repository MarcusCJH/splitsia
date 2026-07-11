"""Score and pick the best ParseResult among Textract parse strategies."""

from __future__ import annotations

import re
from typing import Any

from splitleh.types import ParseResult

FALLBACK_CONFIDENCE_THRESHOLD = 0.75
MIN_ACCEPTABLE_SCORE = 12.0

_FIELD_CODE_NAMES = frozenset(
    {
        "AMOUNT_PAID",
        "SERVICE_CHARGE",
        "OTHER",
        "SUBTOTAL",
        "TAX",
        "TOTAL",
        "ITEM",
        "AMOUNT_DUE",
        "VENDOR_NAME",
    }
)

_PRICE_IN_LABEL = re.compile(r"\$\s*\d")


def average_confidence(documents: list[dict[str, Any]]) -> float:
    scores: list[float] = []
    for doc in documents:
        for group in doc.get("LineItemGroups", []):
            for item in group.get("LineItems", []):
                for field in item.get("LineItemExpenseFields", []):
                    conf = field.get("ValueDetection", {}).get("Confidence")
                    if conf is not None:
                        scores.append(float(conf) / 100.0)
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def line_item_count(documents: list[dict[str, Any]]) -> int:
    count = 0
    for doc in documents:
        for group in doc.get("LineItemGroups", []):
            count += len(group.get("LineItems", []))
    return count


def score_parse_result(parsed: ParseResult) -> float:
    """Higher is better. Works for any receipt shape - no fixed item count."""
    if not parsed.items:
        return -1000.0

    score = 0.0

    for item in parsed.items:
        head = re.split(r"[:(\-]", item.name, maxsplit=1)[0].strip().upper()
        if head in _FIELD_CODE_NAMES:
            score -= 40.0
            continue

        score += 8.0
        alpha = len(re.findall(r"[a-zA-Z]", item.name))
        ratio = alpha / len(item.name) if item.name else 0.0
        if ratio >= 0.35 and len(item.name) >= 2:
            score += 4.0
        if item.confidence == "high":
            score += 2.0
        elif item.confidence == "low":
            score -= 3.0
        if item.total_price <= 0 or item.total_price > 5000:
            score -= 15.0

    charge_types = {c.type for c in parsed.charges}
    if "total" in charge_types:
        score += 8.0
    if "subtotal" in charge_types:
        score += 4.0
    if "service_charge" in charge_types and "gst" in charge_types:
        score += 6.0

    for charge in parsed.charges:
        if _PRICE_IN_LABEL.search(charge.label):
            score -= 4.0

    subtotal = next((c for c in parsed.charges if c.type == "subtotal"), None)
    if subtotal is not None:
        item_sum = sum(it.total_price for it in parsed.items)
        discount = sum(c.amount for c in parsed.charges if c.type == "discount")
        expected = subtotal.amount - discount
        diff = abs(item_sum - expected)
        if diff <= 0.15:
            score += 12.0
        elif diff <= 2.0:
            score += 5.0
        elif diff > 50:
            score -= 8.0

    score -= len(parsed.warnings) * 1.5
    return score


def pick_best_parse(candidates: list[tuple[str, ParseResult]]) -> tuple[str, ParseResult] | None:
    if not candidates:
        return None
    ranked = sorted(
        ((name, parsed, score_parse_result(parsed)) for name, parsed in candidates),
        key=lambda row: row[2],
        reverse=True,
    )
    best_name, best_parsed, best_score = ranked[0]
    if best_score < MIN_ACCEPTABLE_SCORE:
        return None
    return best_name, best_parsed


def needs_bedrock_fallback(
    documents: list[dict[str, Any]],
    parsed: ParseResult | None = None,
) -> bool:
    if parsed is not None and score_parse_result(parsed) >= MIN_ACCEPTABLE_SCORE:
        return False
    if line_item_count(documents) == 0 and average_confidence(documents) == 0.0:
        return True
    if parsed is None or not parsed.items:
        return True
    return average_confidence(documents) < FALLBACK_CONFIDENCE_THRESHOLD


def parsed_result_looks_valid(parsed: ParseResult) -> bool:
    return score_parse_result(parsed) >= MIN_ACCEPTABLE_SCORE
