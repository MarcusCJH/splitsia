import pytest

from splitleh.parse_receipt import parse_receipt
from splitleh_telegram.split_builder import parsed_to_receipt
from tests.fixtures.load_receipts import POS_NATURELAND_RECEIPT


def test_parsed_to_receipt_matches_lite_charge_mapping():
    parsed = parse_receipt(POS_NATURELAND_RECEIPT)
    items = [
        {
            "id": f"i{idx}",
            "name": it.name,
            "unitPrice": it.unit_price,
            "quantity": it.quantity,
            "totalPrice": it.total_price,
        }
        for idx, it in enumerate(parsed.items, start=1)
    ]
    charges = [
        {"type": c.type, "label": c.label, "amount": c.amount}
        for c in parsed.charges
    ]

    receipt = parsed_to_receipt(items, charges)

    svc = next(c for c in receipt.charges if c.id == "svc")
    gst = next(c for c in receipt.charges if c.id == "gst")
    disc = next(c for c in receipt.charges if c.id == "discount")

    assert svc.amount == pytest.approx(37.18)
    assert gst.amount == pytest.approx(36.81)
    assert disc.amount == pytest.approx(-136.8)
    assert receipt.total == pytest.approx(445.79)
