"""OCR Lambda - invoked by telegram Lambda with {bucket, s3Key, chatId, splitId}."""

from __future__ import annotations

import json
import os

import boto3
from aws_lambda_powertools import Logger, Tracer

from shared.split_store import update_split
try:
    from run import delete_s3_object, run_ocr
except ImportError:
    from splitleh_ocr.run import delete_s3_object, run_ocr

logger = Logger(service="splitleh-ocr")
tracer = Tracer(service="splitleh-ocr")
BUCKET = os.environ["SPLITLEH_RECEIPTS_BUCKET"]


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
def handler(event: dict, context) -> dict:
    if isinstance(event, str):
        event = json.loads(event)

    chat_id = event["chatId"]
    split_id = event["splitId"]
    s3_key = event["s3Key"]
    bucket = event.get("bucket", BUCKET)

    try:
        raw_text, provider, parsed = run_ocr(bucket, s3_key)
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
        update_split(
            chat_id,
            split_id,
            status="claiming",
            rawText=raw_text,
            provider=provider,
            items=items,
            charges=charges,
            warnings=parsed.warnings,
        )
        delete_s3_object(bucket, s3_key)
        _notify_telegram(chat_id, split_id)
        return {"ok": True, "itemCount": len(items)}
    except Exception as exc:
        logger.exception("ocr failed")
        try:
            update_split(chat_id, split_id, status="failed", error=str(exc))
        except Exception:
            logger.exception("could not persist failed status")
        _notify_telegram(chat_id, split_id, error=str(exc))
        raise


def _notify_telegram(chat_id: int | str, split_id: str, *, error: str | None = None) -> None:
    fn = os.environ.get("SPLITLEH_TELEGRAM_FUNCTION", "splitleh_telegram")
    payload: dict = {"type": "ocr_complete", "chatId": chat_id, "splitId": split_id}
    if error:
        payload["failed"] = error
    try:
        boto3.client("lambda").invoke(
            FunctionName=fn,
            InvocationType="Event",
            Payload=json.dumps(payload).encode(),
        )
    except Exception:
        logger.exception("failed to notify telegram")
