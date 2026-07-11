"""Bedrock Nova - structured receipt extraction + verbatim fallback."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import boto3

from splitleh.types import ParsedCharge, ParsedChargeType, ParsedItem, ParseResult

MODEL_ID = os.environ.get("SPLITLEH_BEDROCK_MODEL_ID", "apac.amazon.nova-lite-v1:0")

STRUCTURED_PROMPT = """Analyze this restaurant or cafe receipt (often Singapore POS format).

Return ONLY valid JSON - no markdown fences, no commentary:
{
  "raw_lines": ["verbatim printed lines for audit"],
  "items": [
    {"name": "Guinness", "quantity": 1, "unit_price": 13.0, "total_price": 13.0}
  ],
  "charges": [
    {"type": "subtotal", "label": "SUBTOTAL", "amount": 371.80},
    {"type": "service_charge", "label": "10% Svr Chrg", "amount": 37.18},
    {"type": "gst", "label": "9% GST", "amount": 36.81},
    {"type": "discount", "label": "ITEM DISC 30%", "amount": -136.80},
    {"type": "total", "label": "TOTAL", "amount": 445.79}
  ]
}

Rules:
- items = purchasable food/drink/products only (not subtotal, tax, service, payment, thank-you)
- charges.type must be one of: subtotal, gst, service_charge, discount, rounding, total
- Omit payment tender lines (VISA, NETS, cash) unless they are the only total
- quantity defaults to 1; amounts are numbers without currency symbols
- Include line-item discounts as charges.type discount when shown as separate receipt rows
- Preserve promo/qty prefixes inside item names when helpful, e.g. "(Promo) Guinness"
"""

VERBATIM_PROMPT = (
    "Transcribe this receipt as plain POS text. One printed row per output line. "
    "Keep leading quantities and prices with $ as shown. "
    "Include subtotal, service charge, GST, discounts, and total rows. "
    "Do not use internal field codes (AMOUNT_PAID, ITEM, OTHER). "
    "Skip payment card brand lines and thank-you footers."
)

_CHARGE_TYPES: dict[str, ParsedChargeType] = {
    "subtotal": "subtotal",
    "gst": "gst",
    "tax": "gst",
    "service_charge": "service_charge",
    "service": "service_charge",
    "svr_chrg": "service_charge",
    "discount": "discount",
    "rounding": "rounding",
    "total": "total",
}


def extract_receipt_structured(bucket: str, key: str) -> tuple[str, ParseResult]:
    """Primary cloud OCR - Bedrock vision → structured items/charges."""
    image_bytes, content_type = _load_image(bucket, key)
    resp = _converse(STRUCTURED_PROMPT, image_bytes, content_type)
    text = _extract_text(resp)
    data = _parse_json_payload(text)
    parsed = structured_data_to_parse_result(data)
    if not parsed.items:
        raise ValueError("Bedrock returned no items")
    raw_text = "\n".join(data.get("raw_lines") or []) or text
    return raw_text.strip(), parsed


def transcribe_receipt_image(bucket: str, key: str) -> str:
    """Verbatim transcription fallback when JSON extraction fails."""
    image_bytes, content_type = _load_image(bucket, key)
    resp = _converse(VERBATIM_PROMPT, image_bytes, content_type)
    return _extract_text(resp).strip()


def structured_data_to_parse_result(data: dict[str, Any]) -> ParseResult:
    items: list[ParsedItem] = []
    for row in data.get("items") or []:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        qty = int(row.get("quantity") or 1)
        total = float(row["total_price"])
        unit = float(row.get("unit_price") or (total / qty if qty else total))
        items.append(
            ParsedItem(
                name=name,
                unit_price=unit,
                quantity=max(qty, 1),
                total_price=total,
                confidence="high",
            )
        )

    charges: list[ParsedCharge] = []
    for row in data.get("charges") or []:
        raw_type = str(row.get("type") or "").lower().replace(" ", "_").replace("-", "_")
        charge_type = _CHARGE_TYPES.get(raw_type)
        if not charge_type:
            continue
        label = str(row.get("label") or charge_type).strip()
        charges.append(
            ParsedCharge(
                type=charge_type,
                label=label,
                amount=float(row["amount"]),
            )
        )

    return ParseResult(items=items, charges=charges, warnings=list(data.get("warnings") or []))


def _parse_json_payload(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Bedrock response is not JSON")
    return json.loads(cleaned[start : end + 1])


def _load_image(bucket: str, key: str) -> tuple[bytes, str]:
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read(), obj.get("ContentType") or "image/jpeg"


def _converse(prompt: str, image_bytes: bytes, content_type: str) -> dict:
    client = boto3.client("bedrock-runtime")
    return client.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [
                    {"text": prompt},
                    {
                        "image": {
                            "format": _format_for_content_type(content_type),
                            "source": {"bytes": image_bytes},
                        },
                    },
                ],
            },
        ],
        inferenceConfig={"maxTokens": 4096, "temperature": 0},
    )


def _extract_text(resp: dict) -> str:
    message = resp.get("output", {}).get("message", {})
    parts: list[str] = []
    for block in message.get("content", []):
        text = block.get("text")
        if text:
            parts.append(text)
    return "\n".join(parts)


def _format_for_content_type(content_type: str) -> str:
    if "png" in content_type:
        return "png"
    if "webp" in content_type:
        return "webp"
    return "jpeg"
