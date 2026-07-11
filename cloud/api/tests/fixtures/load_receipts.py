"""Load shared receipt OCR text from lite/core/tests/fixtures/receipts/."""

from __future__ import annotations

from pathlib import Path

RECEIPTS_DIR = (
    Path(__file__).resolve().parents[4]
    / "lite"
    / "core"
    / "tests"
    / "fixtures"
    / "receipts"
)

GOLDEN_PATH = (
    Path(__file__).resolve().parents[4]
    / "lite"
    / "core"
    / "tests"
    / "fixtures"
    / "parseGolden.json"
)


def load_receipt(name: str) -> str:
    return (RECEIPTS_DIR / f"{name}.txt").read_text(encoding="utf-8").strip()


CLEAN_RECEIPT = load_receipt("clean")
QTY_RECEIPT = load_receipt("qty")
CODES_RECEIPT = load_receipt("codes")
NOISY_RECEIPT = load_receipt("noisy")
DISCOUNT_RECEIPT = load_receipt("discount")
DISCOUNT_POSITIVE_RECEIPT = load_receipt("discount_positive")
MISMATCH_RECEIPT = load_receipt("mismatch")
TWO_TOTALS_RECEIPT = load_receipt("two_totals")
NO_TOTAL_RECEIPT = load_receipt("no_total")
LOW_CONF_RECEIPT = load_receipt("low_conf")
POS_NATURELAND_RECEIPT = load_receipt("pos_natureland")
TSUTA_RECEIPT = load_receipt("tsuta")
SANOOK_RECEIPT = load_receipt("sanook")

PARSE_FIXTURES = [
    ("clean", CLEAN_RECEIPT, 3),
    ("qty", QTY_RECEIPT, 3),
    ("codes", CODES_RECEIPT, 3),
    ("noisy", NOISY_RECEIPT, 2),
    ("discount", DISCOUNT_RECEIPT, 3),
]
