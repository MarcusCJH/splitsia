from splitleh_telegram.formatters import format_item_list, format_item_list_plain


def test_format_item_list_escapes_html_in_names():
    text = format_item_list(
        [{"name": "Fish & Chips <extra>", "totalPrice": 12.5}],
        [{"type": "tax", "label": "GST & service", "amount": 1.13}],
    )
    assert "Fish &amp; Chips &lt;extra&gt;" in text
    assert "GST &amp; service" in text
    assert "/people" in text


def test_format_item_list_proxy_mode_shows_active_person():
    text = format_item_list(
        [{"name": "Milo", "totalPrice": 6.2}],
        [],
        active_person_name="Alice",
        proxy_mode=True,
    )
    assert "Assigning for: <b>Alice</b>" in text
    assert "/people" not in text


def test_format_item_list_plain_has_no_markup():
    text = format_item_list_plain(
        [{"name": "Fish & Chips", "totalPrice": 12.5}],
        [],
    )
    assert "Fish & Chips" in text
    assert "&amp;" not in text
