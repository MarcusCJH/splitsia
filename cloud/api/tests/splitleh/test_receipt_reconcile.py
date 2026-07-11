import pytest

from splitleh.parse_receipt import parse_receipt
from splitleh.receipt_reconcile import charges_from_parse, extract_rate
from tests.fixtures.load_receipts import POS_NATURELAND_RECEIPT


def test_extract_rate_from_label():
    assert extract_rate("10% Svr Chrg") == pytest.approx(0.1)
    assert extract_rate("GST 9%") == pytest.approx(0.09)
    assert extract_rate("Service Charge") is None


def test_charges_from_parse_natureland():
    parsed = parse_receipt(POS_NATURELAND_RECEIPT)
    charges = charges_from_parse(parsed)

    svc = next(c for c in charges if c.id == "svc")
    gst = next(c for c in charges if c.id == "gst")
    disc = next(c for c in charges if c.id == "discount")

    assert svc.amount == pytest.approx(37.18)
    assert svc.rate == pytest.approx(0.1)
    assert gst.amount == pytest.approx(36.81)
    assert gst.rate == pytest.approx(0.09)
    assert disc.amount == pytest.approx(-136.8)


def test_rounding_charge_uses_none_strategy():
    parsed = parse_receipt(
        """
Burger $10.00
Rounding -0.02
Total $9.98
""".strip()
    )
    charges = charges_from_parse(parsed)
    rounding = next(c for c in charges if c.id == "rounding")
    assert rounding.split_strategy == "none"
    assert rounding.amount == pytest.approx(-0.02)
