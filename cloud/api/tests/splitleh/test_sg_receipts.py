"""Real Singapore F&B OCR fixtures - tsuta, sanook, natureland."""

import pytest

from splitleh.parse_receipt import parse_receipt
from splitleh.repair_receipt import repair_parsed_receipt
from tests.fixtures.load_receipts import POS_NATURELAND_RECEIPT, load_receipt


def _parse(name: str):
    text = load_receipt(name)
    return repair_parsed_receipt(parse_receipt(text), text)


def test_natureland_pos_footer():
    parsed = _parse("pos_natureland")
    assert len(parsed.items) == 4
    assert parsed.charges[-1].type == "total"
    assert parsed.charges[-1].amount == pytest.approx(445.79)
    svc = next(c for c in parsed.charges if c.type == "service_charge")
    assert svc.amount == pytest.approx(37.18)


def test_tsuta_staff_discount_before_service():
    parsed = _parse("tsuta")
    pho = next(it for it in parsed.items if "slice beef pho" in it.name.lower())
    assert pho.quantity == 3
    assert pho.total_price == pytest.approx(44.40)

    subtotal = next(c for c in parsed.charges if c.type == "subtotal")
    assert subtotal.amount == pytest.approx(226.50)

    discount = next(c for c in parsed.charges if c.type == "discount")
    assert discount.amount == pytest.approx(-22.65)

    svc = next(c for c in parsed.charges if c.type == "service_charge")
    assert svc.amount == pytest.approx(20.39)

    total = next(c for c in parsed.charges if c.type == "total")
    assert total.amount == pytest.approx(244.42)

    assert not any("krisplus" in it.name.lower() for it in parsed.items)


def test_sanook_infers_sg_footer_when_labels_have_no_amounts():
    parsed = _parse("sanook")
    subtotal = next(c for c in parsed.charges if c.type == "subtotal")
    assert subtotal.amount == pytest.approx(239.10)

    svc = next((c for c in parsed.charges if c.type == "service_charge"), None)
    gst = next((c for c in parsed.charges if c.type == "gst"), None)
    assert svc is not None
    assert gst is not None
    assert svc.amount == pytest.approx(23.91)
    assert gst.amount == pytest.approx(23.67)

    chicken = next(
        (it for it in parsed.items if "deep" in it.name.lower() and "chicken" in it.name.lower()),
        None,
    )
    assert chicken is not None
    assert chicken.total_price == pytest.approx(9.90)


def test_hawker_closed_bill_does_not_invent_service_or_gst():
    """Sub Total == Net Total and no S/C/GST lines - do not invent charges."""
    parsed = _parse("hawker_closed")
    assert [(it.name, it.quantity, it.total_price) for it in parsed.items] == [
        ("MILO ICE", 2, 6.2),
        ("PRATA RK SPL", 2, 18.4),
    ]
    assert not any(c.type == "service_charge" for c in parsed.charges)
    assert not any(c.type == "gst" for c in parsed.charges)
    subtotal = next(c for c in parsed.charges if c.type == "subtotal")
    total = next(c for c in parsed.charges if c.type == "total")
    assert subtotal.amount == pytest.approx(24.60)
    assert total.amount == pytest.approx(24.60)


def test_natureland_fixture_still_loads_from_shared_path():
    assert "Natureland Cafe" in POS_NATURELAND_RECEIPT
