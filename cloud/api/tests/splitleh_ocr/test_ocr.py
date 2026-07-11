import pytest

from splitleh.parse_receipt import parse_receipt
from splitleh_ocr.bedrock_provider import structured_data_to_parse_result
from splitleh_ocr.pick_parse import (
    average_confidence,
    line_item_count,
    needs_bedrock_fallback,
    parsed_result_looks_valid,
    pick_best_parse,
    score_parse_result,
)
from splitleh_ocr.normalize import (
    expense_documents_blocks_to_text,
    expense_documents_to_parse_result,
    expense_documents_to_text,
    parse_receipt_text,
)

NATURELAND_TEXTRACT = [
    {
        "SummaryFields": [
            {
                "Type": {"Text": "SUBTOTAL"},
                "LabelDetection": {"Text": "SUBTOTAL"},
                "ValueDetection": {"Text": "$371.80"},
            },
            {
                "Type": {"Text": "SERVICE_CHARGE"},
                "LabelDetection": {"Text": "10% Svr Chrg"},
                "ValueDetection": {"Text": "$37.18"},
            },
            {
                "Type": {"Text": "OTHER"},
                "LabelDetection": {"Text": "ITEM DISC 30%"},
                "ValueDetection": {"Text": "($136.80)"},
            },
            {
                "Type": {"Text": "TAX"},
                "LabelDetection": {"Text": "9% GST"},
                "ValueDetection": {"Text": "$36.81"},
            },
            {
                "Type": {"Text": "TOTAL"},
                "LabelDetection": {"Text": "TOTAL"},
                "ValueDetection": {"Text": "$445.79"},
            },
            {
                "Type": {"Text": "AMOUNT_PAID"},
                "ValueDetection": {"Text": "$445.79"},
            },
        ],
        "LineItemGroups": [
            {
                "LineItems": [
                    {
                        "LineItemExpenseFields": [
                            {
                                "Type": {"Text": "ITEM"},
                                "ValueDetection": {"Text": "(Promo) Guinness", "Confidence": 96.0},
                            },
                            {
                                "Type": {"Text": "QUANTITY"},
                                "ValueDetection": {"Text": "1", "Confidence": 95.0},
                            },
                            {
                                "Type": {"Text": "PRICE"},
                                "ValueDetection": {"Text": "$13.00", "Confidence": 97.0},
                            },
                        ]
                    },
                    {
                        "LineItemExpenseFields": [
                            {
                                "Type": {"Text": "ITEM"},
                                "ValueDetection": {"Text": "Apple Juice", "Confidence": 96.0},
                            },
                            {
                                "Type": {"Text": "QUANTITY"},
                                "ValueDetection": {"Text": "1", "Confidence": 95.0},
                            },
                            {
                                "Type": {"Text": "PRICE"},
                                "ValueDetection": {"Text": "$5.00", "Confidence": 97.0},
                            },
                        ]
                    },
                    {
                        "LineItemExpenseFields": [
                            {
                                "Type": {"Text": "ITEM"},
                                "ValueDetection": {"Text": "Ki No Bi Btl", "Confidence": 96.0},
                            },
                            {
                                "Type": {"Text": "QUANTITY"},
                                "ValueDetection": {"Text": "2", "Confidence": 95.0},
                            },
                            {
                                "Type": {"Text": "PRICE"},
                                "ValueDetection": {"Text": "$456.00", "Confidence": 97.0},
                            },
                        ]
                    },
                    {
                        "LineItemExpenseFields": [
                            {
                                "Type": {"Text": "ITEM"},
                                "ValueDetection": {"Text": "Moscato (WP)", "Confidence": 96.0},
                            },
                            {
                                "Type": {"Text": "QUANTITY"},
                                "ValueDetection": {"Text": "2", "Confidence": 95.0},
                            },
                            {
                                "Type": {"Text": "PRICE"},
                                "ValueDetection": {"Text": "$22.00", "Confidence": 97.0},
                            },
                        ]
                    },
                ]
            }
        ],
    }
]


def test_structured_data_natureland_shape():
    data = {
        "raw_lines": ["Natureland Cafe", "1 Guinness $13.00"],
        "items": [
            {"name": "(Promo) Guinness", "quantity": 1, "total_price": 13.0},
            {"name": "Apple Juice", "quantity": 1, "total_price": 5.0},
            {"name": "Ki No Bi Btl", "quantity": 2, "total_price": 456.0},
            {"name": "Moscato (WP)", "quantity": 2, "total_price": 22.0},
        ],
        "charges": [
            {"type": "subtotal", "label": "SUBTOTAL", "amount": 371.80},
            {"type": "discount", "label": "ITEM DISC 30%", "amount": -136.80},
            {"type": "service_charge", "label": "10% Svr Chrg", "amount": 37.18},
            {"type": "gst", "label": "9% GST", "amount": 36.81},
            {"type": "total", "label": "TOTAL", "amount": 445.79},
        ],
    }
    parsed = structured_data_to_parse_result(data)
    assert len(parsed.items) == 4
    assert parsed.items[0].name == "(Promo) Guinness"
    assert parsed.charges[-1].type == "total"
    assert parsed.charges[-1].amount == pytest.approx(445.79)


def test_expense_documents_to_parse_result_natureland():
    parsed = expense_documents_to_parse_result(NATURELAND_TEXTRACT)
    assert parsed_result_looks_valid(parsed)
    assert len(parsed.items) == 4
    assert parsed.items[2].name == "Ki No Bi Btl"
    assert parsed.items[2].quantity == 2
    assert not any(it.name.startswith("AMOUNT_PAID") for it in parsed.items)
    assert not any(it.name.startswith("SERVICE_CHARGE") for it in parsed.items)
    subtotal = next(c for c in parsed.charges if c.type == "subtotal")
    assert subtotal.amount == pytest.approx(371.80)
    assert subtotal.label == "SUBTOTAL"
    discount = next(c for c in parsed.charges if c.type == "discount")
    assert discount.amount == pytest.approx(-136.80)


def test_expense_documents_to_text_uses_labels_not_field_codes():
    text = expense_documents_to_text(NATURELAND_TEXTRACT)
    assert "SERVICE_CHARGE:" not in text
    assert "10% Svr Chrg $37.18" in text
    assert "Guinness" in text


def test_old_summary_field_text_no_longer_parsed_as_items():
    bad_text = "\n".join(
        [
            "AMOUNT_PAID: $445.79",
            "SERVICE_CHARGE: $37.18",
            "OTHER: ($136.80)",
            "Ki No Bi Btl $456.00 2 2 Ki No Bi Btl $456.00",
            "SUBTOTAL: $371.80",
            "TAX: $36.81",
            "TOTAL: $445.79",
        ]
    )
    parsed = parse_receipt(bad_text)
    assert not parsed_result_looks_valid(parsed)


def test_expense_documents_to_text():
    documents = [
        {
            "SummaryFields": [
                {
                    "Type": {"Text": "TOTAL"},
                    "ValueDetection": {"Text": "$45.79"},
                }
            ],
            "LineItemGroups": [
                {
                    "LineItems": [
                        {
                            "LineItemExpenseFields": [
                                {"ValueDetection": {"Text": "Guinness"}},
                                {"ValueDetection": {"Text": "$13.00"}},
                            ]
                        }
                    ]
                }
            ],
        }
    ]
    text = expense_documents_to_text(documents)
    assert "Total $45.79" in text
    assert "Guinness $13.00" in text


def test_pick_best_prefers_structured_over_field_code_text():
    structured = expense_documents_to_parse_result(NATURELAND_TEXTRACT)
    bad_text = "\n".join(
        [
            "AMOUNT_PAID: $445.79",
            "SERVICE_CHARGE: $37.18",
            "Ki No Bi Btl $456.00",
        ]
    )
    text_parsed = parse_receipt_text(bad_text)
    picked = pick_best_parse([("text", text_parsed), ("structured", structured)])
    assert picked is not None
    assert picked[0] == "structured"
    assert len(picked[1].items) == 4


def test_single_item_receipt_scores_acceptable():
    parsed = parse_receipt_text("1 Latte $6.50\nTOTAL $6.50")
    assert score_parse_result(parsed) >= 12.0
    assert parsed_result_looks_valid(parsed)


def test_blocks_to_text_reads_raw_lines():
    documents = [
        {
            "Blocks": [
                {"BlockType": "LINE", "Text": "Joe's Cafe"},
                {"BlockType": "WORD", "Text": "skip"},
                {"BlockType": "LINE", "Text": "1 Burger $12.00"},
            ]
        }
    ]
    text = expense_documents_blocks_to_text(documents)
    assert "Joe's Cafe" in text
    assert "Burger" in text


def test_needs_bedrock_fallback_low_confidence():
    documents = [
        {
            "LineItemGroups": [
                {
                    "LineItems": [
                        {
                            "LineItemExpenseFields": [
                                {"ValueDetection": {"Text": "Item", "Confidence": 50.0}},
                            ]
                        },
                        {
                            "LineItemExpenseFields": [
                                {"ValueDetection": {"Text": "Item 2", "Confidence": 55.0}},
                            ]
                        },
                    ]
                }
            ]
        }
    ]
    assert line_item_count(documents) == 2
    assert average_confidence(documents) == pytest.approx(0.525)
    assert needs_bedrock_fallback(documents) is True
