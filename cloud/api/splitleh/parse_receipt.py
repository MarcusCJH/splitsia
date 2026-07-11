"""Receipt text parser - line-by-line heuristics for common SG receipt formats."""

from __future__ import annotations

import re
from dataclasses import dataclass

from splitleh.repair_receipt import repair_parsed_receipt
from splitleh.types import (
    Confidence,
    ParsedCharge,
    ParsedChargeType,
    ParsedItem,
    ParseResult,
)


@dataclass
class _ChargePattern:
    type: ParsedChargeType
    re: re.Pattern[str]
    force_negative: bool = False


@dataclass
class _PriceMatch:
    value: float
    index: int
    length: int


@dataclass
class _MatchedChargePattern:
    type: ParsedChargeType
    force_negative: bool = False


NOISE_RE = re.compile(
    "|".join(
        [
            r"\bcash\b",
            r"\bchange\b",
            r"\bcredit\s*card\b",
            r"\bdebit\s*card\b",
            r"\bnets\b",
            r"\bvisa\b",
            r"\bvis\b",
            r"\bmastercard\b",
            r"\bamex\b",
            r"\bkrisplus\b",
            r"\bpaynow\b",
            r"\bgrabpay\b",
            r"\bpayment\b",
            r"\bpayment\s+info\b",
            r"\bpaid\s*by\b",
            r"\bref(?:erence)?\s*(?:no|#)\b",
            r"\breceipt\s*(?:no|#|num)\b",
            r"\brcpt\b",
            r"\brept\b",
            r"\border\s*(?:no|#|num)\b",
            r"\binvoice\s*(?:no|#|num)\b",
            r"\bserver\b",
            r"\bcashier\b",
            r"\btable\s+\d",
            r"\bgst\s*reg\b",
            r"\buen\b",
            r"\bnric\b",
            r"\bthank\s*you\b",
            r"\bthanks\b",
            r"\bclosed\s+bill\b",
            r"\bbill\s+close\b",
            r"\bsignature\b",
            r"\bmember\s+tier\b",
            r"\bredeemable\s+points\b",
            r"\brewards\s+catalogue\b",
            r"\bsales\s+no\b",
            r"\btel\b",
            r"\bregister\b",
            r"\bcover\b",
            r"\bcaver\b",
            r"\baccumulated\b",
            r"\bissued\s+points\b",
            r"\bpoints\b",
            r"\bplease\s+(?:come|visit|call)\b",
            r"\bwelcome\b",
            r"\bwifi\b",
            r"\bpassword\b",
            r"@",
            r"www\.",
            r"\.com\b",
            r"\.sg\b",
        ]
    ),
    re.I,
)

CHARGE_PATTERNS: list[_ChargePattern] = [
    _ChargePattern(
        "subtotal",
        re.compile(
            r"\b(sub[\s-]?total|sub[\s-]?amt|sub\s*ttl|cubtota|subtota)\b",
            re.I,
        ),
    ),
    _ChargePattern("gst", re.compile(r"\bgst\b|\bg\.s\.t\.?\b", re.I)),
    _ChargePattern("gst", re.compile(r"\b\d{1,2}\s*ST\b", re.I)),
    _ChargePattern(
        "gst",
        re.compile(r"\b\d+%\s*(?:tax|vat)\b|\btax\b|\bvat\b", re.I),
    ),
    _ChargePattern(
        "service_charge",
        re.compile(
            r"\bservice\s*charges?\b|\bservice\s*cha(?:r(?:ge)?)?\b|"
            r"\bsvc\.?\s*ch(?:r?g?)?\b|\bsvr\.?\s*ch(?:r?g?)?\b|"
            r"\bsur\s+ch(?:r?g?)?\b|\bs\/c\b|\b\d+%\s*sur\b|\bvr\s+cheg",
            re.I,
        ),
    ),
    _ChargePattern(
        "discount",
        re.compile(
            r"\bdisc(?:ount)?\b|\bvoucher\b|\brebate\b|\bcoupon\b|\bitem\s+disc\b|"
            r"%disc\b|\bstaff[\s_]*disc\b",
            re.I,
        ),
        force_negative=True,
    ),
    _ChargePattern(
        "rounding",
        re.compile(r"\brounding\b|\bround\s*adj\b", re.I),
    ),
    _ChargePattern(
        "total",
        re.compile(
            r"\b(?:grand|nett?|net|bill)\s+total\b|"
            r"\btotal\s+(?:amount|bill|due|payable)\b|\bamount\s+due\b",
            re.I,
        ),
    ),
    _ChargePattern("total", re.compile(r"^\s*total\b", re.I)),
]

PRICE_RE = re.compile(r"(?:S?\$\s*)?(\d{1,4}\.\d{1,2})(?!\d)")


def _normalize_ocr_text(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"\b(\d{1,4}),(\d{2})\b", r"\1.\2", line)
        line = re.sub(r"(\d)[·•](\d)", r"\1.\2", line)
        line = re.sub(r"(\d)\.\s+(\d{2})\b", r"\1.\2", line)
        line = re.sub(r"(\d{1,4})\s+(\d{2})(\s*(?:[|}\]])?\s*)$", r"\1.\2\3", line)
        line = re.sub(r"(\d\.\d{2})[|}\]]+", r"\1", line)
        line = re.sub(r"([A-Za-z])(\$)", r"\1 \2", line)
        line = re.sub(r"\[TEM\s+DISC", "ITEM DISC", line, flags=re.I)
        line = re.sub(r"\{TEM\s+DISC", "ITEM DISC", line, flags=re.I)
        line = re.sub(
            r"([({\[])\s*S?\$?\s*(\d{1,4}),(\d{2})\s*([)\]}])",
            r"\1\2.\3\4",
            line,
        )
        line = re.sub(r"\bCUBTOTA\b", "SUBTOTAL", line, flags=re.I)
        line = re.sub(r"\bSUBTOTA\b", "SUBTOTAL", line, flags=re.I)
        line = re.sub(r"\bS\s*J\s*B\s*TOTAL\b", "SUBTOTAL", line, flags=re.I)
        line = re.sub(r"\bSur\s+Chir?ge?\b", "Svr Chrg", line, flags=re.I)
        line = re.sub(r"\bSur\s+Cha(?:rge)?\b", "Service Charge", line, flags=re.I)
        line = re.sub(r"\b0%\s*GST\b", "9% GST", line, flags=re.I)
        lines.append(line)
    return "\n".join(lines)


def _norm_price(raw: str) -> float:
    parts = raw.split(".")
    if len(parts) == 2 and len(parts[1]) == 1:
        return float(raw + "0")
    return float(raw)


def _all_prices(line: str) -> list[_PriceMatch]:
    matches: list[_PriceMatch] = []
    for m in PRICE_RE.finditer(line):
        if m.end() < len(line) and line[m.end()] == "%":
            continue
        value = _norm_price(m.group(1))
        if 0 < value < 9999.99:
            matches.append(_PriceMatch(value=value, index=m.start(), length=len(m.group(0))))

    if "." not in line:
        implicit = re.search(r"\s{2,}(\d{3,4})(?:\s*[|}\]])?\s*$", line)
        if implicit and not re.search(r"[/:]|gst\s*reg", line, re.I):
            value = int(implicit.group(1)) / 100
            if 0 < value < 500:
                index = line.rfind(implicit.group(1))
                overlaps = any(
                    index >= pm.index and index < pm.index + pm.length
                    for pm in matches
                )
                if not overlaps:
                    matches.append(
                        _PriceMatch(
                            value=value,
                            index=index,
                            length=len(implicit.group(1)),
                        )
                    )

    return sorted(matches, key=lambda pm: pm.index)


def _extract_signed_amount(line: str) -> float | None:
    neg_match = re.search(r"-\s*(?:S?\$\s*)?(\d{1,4}\.\d{1,2})", line)
    if neg_match:
        return -_norm_price(neg_match.group(1))

    paren_match = re.search(
        r"[{(\[]\s*S?\$?\s*(\d{1,4})[.,](\d{2})\s*[)\]}]",
        line,
    )
    if paren_match:
        return -_norm_price(f"{paren_match.group(1)}.{paren_match.group(2)}")

    paren_plain = re.search(r"\(\s*S?\$?\s*(\d{1,4}\.\d{1,2})\s*\)", line)
    if paren_plain:
        return -_norm_price(paren_plain.group(1))

    prices = _all_prices(line)
    return prices[-1].value if prices else None


def _match_charge_pattern(line: str) -> _MatchedChargePattern | None:
    for pattern in CHARGE_PATTERNS:
        if pattern.re.search(line):
            return _MatchedChargePattern(
                type=pattern.type,
                force_negative=pattern.force_negative,
            )
    return None


def _detect_charge(
    line: str,
    fallback_amount: float | None = None,
) -> ParsedCharge | None:
    pattern = _match_charge_pattern(line)
    if not pattern:
        return None
    raw = _extract_signed_amount(line)
    if raw is None:
        raw = fallback_amount
    if raw is None:
        return None
    amount = -raw if pattern.force_negative and raw > 0 else raw
    return ParsedCharge(type=pattern.type, label=line, amount=amount)


def _extract_qty(text: str) -> tuple[str, int]:
    name = text.strip()
    qty = 1

    if re.match(r"^\(\d{1,2}\)\s", name):
        return name, 1

    front = re.match(r"^(\d{1,2})\s*[x×@]\s+", name, re.I)
    if front:
        qty = max(1, int(front.group(1)))
        name = name[len(front.group(0)) :]
        return name, qty

    with_code = re.match(r"^(\d{1,2})\s+(\d{3,4})\s+(.+)$", name)
    if with_code:
        qty = max(1, int(with_code.group(1)))
        name = with_code.group(3).strip()
        return name, qty

    back = re.search(r"\s+[x×]\s*(\d{1,2})$", name, re.I)
    if back:
        qty = max(1, int(back.group(1)))
        name = name[: -len(back.group(0))]
        return name, qty

    bare = re.match(r"^(\d{1,2})\s+(?=[A-Za-z(])", name)
    if bare:
        qty = max(1, int(bare.group(1)))
        name = name[len(bare.group(0)) :]

    return name, qty


def _clean_name(raw: str) -> str:
    name = re.sub(r"^\d{3,}\s+", "", raw)
    name = re.sub(r"^[A-Za-z]\s+(?=[A-Z(])", "", name)
    name = re.sub(r"^[^\w(]+\s*", "", name)
    name = re.sub(r"\s{2,}", " ", name)
    return name.strip()


def _is_likely_summary_line(name: str, price: float) -> bool:
    if _match_charge_pattern(name):
        return True
    if re.search(
        r"\b(?:sub\s*total|cubtota|subtota|grand\s*total|amount\s+due)\b",
        name,
        re.I,
    ):
        return True
    if price >= 100:
        alpha = len(re.findall(r"[a-zA-Z]", name))
        ratio = alpha / len(name) if name else 0.0
        if ratio < 0.45:
            return True
    return False


def _is_junk_name_line(raw: str) -> bool:
    trimmed = raw.strip()
    if len(trimmed) < 2:
        return True
    if re.match(r"^[\W_=]+$", trimmed):
        return True
    alpha = len(re.findall(r"[a-zA-Z]", trimmed))
    return alpha < 2


def _score_confidence(name: str, price_count: int) -> Confidence:
    alpha = len(re.findall(r"[a-zA-Z]", name))
    ratio = alpha / len(name) if name else 0.0
    if price_count >= 3 or len(name) < 3:
        return "low"
    if price_count == 1 and len(name) >= 4 and ratio >= 0.5:
        return "high"
    return "medium"


def parse_receipt(raw_text: str) -> ParseResult:
    items: list[ParsedItem] = []
    charges: list[ParsedCharge] = []
    warnings: list[str] = []

    lines = [
        l.strip()
        for l in _normalize_ocr_text(raw_text).split("\n")
        if len(l.strip()) >= 3
    ]

    orphan_name: str | None = None
    pending_amounts: list[float] = []
    pending_item_price: float | None = None

    def looks_like_new_item_line(line: str) -> bool:
        return bool(re.match(r"^\d{1,2}\s+(\d{3,4}\s+)?[A-Za-z(]", line))

    for line in lines:
        if NOISE_RE.search(line):
            orphan_name = None
            continue

        charge_pattern = _match_charge_pattern(line)
        inline_amount = _extract_signed_amount(line)

        if (
            charge_pattern
            and inline_amount is None
            and pending_amounts
        ):
            amount = pending_amounts.pop()
            signed = -amount if charge_pattern.force_negative and amount > 0 else amount
            charges.append(
                ParsedCharge(type=charge_pattern.type, label=line, amount=signed)
            )
            orphan_name = None
            continue

        prices = _all_prices(line)

        if len(prices) == 1 and re.match(r"^\s*\$\s*\d{1,4}\.\d{2}\s*$", line):
            if prices[0].value >= 20:
                charges.append(
                    ParsedCharge(type="total", label=line, amount=prices[0].value)
                )
                orphan_name = None
                continue

        if not prices:
            if (
                looks_like_new_item_line(line)
                and items
                and re.match(r"^tot$", items[-1].name, re.I)
            ):
                prev = items.pop()
                pending_item_price = prev.total_price
                orphan_name = line
                continue
            if charge_pattern:
                orphan_name = line
            elif looks_like_new_item_line(line):
                orphan_name = line
            elif orphan_name:
                merged = f"{orphan_name} {line}".strip()
                orphan_name = merged if len(merged) <= 48 else orphan_name
            else:
                orphan_name = line
            continue

        charge = _detect_charge(line)
        if charge:
            orphan_name = None
            pending_amounts.clear()
            charges.append(charge)
            continue

        last = prices[-1]
        raw_name = line[: last.index].strip()

        if _is_junk_name_line(raw_name):
            if orphan_name is not None:
                raw_name = orphan_name
                combined_charge = _detect_charge(f"{raw_name} {line.strip()}")
                if combined_charge:
                    orphan_name = None
                    charges.append(combined_charge)
                    continue
            elif re.match(r"^[\W_=]+\s*$", raw_name):
                continue
            else:
                pending_amounts.append(last.value)
                continue

        joined_orphan = orphan_name
        orphan_name = None
        pending_amounts.clear()

        name_with_qty, qty = _extract_qty(raw_name)
        name = _clean_name(name_with_qty)
        total_price = last.value
        quantity = qty

        if (
            joined_orphan
            and (re.match(r"^tot$", name, re.I) or len(name) <= 3)
            and total_price < 50
        ):
            name = _clean_name(_extract_qty(joined_orphan)[0])
        elif re.match(r"^tot$", name, re.I) and total_price < 50:
            pending_item_price = total_price
            continue
        elif pending_item_price is not None and looks_like_new_item_line(
            joined_orphan or raw_name
        ):
            source = joined_orphan or raw_name
            name = _clean_name(_extract_qty(source)[0])
            total_price = pending_item_price
            quantity = _extract_qty(source)[1]
            pending_item_price = None

        if len(name) < 2 or len(name) > 52:
            continue
        if len(name) > 28 and total_price < 25 and not re.match(r"^\d", raw_name):
            continue

        unit_price = (
            round((total_price / quantity) * 100) / 100
            if quantity > 1
            else total_price
        )
        confidence = _score_confidence(name, len(prices))

        items.append(
            ParsedItem(
                name=name,
                unit_price=unit_price,
                quantity=quantity,
                total_price=total_price,
                confidence=confidence,
            )
        )

    subtotal = next((c for c in charges if c.type == "subtotal"), None)
    totals = [c for c in charges if c.type == "total"]

    if len(totals) > 1:
        warnings.append("Multiple total lines detected - verify the correct total.")

    if not totals and items:
        warnings.append("No total line detected - add the total manually.")

    low_count = sum(1 for it in items if it.confidence == "low")
    if low_count > 0:
        warnings.append(
            f"{low_count} item{'s' if low_count > 1 else ''} "
            f"{'have' if low_count > 1 else 'has'} low OCR confidence - "
            "check names and prices carefully."
        )

    total_charge = next((c for c in charges if c.type == "total"), None)
    filtered_items = [
        it
        for it in items
        if not _is_likely_summary_line(it.name, it.total_price)
        and not (
            subtotal is not None
            and abs(it.total_price - subtotal.amount) < 0.02
            and (it.total_price > 80 or _match_charge_pattern(it.name))
        )
        and not (
            total_charge is not None
            and abs(it.total_price - total_charge.amount) < 0.02
            and _match_charge_pattern(it.name)
        )
    ]

    if len(filtered_items) < len(items):
        warnings.append("Removed lines that look like receipt totals, not items.")

    result = repair_parsed_receipt(
        ParseResult(items=filtered_items, charges=charges, warnings=warnings),
        raw_text,
    )

    repaired_subtotal = next((c for c in result.charges if c.type == "subtotal"), None)
    if repaired_subtotal is not None:
        discount_sum = sum(c.amount for c in result.charges if c.type == "discount")
        net_items = sum(it.total_price for it in result.items) + discount_sum
        diff = abs(net_items - repaired_subtotal.amount)
        if diff > 0.10:
            result.warnings.append(
                f"Items sum ${net_items:.2f} differs from detected subtotal "
                f"${repaired_subtotal.amount:.2f} - some items may be missing."
            )

    return result
