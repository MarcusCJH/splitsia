"""Telegram webhook Lambda entrypoint."""

from __future__ import annotations

import asyncio
import json
import os

import boto3
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aws_lambda_powertools import Logger, Tracer

try:
    from router import _post_claiming_message, router
except ImportError:
    from splitleh_telegram.router import _post_claiming_message, router

logger = Logger(service="splitleh-telegram")
tracer = Tracer(service="splitleh-telegram")

dp = Dispatcher()
dp.include_router(router)
_cached_token: str | None = None
_cached_webhook_secret: str | None = None


def _get_ssm_param(name: str) -> str:
    resp = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)
    return resp["Parameter"]["Value"]


def _load_bot_token() -> str:
    global _cached_token
    if _cached_token:
        return _cached_token

    direct = os.environ.get("TELEGRAM_BOT_TOKEN")
    if direct:
        _cached_token = direct
        return direct

    param_name = os.environ.get("TELEGRAM_BOT_TOKEN_PARAM_NAME")
    if not param_name:
        return ""

    _cached_token = _get_ssm_param(param_name)
    return _cached_token


def _load_webhook_secret() -> str:
    global _cached_webhook_secret
    if _cached_webhook_secret is not None:
        return _cached_webhook_secret

    direct = os.environ.get("SPLITLEH_WEBHOOK_SECRET")
    if direct:
        _cached_webhook_secret = direct
        return direct

    param_name = os.environ.get("TELEGRAM_WEBHOOK_SECRET_PARAM_NAME")
    if not param_name:
        _cached_webhook_secret = ""
        return ""

    _cached_webhook_secret = _get_ssm_param(param_name)
    return _cached_webhook_secret


async def _handle_webhook(event: dict) -> dict:
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    secret = headers.get("x-telegram-bot-api-secret-token", "")
    expected = _load_webhook_secret()
    if expected and secret != expected:
        return {"statusCode": 401, "body": ""}

    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode()
    update = Update.model_validate(json.loads(body))

    token = _load_bot_token()
    if not token:
        logger.error("bot token not configured")
        return {"statusCode": 500, "body": "Bot not configured"}

    bot = Bot(token=token)
    try:
        await dp.feed_update(bot, update)
    finally:
        await bot.session.close()

    return {"statusCode": 200, "body": ""}


async def _handle_ocr_complete(event: dict) -> dict:
    chat_id = event["chatId"]
    split_id = event["splitId"]
    error = event.get("failed")

    token = _load_bot_token()
    if not token:
        logger.error("bot token not configured")
        return {"ok": False}

    bot = Bot(token=token)
    try:
        if error:
            await bot.send_message(chat_id, f"❌ Receipt scan failed: {error}")
        else:
            await _post_claiming_message(bot, chat_id, split_id)
    except Exception:
        logger.exception("ocr_complete handler failed")
        try:
            await bot.send_message(
                chat_id,
                "❌ Could not post items to chat. Try /scan again or use SplitLeh Lite.",
            )
        except Exception:
            logger.exception("could not send failure notice")
    finally:
        await bot.session.close()
    return {"ok": True}


@logger.inject_lambda_context(log_event=False)
@tracer.capture_lambda_handler
def handler(event: dict, context) -> dict:
    if isinstance(event, str):
        event = json.loads(event)
    if event.get("type") == "ocr_complete":
        return asyncio.run(_handle_ocr_complete(event))
    return asyncio.run(_handle_webhook(event))
