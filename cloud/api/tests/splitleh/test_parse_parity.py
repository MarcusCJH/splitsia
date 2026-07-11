import json

import pytest

from splitleh.parse_receipt import parse_receipt
from tests.fixtures.load_receipts import GOLDEN_PATH, load_receipt


def _golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["clean", "codes", "qty", "discount_positive", "low_conf"])
def test_parse_matches_golden(name: str):
    expected = _golden()[name]
    result = parse_receipt(load_receipt(name))

    if "itemCount" in expected:
        assert len(result.items) == expected["itemCount"]

    if "itemCountMin" in expected:
        assert len(result.items) >= expected["itemCountMin"]

    for spec in expected.get("items", []):
        match = next(
            (it for it in result.items if it.name == spec["name"]),
            None,
        )
        assert match is not None, f"missing item {spec['name']}"
        if "totalPrice" in spec:
            assert match.total_price == pytest.approx(spec["totalPrice"])
        if "quantity" in spec:
            assert match.quantity == spec["quantity"]

    for spec in expected.get("charges", []):
        charge = next((c for c in result.charges if c.type == spec["type"]), None)
        assert charge is not None, f"missing charge {spec['type']}"
        assert charge.amount == pytest.approx(spec["amount"])

    if expected.get("hasNegativeDiscount"):
        assert any(c.type == "discount" and c.amount < 0 for c in result.charges)

    if "lowConfidenceItem" in expected:
        low = next((it for it in result.items if it.name == expected["lowConfidenceItem"]), None)
        assert low is not None
        assert low.confidence == "low"

    if "serviceCharge" in expected:
        svc = next((c for c in result.charges if c.type == "service_charge"), None)
        assert svc is not None
        assert svc.amount == pytest.approx(expected["serviceCharge"])

    if "gst" in expected:
        gst = next((c for c in result.charges if c.type == "gst"), None)
        assert gst is not None
        assert gst.amount == pytest.approx(expected["gst"])

    if "discount" in expected:
        disc = next((c for c in result.charges if c.type == "discount"), None)
        assert disc is not None
        assert disc.amount == pytest.approx(expected["discount"])

    if "total" in expected:
        total = next((c for c in result.charges if c.type == "total"), None)
        assert total is not None
        assert total.amount == pytest.approx(expected["total"])
