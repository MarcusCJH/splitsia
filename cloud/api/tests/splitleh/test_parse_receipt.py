import pytest

from splitleh.parse_receipt import parse_receipt
from tests.fixtures.receipt_text import (
    CLEAN_RECEIPT,
    CODES_RECEIPT,
    DISCOUNT_POSITIVE_RECEIPT,
    LOW_CONF_RECEIPT,
    PARSE_FIXTURES,
    QTY_RECEIPT,
)


@pytest.mark.parametrize("name,text,min_items", PARSE_FIXTURES)
def test_parse_receipt_fixture_item_counts(name, text, min_items):
    result = parse_receipt(text)
    assert len(result.items) >= min_items


@pytest.mark.parametrize(
    "text,checks",
    [
        (
            CLEAN_RECEIPT,
            lambda r: (
                r.items[0].name == "Chicken Rice"
                and r.items[0].total_price == 3.5
                and any(c.type == "gst" for c in r.charges)
            ),
        ),
        (
            CODES_RECEIPT,
            lambda r: r.items[0].name == "Laksa" and r.items[2].name == "Mee Goreng",
        ),
        (
            QTY_RECEIPT,
            lambda r: r.items[0].quantity == 2 and r.items[1].quantity == 2,
        ),
        (
            DISCOUNT_POSITIVE_RECEIPT,
            lambda r: any(c.type == "discount" and c.amount < 0 for c in r.charges),
        ),
        (
            LOW_CONF_RECEIPT,
            lambda r: any(it.name == "Xz" and it.confidence == "low" for it in r.items),
        ),
    ],
    ids=["clean", "codes", "qty", "discount_negative", "low_confidence"],
)
def test_parse_receipt_cases(text, checks):
    assert checks(parse_receipt(text))
