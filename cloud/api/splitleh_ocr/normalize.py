"""Convert Textract AnalyzeExpense documents to ParseResult or audit text."""

from __future__ import annotations

import re
from typing import Any

from splitleh.parse_receipt import parse_receipt
from splitleh.repair_receipt import repair_parsed_receipt
from splitleh.types import Confidence, ParsedCharge, ParsedChargeType, ParsedItem, ParseResult

_PRICE_RE = re.compile(r"(?:S?\$\s*)?(\d{1,4}\.\d{1,2})")

_SUMMARY_CHARGE_TYPES: dict[str, ParsedChargeType] = {
    "SUBTOTAL": "subtotal",
    "TAX": "gst",
    "GST": "gst",
    "SERVICE_CHARGE": "service_charge",
    "TIP": "service_charge",
    "DISCOUNT": "discount",
    "TOTAL": "total",
    "AMOUNT_DUE": "total",
}

_SKIP_SUMMARY_TYPES = frozenset(
    {
        "VENDOR_NAME",
        "VENDOR_ADDRESS",
        "VENDOR_PHONE",
        "RECEIVER_NAME",
        "RECEIVER_ADDRESS",
        "RECEIVER_PHONE",
        "INVOICE_RECEIPT_ID",
        "INVOICE_RECEIPT_DATE",
        "PO_NUMBER",
        "AMOUNT_PAID",
        "PAYMENT_TERMS",
        "DUE_DATE",
        "ADDRESS",
        "NAME",
        "ADDRESS_BLOCK",
        "STREET",
        "CITY",
        "STATE",
        "ZIP_CODE",
        "COUNTRY",
    }
)

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
    }
)


def expense_documents_to_parse_result(documents: list[dict[str, Any]]) -> ParseResult:
    """Structured Textract → items/charges (preferred over plain-text parse)."""
    items: list[ParsedItem] = []
    charges: list[ParsedCharge] = []
    warnings: list[str] = []

    for doc in documents:
        for field in doc.get("SummaryFields", []):
            charge = _summary_field_to_charge(field)
            if charge:
                charges.append(charge)

        for group in doc.get("LineItemGroups", []):
            for row in group.get("LineItems", []):
                item = _line_item_to_parsed_item(row.get("LineItemExpenseFields", []))
                if item:
                    items.append(item)

    charges = _dedupe_charges(charges)
    raw_text = expense_documents_to_text(documents)
    return repair_parsed_receipt(
        ParseResult(items=items, charges=charges, warnings=warnings),
        raw_text,
    )


def expense_documents_blocks_to_text(documents: list[dict[str, Any]]) -> str:
    """Raw LINE blocks from Textract - works when structured fields are incomplete."""
    lines: list[str] = []
    for doc in documents:
        for block in doc.get("Blocks", []):
            if block.get("BlockType") == "LINE":
                text = (block.get("Text") or "").strip()
                if text:
                    lines.append(text)
    return "\n".join(lines).strip()


def parse_receipt_text(text: str) -> ParseResult:
    """Text → ParseResult with repair pass."""
    cleaned = text.strip()
    if not cleaned:
        return ParseResult()
    return repair_parsed_receipt(parse_receipt(cleaned), cleaned)


def expense_documents_to_text(
    documents: list[dict[str, Any]],
    *,
    include_summary: bool = True,
) -> str:
    """Plain receipt lines for audit / text-parser fallback."""
    lines: list[str] = []

    for doc in documents:
        if include_summary:
            for field in doc.get("SummaryFields", []):
                type_text = _field_type(field)
                if type_text in _SKIP_SUMMARY_TYPES:
                    continue
                label = _summary_label(field)
                value = _field_value(field)
                if label and value:
                    lines.append(f"{label} {value}")
                elif value:
                    lines.append(value)

        for group in doc.get("LineItemGroups", []):
            for row in group.get("LineItems", []):
                line = _line_item_to_text(row.get("LineItemExpenseFields", []))
                if line:
                    lines.append(line)

    return "\n".join(lines).strip()

def _infer_charge_from_label(label: str, amount: float) -> ParsedCharge | None:
    """Reuse receipt charge heuristics on arbitrary vendor labels."""
    sign = f"-${abs(amount):.2f}" if amount < 0 else f"${amount:.2f}"
    result = parse_receipt(f"{label} {sign}")
    return result.charges[0] if result.charges else None


def _summary_field_to_charge(field: dict[str, Any]) -> ParsedCharge | None:
    type_text = _field_type(field).upper()
    if not type_text or type_text in _SKIP_SUMMARY_TYPES:
        return None

    value = _field_value(field)
    amount = _parse_amount(value)
    if amount is None:
        return None

    label = _summary_label(field) or type_text.replace("_", " ").title()
    charge_type = _SUMMARY_CHARGE_TYPES.get(type_text)

    if type_text == "OTHER":
        inferred = _infer_charge_from_label(label, amount)
        if inferred:
            return inferred
        if amount < 0:
            return ParsedCharge(type="discount", label=label, amount=amount)
        return None

    if not charge_type:
        return _infer_charge_from_label(label, amount)

    if charge_type == "discount" and amount > 0:
        amount = -amount

    return ParsedCharge(type=charge_type, label=label, amount=amount)


def _line_item_to_parsed_item(fields: list[dict[str, Any]]) -> ParsedItem | None:
    by_type: dict[str, str] = {}
    expense_rows: list[str] = []
    confidences: list[float] = []

    for field in fields:
        type_text = _field_type(field).upper()
        value = _field_value(field)
        if not value:
            continue
        conf = field.get("ValueDetection", {}).get("Confidence")
        if conf is not None:
            confidences.append(float(conf) / 100.0)

        if type_text in {"ITEM", "QUANTITY", "PRICE", "UNIT_PRICE", "PRODUCT_CODE"}:
            by_type[type_text] = value
        elif type_text == "EXPENSE_ROW":
            expense_rows.append(value)

    name = by_type.get("ITEM")
    qty = _parse_quantity(by_type.get("QUANTITY"))
    price_text = by_type.get("PRICE") or by_type.get("UNIT_PRICE")
    total_price = _parse_amount(price_text) if price_text else None

    if not name and expense_rows:
        parsed = _parse_expense_row(expense_rows[0])
        if parsed:
            name, qty, total_price = parsed

    if not name:
        joined = " ".join(
            _field_value(f)
            for f in fields
            if _field_type(f).upper() not in {"PRICE", "UNIT_PRICE", "QUANTITY"}
        ).strip()
        if joined:
            parsed = _parse_expense_row(joined)
            if parsed:
                name, qty, total_price = parsed

    if not name or total_price is None or total_price <= 0:
        return None

    head = re.split(r"[:(\-]", name, maxsplit=1)[0].strip().upper()
    if head in _FIELD_CODE_NAMES or head in _SUMMARY_CHARGE_TYPES:
        return None

    quantity = max(qty, 1)
    unit_price = round((total_price / quantity) * 100) / 100
    confidence = _score_confidence(confidences, name)

    return ParsedItem(
        name=name.strip(),
        unit_price=unit_price,
        quantity=quantity,
        total_price=total_price,
        confidence=confidence,
    )


def _line_item_to_text(fields: list[dict[str, Any]]) -> str:
    by_type: dict[str, str] = {}
    expense_rows: list[str] = []

    for field in fields:
        type_text = _field_type(field).upper()
        value = _field_value(field)
        if not value:
            continue
        if type_text in {"ITEM", "QUANTITY", "PRICE", "UNIT_PRICE"}:
            by_type[type_text] = value
        elif type_text == "EXPENSE_ROW":
            expense_rows.append(value)

    qty = by_type.get("QUANTITY")
    name = by_type.get("ITEM")
    price = by_type.get("PRICE") or by_type.get("UNIT_PRICE")

    if name and price:
        prefix = f"{qty} " if qty else ""
        return f"{prefix}{name} {price}".strip()

    if expense_rows:
        return expense_rows[0]

    parts = [_field_value(f) for f in fields if _field_value(f)]
    return " ".join(parts).strip()


def _parse_expense_row(text: str) -> tuple[str, int, float] | None:
    prices = [
        float(m.group(1))
        for m in _PRICE_RE.finditer(text)
        if 0 < float(m.group(1)) < 9999.99
    ]
    if not prices:
        return None

    total_price = prices[-1]
    qty = 1
    name = text

    qty_match = re.match(r"^(\d{1,2})\s+(\d{3,4}\s+)?(.+)$", text.strip())
    if qty_match:
        qty = max(1, int(qty_match.group(1)))
        name = qty_match.group(3)

    name = _PRICE_RE.sub("", name)
    name = re.sub(r"\s{2,}", " ", name).strip(" -")
    name = re.sub(rf"\b{qty}\b\s*$", "", name).strip()

    if len(name) < 2:
        return None
    return name, qty, total_price


def _parse_quantity(raw: str | None) -> int:
    if not raw:
        return 1
    match = re.search(r"\d+", raw)
    if not match:
        return 1
    return max(1, int(match.group(0)))


def _parse_amount(text: str | None) -> float | None:
    if not text:
        return None
    trimmed = text.strip()
    negative = trimmed.startswith("-") or trimmed.startswith("(")
    match = _PRICE_RE.search(trimmed)
    if not match:
        return None
    value = float(match.group(1))
    if negative:
        value = -value
    return value


def _summary_label(field: dict[str, Any]) -> str:
    label = _field_text(field.get("LabelDetection"))
    if label:
        return label
    type_text = _field_type(field)
    if not type_text:
        return ""
    return type_text.replace("_", " ").title()


def _dedupe_charges(charges: list[ParsedCharge]) -> list[ParsedCharge]:
    seen: set[tuple[ParsedChargeType, float]] = set()
    deduped: list[ParsedCharge] = []
    for charge in charges:
        key = (charge.type, round(charge.amount, 2))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(charge)
    return deduped


def _score_confidence(confidences: list[float], name: str) -> Confidence:
    if confidences:
        avg = sum(confidences) / len(confidences)
        if avg >= 0.85 and len(name) >= 3:
            return "high"
        if avg >= 0.65:
            return "medium"
        return "low"
    alpha = len(re.findall(r"[a-zA-Z]", name))
    ratio = alpha / len(name) if name else 0.0
    if len(name) >= 4 and ratio >= 0.5:
        return "medium"
    return "low"


def _field_type(field: dict[str, Any]) -> str:
    return (_field_text(field.get("Type")) or "").strip().upper()


def _field_value(field: dict[str, Any]) -> str:
    return _field_text(field.get("ValueDetection"))


def _field_text(field: dict[str, Any] | None) -> str:
    if not field:
        return ""
    return (field.get("Text") or "").strip()
