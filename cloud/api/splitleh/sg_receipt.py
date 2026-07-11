"""Singapore F&B receipt conventions - IRAS / POS patterns shared by parse + OCR."""

from __future__ import annotations

import re

# Current GST rate (Apr 2024 onward). Update when IRAS changes the rate.
SG_GST_RATE = 0.09
SG_SERVICE_CHARGE_RATE = 0.10

# Dine-in tax / service signals only - not "GST Reg No" (registration).
SG_TAX_OR_SERVICE_RE = re.compile(
    r"\b("
    r"service\s*cha(?:r(?:ge)?)?|service\s*charge|svr\s*ch|s\/c|"
    r"gst\s*\d+\s*%|\d+\s*%\s*gst|"
    r"(?<!reg\s)\bgst\b(?!\s*reg)|"
    r"\d+\s*%\s*(?:tax|svc|svr|sur)"
    r")\b",
    re.I,
)

# Broader footer vocabulary (includes subtotal labels).
SG_FNB_FOOTER_RE = re.compile(
    r"\b("
    r"service\s*cha(?:r(?:ge)?)?|service\s*charge|svr\s*ch|s\/c|"
    r"gst\s*\d+\s*%|\d+\s*%\s*gst|"
    r"(?<!reg\s)\bgst\b(?!\s*reg)|"
    r"sub[\s-]?total|subttl|cubtota|subtota|"
    r"item\s*disc|%disc|staff\s*disc|member\s*disc|"
    r"nett?\s*total|grand\s*total"
    r")\b",
    re.I,
)

# Payment tender lines - never splittable items.
SG_PAYMENT_NOISE_RE = re.compile(
    r"\b("
    r"visa|mastercard|amex|nets|paynow|grabpay|krisplus|"
    r"cash|change|octopus|apple\s*pay|google\s*pay"
    r")\b",
    re.I,
)


def looks_like_sg_fnb_footer(raw_text: str | None) -> bool:
    """True when OCR text resembles a Singapore restaurant bill footer."""
    return bool(raw_text and SG_FNB_FOOTER_RE.search(raw_text))


def looks_like_sg_tax_or_service_footer(raw_text: str | None) -> bool:
    """True when the receipt shows service charge / GST amount lines (not just GST Reg)."""
    return bool(raw_text and SG_TAX_OR_SERVICE_RE.search(raw_text))


def net_food_subtotal(subtotal: float, discount_sum: float) -> float:
    """
    Taxable food subtotal after item discounts.

    IRAS: 10% service charge applies to the food/beverage amount after discounts,
    then 9% GST applies to (net subtotal + service charge).
    """
    return round(subtotal + discount_sum, 2)


def expected_service_charge(subtotal: float, discount_sum: float) -> float:
    return round(net_food_subtotal(subtotal, discount_sum) * SG_SERVICE_CHARGE_RATE, 2)


def service_charge_candidates(subtotal: float, discount_sum: float) -> set[float]:
    """Some POS apply 10% before discounts, others after - accept either if close."""
    gross = round(subtotal, 2)
    net = net_food_subtotal(subtotal, discount_sum)
    return {
        round(gross * SG_SERVICE_CHARGE_RATE, 2),
        round(net * SG_SERVICE_CHARGE_RATE, 2),
    }


def expected_gst(subtotal: float, discount_sum: float, service_charge: float) -> float:
    base = net_food_subtotal(subtotal, discount_sum) + service_charge
    return round(base * SG_GST_RATE, 2)


def gst_candidates(subtotal: float, discount_sum: float, service_charge: float) -> set[float]:
    gross = round(subtotal, 2)
    net = net_food_subtotal(subtotal, discount_sum)
    return {
        round((net + service_charge) * SG_GST_RATE, 2),
        round((gross + service_charge) * SG_GST_RATE, 2),
    }
