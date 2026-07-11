"""Recover footer lines and infer missing discount / GST - mirrors repairReceipt.ts."""

from __future__ import annotations

import re

from splitleh.money import round2
from splitleh.sg_receipt import (
    expected_gst,
    expected_service_charge,
    gst_candidates,
    looks_like_sg_tax_or_service_footer,
    service_charge_candidates,
)
from splitleh.types import ParseResult, ParsedCharge, ParsedItem


def _letter_ratio(name: str) -> float:
    alpha = len(re.findall(r"[a-zA-Z]", name))
    return alpha / len(name) if name else 0.0


def _is_subtotal_name(name: str) -> bool:
    return bool(
        re.search(r"\b(?:sub|cub|sjb)\s*tot", name, re.I)
        or re.match(r"^subtot", name, re.I)
    )


def _is_footer_garbage_name(name: str) -> bool:
    n = name.strip()
    if _letter_ratio(n) < 0.42 and len(n) <= 14:
        return True
    return bool(re.match(r"^(?:se oy|sar ii|cubtota|subtota|ttl|tot|vr cheg)", n, re.I))


def _looks_like_service_label(name: str) -> bool:
    return bool(re.search(r"\b(?:svr|svc|cheg|chrg|service|sur)\b", name, re.I))


def _looks_like_gst_label(name: str) -> bool:
    return bool(re.search(r"\bgst\b", name, re.I) or re.search(r"\d{1,2}\s*ST\b", name))


def _match_charge_pattern(name: str) -> bool:
    return bool(re.search(r"\b(?:total|subtotal|gst|service|discount)\b", name, re.I))


def _has_charge(charges: list[ParsedCharge], charge_type: str) -> bool:
    return any(c.type == charge_type for c in charges)


def _bill_already_closed(charges: list[ParsedCharge]) -> bool:
    """Subtotal ≈ total means no room for inventing service charge + GST."""
    subtotal = next((c for c in charges if c.type == "subtotal"), None)
    total = next((c for c in charges if c.type == "total"), None)
    if not subtotal or not total:
        return False
    return abs(subtotal.amount - total.amount) < 0.05


def _should_infer_taxes(
    charges: list[ParsedCharge],
    items: list[ParsedItem],
    raw_text: str | None = None,
) -> bool:
    if _has_charge(charges, "service_charge"):
        return True
    if _has_charge(charges, "subtotal") and _has_charge(charges, "gst"):
        return False
    # Hawker / GST-inclusive: Sub Total == Net Total, no S/C or GST lines printed.
    if _bill_already_closed(charges):
        return False
    if (
        looks_like_sg_tax_or_service_footer(raw_text)
        and _has_charge(charges, "subtotal")
        and (
            not _has_charge(charges, "service_charge")
            or not _has_charge(charges, "gst")
        )
    ):
        return True
    return False


def _find_price_near(raw_text: str, target: float) -> float | None:
    re_price = re.compile(r"(?:S?\$\s*)?(\d{1,4}\.\d{1,2})")
    best: float | None = None
    best_diff = float("inf")
    for m in re_price.finditer(raw_text):
        v = float(m.group(1))
        diff = abs(v - target)
        if diff < 0.12 and diff < best_diff:
            best = v
            best_diff = diff
    return best


def _food_item_sum(items: list[ParsedItem], charges: list[ParsedCharge]) -> float:
    subtotal = next((c.amount for c in charges if c.type == "subtotal"), None)
    footer_amounts = {
        round2(abs(c.amount))
        for c in charges
        if c.type != "discount"
    }

    total = sum(
        it.total_price
        for it in items
        if not (
            (subtotal is not None and abs(it.total_price - subtotal) < 0.03)
            or round2(it.total_price) in footer_amounts
            or _is_footer_garbage_name(it.name)
            or _is_subtotal_name(it.name)
            or _looks_like_service_label(it.name)
            or _looks_like_gst_label(it.name)
        )
    )
    return round2(total)


def _remove_footer_amount_items(
    items: list[ParsedItem],
    charges: list[ParsedCharge],
) -> list[ParsedItem]:
    subtotal = next((c for c in charges if c.type == "subtotal"), None)
    svc = next((c for c in charges if c.type == "service_charge"), None)
    gst = next((c for c in charges if c.type == "gst"), None)
    total = next((c for c in charges if c.type == "total"), None)

    def keep(it: ParsedItem) -> bool:
        if subtotal and abs(it.total_price - subtotal.amount) < 0.03:
            if _is_subtotal_name(it.name) or _letter_ratio(it.name) < 0.55:
                return False
        if svc and abs(it.total_price - svc.amount) < 0.03:
            if _looks_like_service_label(it.name) or _letter_ratio(it.name) < 0.55:
                return False
        if gst and abs(it.total_price - gst.amount) < 0.03:
            if _looks_like_gst_label(it.name) or _letter_ratio(it.name) < 0.55:
                return False
        if total and abs(it.total_price - total.amount) < 0.03:
            if _match_charge_pattern(it.name) or _is_footer_garbage_name(it.name):
                return False
        if _is_footer_garbage_name(it.name):
            return False
        if _looks_like_service_label(it.name) and it.total_price < 100:
            if not _has_charge(charges, "service_charge"):
                charges.append(
                    ParsedCharge(
                        type="service_charge",
                        label=it.name,
                        amount=it.total_price,
                    )
                )
            return False
        if _looks_like_gst_label(it.name) and it.total_price < 100:
            if not _has_charge(charges, "gst"):
                charges.append(
                    ParsedCharge(type="gst", label=it.name, amount=it.total_price)
                )
            return False
        return True

    return [it for it in items if keep(it)]


def _strip_computed_total_items(
    items: list[ParsedItem],
    charges: list[ParsedCharge],
) -> None:
    subtotal = next((c for c in charges if c.type == "subtotal"), None)
    svc = next((c for c in charges if c.type == "service_charge"), None)
    gst = next((c for c in charges if c.type == "gst"), None)
    if not subtotal or not svc or not gst:
        return
    expected = round2(subtotal.amount + svc.amount + gst.amount)
    i = len(items) - 1
    while i >= 0:
        if abs(items[i].total_price - expected) < 0.15:
            items.pop(i)
        i -= 1


def _promote_subtotal(items: list[ParsedItem], charges: list[ParsedCharge]) -> None:
    if _has_charge(charges, "subtotal"):
        return

    foodish = re.compile(
        r"\b(?:juice|beer|wine|moscato|guinness|pho|coffee|btl|bt\]|bt\}|noodle|rice|satay|chicken)\b",
        re.I,
    )

    candidates: list[tuple[ParsedItem, int]] = []
    for i, it in enumerate(items):
        if (
            _is_subtotal_name(it.name)
            or (
                it.total_price >= 50
                and it.total_price < 2000
                and _letter_ratio(it.name) < 0.8
                and not foodish.search(it.name)
            )
        ) and not (it.quantity > 1 and not _is_subtotal_name(it.name)):
            candidates.append((it, i))

    if not candidates:
        return

    max_price = max(it.total_price for it in items)
    item_sum = sum(it.total_price for it in items)

    def sort_key(pair: tuple[ParsedItem, int]) -> tuple:
        it, _ = pair
        a_sub = _is_subtotal_name(it.name)
        a_below_max = 1 if it.total_price < max_price else 0
        a_below_sum = 1 if it.total_price < item_sum - 20 else 0
        return (
            0 if a_sub else 1,
            -a_below_max,
            -a_below_sum,
            _letter_ratio(it.name),
        )

    candidates.sort(key=sort_key)
    pick, pick_i = candidates[0]
    charges.append(
        ParsedCharge(type="subtotal", label=pick.name, amount=pick.total_price)
    )
    items.pop(pick_i)


def _ensure_service_charge(
    items: list[ParsedItem],
    charges: list[ParsedCharge],
    warnings: list[str],
) -> None:
    subtotal = next((c for c in charges if c.type == "subtotal"), None)
    if not subtotal:
        return

    discount_sum = sum(c.amount for c in charges if c.type == "discount")
    expected = expected_service_charge(subtotal.amount, discount_sum)
    candidates = service_charge_candidates(subtotal.amount, discount_sum)
    existing = next((c for c in charges if c.type == "service_charge"), None)

    if existing:
        if any(abs(existing.amount - c) <= 0.55 for c in candidates):
            return
        existing.amount = expected
        warnings.append("Service charge corrected to 10% of net subtotal.")
        return

    idx = next(
        (
            i
            for i, it in enumerate(items)
            if _looks_like_service_label(it.name)
            or (
                _letter_ratio(it.name) < 0.55
                and abs(it.total_price - expected) < 6
            )
        ),
        -1,
    )
    if idx >= 0 and abs(items[idx].total_price - expected) < 6:
        charges.append(
            ParsedCharge(
                type="service_charge",
                label=items[idx].name,
                amount=expected,
            )
        )
        if abs(items[idx].total_price - expected) > 0.03:
            warnings.append("Service charge corrected to 10% of net subtotal.")
        items.pop(idx)
    else:
        charges.append(
            ParsedCharge(type="service_charge", label="10% Svr Chrg", amount=expected)
        )
        warnings.append("Service charge inferred at 10% of net subtotal.")


def _ensure_gst(
    items: list[ParsedItem],
    charges: list[ParsedCharge],
    warnings: list[str],
) -> None:
    subtotal = next((c for c in charges if c.type == "subtotal"), None)
    svc = next((c for c in charges if c.type == "service_charge"), None)
    if not subtotal or not svc:
        return

    discount_sum = sum(c.amount for c in charges if c.type == "discount")
    expected = expected_gst(subtotal.amount, discount_sum, svc.amount)
    candidates = gst_candidates(subtotal.amount, discount_sum, svc.amount)
    existing = next((c for c in charges if c.type == "gst"), None)

    if existing:
        if any(abs(existing.amount - c) <= 0.55 for c in candidates):
            return
        existing.amount = expected
        warnings.append("GST corrected to 9% of (net subtotal + service).")
        return

    idx = next(
        (
            i
            for i, it in enumerate(items)
            if _looks_like_gst_label(it.name)
            or (
                _letter_ratio(it.name) < 0.55
                and abs(it.total_price - expected) < 1.5
            )
        ),
        -1,
    )
    if idx >= 0:
        amount = (
            items[idx].total_price
            if abs(items[idx].total_price - expected) < 1.5
            else expected
        )
        charges.append(ParsedCharge(type="gst", label=items[idx].name, amount=amount))
        items.pop(idx)
    else:
        charges.append(
            ParsedCharge(type="gst", label="9% GST (inferred)", amount=expected)
        )
        warnings.append("GST inferred at 9% - footer was unclear in the photo.")


def _fix_underpriced_qty_item(
    items: list[ParsedItem],
    charges: list[ParsedCharge],
    warnings: list[str],
) -> None:
    subtotal = next((c for c in charges if c.type == "subtotal"), None)
    if not subtotal:
        return

    discount_sum = sum(c.amount for c in charges if c.type == "discount")
    net = round2(_food_item_sum(items, charges) + discount_sum)
    gap = round2(subtotal.amount - net)
    if abs(gap) < 0.5 or abs(gap) > 30:
        return

    suspect = next(
        (
            it
            for it in items
            if it.quantity > 1
            and it.unit_price < 5
            and it.total_price < it.quantity * 5
        ),
        None,
    )
    if not suspect:
        return

    suspect.total_price = round2(suspect.total_price + gap)
    suspect.unit_price = round2(suspect.total_price / suspect.quantity)
    warnings.append(f'Adjusted "{suspect.name}" price using receipt subtotal.')


def repair_parsed_receipt(
    parse: ParseResult,
    raw_text: str | None = None,
) -> ParseResult:
    """Recover footer lines that OCR turned into fake items, and infer missing charges."""
    items = list(parse.items)
    charges = list(parse.charges)
    warnings = list(parse.warnings)

    i = len(items) - 1
    while i >= 0:
        it = items[i]
        if _is_subtotal_name(it.name) and not _has_charge(charges, "subtotal"):
            charges.append(
                ParsedCharge(type="subtotal", label=it.name, amount=it.total_price)
            )
            items.pop(i)
        i -= 1

    _promote_subtotal(items, charges)

    subtotal = next((c for c in charges if c.type == "subtotal"), None)
    infer_taxes = _should_infer_taxes(charges, items, raw_text)

    if infer_taxes and subtotal:
        _ensure_service_charge(items, charges, warnings)
        _ensure_gst(items, charges, warnings)

    items = _remove_footer_amount_items(items, charges)
    _strip_computed_total_items(items, charges)

    if subtotal and not _has_charge(charges, "discount"):
        food_sum = _food_item_sum(items, charges)
        if food_sum > subtotal.amount + 0.05:
            disc = round2(subtotal.amount - food_sum)
            if disc > -250:
                charges.append(
                    ParsedCharge(
                        type="discount",
                        label="Inferred item discount",
                        amount=disc,
                    )
                )
                warnings.append("Inferred discount from items vs printed subtotal.")

    _fix_underpriced_qty_item(items, charges, warnings)

    svc = next((c for c in charges if c.type == "service_charge"), None)
    gst = next((c for c in charges if c.type == "gst"), None)

    if not _has_charge(charges, "total") and subtotal and (
        (svc and gst) or len(items) <= 4
    ):
        expected = round2(subtotal.amount + (svc.amount if svc else 0) + (gst.amount if gst else 0))
        from_text = _find_price_near(raw_text, expected) if raw_text else None
        charges.append(
            ParsedCharge(
                type="total",
                label="TOTAL" if from_text is not None else "TOTAL (calculated)",
                amount=from_text if from_text is not None else expected,
            )
        )

    return ParseResult(items=items, charges=charges, warnings=warnings)
