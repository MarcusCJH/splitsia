import json
from unittest.mock import AsyncMock, patch

import pytest

from splitleh_telegram.lambda_function import handler


@pytest.mark.parametrize(
    "headers,expected_status",
    [
        ({}, 401),
        ({"x-telegram-bot-api-secret-token": "wrong"}, 401),
        ({"x-telegram-bot-api-secret-token": "test-secret"}, 200),
    ],
    ids=["missing_secret", "wrong_secret", "valid_secret"],
)
def test_webhook_secret(headers, expected_status, monkeypatch, lambda_context):
    monkeypatch.setenv("SPLITLEH_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")

    update = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 1, "type": "private"},
            "from": {"id": 1, "is_bot": False, "first_name": "A"},
            "text": "/start",
        },
    }

    with patch("splitleh_telegram.lambda_function.dp.feed_update", new_callable=AsyncMock) as mock_feed:
        resp = handler(
            {
                "headers": headers,
                "body": json.dumps(update),
            },
            lambda_context,
        )
        assert resp["statusCode"] == expected_status
        if expected_status == 200:
            mock_feed.assert_awaited_once()
