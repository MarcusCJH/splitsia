import pytest

from shared.split_store import toggle_claim
from splitleh_telegram.keyboards import build_item_keyboard


@pytest.mark.parametrize(
    "claimed,item_id,expected",
    [
        ([], "i1", ["i1"]),
        (["i1"], "i1", []),
        (["i1"], "i2", ["i1", "i2"]),
        (["i1", "i2"], "i1", ["i2"]),
    ],
    ids=["add", "remove", "add_second", "remove_first"],
)
def test_toggle_claim(claimed, item_id, expected):
    assert toggle_claim(claimed, item_id) == expected


def test_keyboard_callback_data_under_limit():
    items = [{"id": f"i{n}", "name": f"Item {n}", "totalPrice": 1.0} for n in range(8)]
    kb = build_item_keyboard("abc123", items)
    for row in kb.inline_keyboard:
        for btn in row:
            assert len(btn.callback_data) <= 64
