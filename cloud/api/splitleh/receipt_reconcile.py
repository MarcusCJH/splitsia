"""Port of lite/core/src/receiptReconcile.ts (charge mapping only)."""

from __future__ import annotations

import re

from splitleh.money import round2
from splitleh.types import Charge, ParseResult, ParsedCharge


def extract_rate(label: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", label)
    if not match:
        return None
    pct = float(match.group(1))
    return pct / 100 if pct == pct else None


def _shorten_label(label: str, max_len: int = 32) -> str:
    text = " ".join(label.split())
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1]}…"


def _parse_charges(charges: list[dict]) -> list[ParsedCharge]:
    return [
        ParsedCharge(
            type=c["type"],
            label=c.get("label", c["type"]),
            amount=float(c["amount"]),
        )
        for c in charges
    ]


def charges_from_parse(parse: ParseResult) -> list[Charge]:
    """Map OCR footer lines into split charges (mirrors Lite Review screen)."""
    charges: list[Charge] = []

    svc = next((c for c in parse.charges if c.type == "service_charge"), None)
    gst_line = next((c for c in parse.charges if c.type == "gst"), None)
    discounts = [c for c in parse.charges if c.type == "discount"]
    rounding = next((c for c in parse.charges if c.type == "rounding"), None)

    svc_rate = extract_rate(svc.label) if svc else None
    charges.append(
        Charge(
            id="svc",
            type="service_charge",
            label=(
                f"Service Charge ({round(svc_rate * 100)}%)"
                if svc_rate is not None
                else "Service Charge (10%)"
            ),
            amount=svc.amount if svc else 0.0,
            rate=svc_rate if svc_rate is not None else 0.1,
            split_strategy="proportional",
        )
    )

    gst_rate = extract_rate(gst_line.label) if gst_line else None
    charges.append(
        Charge(
            id="gst",
            type="gst",
            label=(
                f"GST ({round(gst_rate * 100)}%)"
                if gst_rate is not None
                else "GST (9%)"
            ),
            amount=gst_line.amount if gst_line else 0.0,
            rate=gst_rate if gst_rate is not None else 0.09,
            split_strategy="proportional",
        )
    )

    if discounts:
        amount = round2(sum(d.amount for d in discounts))
        label = (
            _shorten_label(discounts[0].label)
            if len(discounts) == 1
            else f"Discounts ({len(discounts)})"
        )
        charges.append(
            Charge(
                id="discount",
                type="discount",
                label=label,
                amount=amount,
                split_strategy="proportional",
            )
        )

    if rounding and rounding.amount != 0:
        charges.append(
            Charge(
                id="rounding",
                type="rounding",
                label="Rounding",
                amount=rounding.amount,
                split_strategy="none",
            )
        )

    return charges


def charges_from_parsed_dicts(charges: list[dict]) -> list[Charge]:
    """Build Review-style charges from DynamoDB/OCR charge dicts."""
    parse = ParseResult(items=[], charges=_parse_charges(charges))
    return charges_from_parse(parse)
