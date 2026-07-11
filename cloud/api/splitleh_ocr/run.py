"""Run receipt OCR on an S3 object - Textract primary, Bedrock fallback."""

from __future__ import annotations

import boto3
from aws_lambda_powertools import Tracer

from shared.scan_budget import ScanBudgetExceeded, assert_scan_allowed, increment_scan_count
from splitleh.parse_receipt import parse_receipt
from splitleh.repair_receipt import repair_parsed_receipt
from splitleh.types import ParseResult

try:
    from bedrock_provider import extract_receipt_structured, transcribe_receipt_image
    from normalize import (
        expense_documents_blocks_to_text,
        expense_documents_to_parse_result,
        expense_documents_to_text,
        parse_receipt_text,
    )
    from pick_parse import pick_best_parse
    from textract_provider import analyze_expense
except ImportError:
    from splitleh_ocr.bedrock_provider import extract_receipt_structured, transcribe_receipt_image
    from splitleh_ocr.normalize import (
        expense_documents_blocks_to_text,
        expense_documents_to_parse_result,
        expense_documents_to_text,
        parse_receipt_text,
    )
    from splitleh_ocr.pick_parse import pick_best_parse
    from splitleh_ocr.textract_provider import analyze_expense

tracer = Tracer(service="splitleh-ocr")


@tracer.capture_method
def run_ocr(bucket: str, s3_key: str) -> tuple[str, str, ParseResult]:
    """Returns (raw_text, provider_name, parsed). Raises on total failure."""
    assert_scan_allowed()

    textract_error: Exception | None = None
    documents: list | None = None
    raw_text = ""

    try:
        documents = analyze_expense(bucket, s3_key)
        raw_text = expense_documents_to_text(documents)
    except Exception as exc:
        textract_error = exc

    if documents:
        picked = pick_best_parse(_textract_candidates(documents))
        if picked:
            _strategy, parsed = picked
            increment_scan_count()
            return raw_text, "textract", parsed

    try:
        raw_text, parsed = _run_bedrock(bucket, s3_key)
        if parsed.items:
            increment_scan_count()
            return raw_text, "bedrock", parsed
    except ScanBudgetExceeded:
        raise
    except Exception:
        pass

    if raw_text:
        parsed = parse_receipt_text(raw_text)
        if parsed.items:
            increment_scan_count()
            return raw_text, "textract", parsed

    if textract_error:
        raise textract_error
    raise RuntimeError("OCR returned no items")


def _textract_candidates(documents: list) -> list[tuple[str, ParseResult]]:
    """Try every Textract interpretation; caller picks the best score."""
    candidates: list[tuple[str, ParseResult]] = []

    structured = expense_documents_to_parse_result(documents)
    if structured.items:
        candidates.append(("structured", structured))

    line_text = expense_documents_to_text(documents, include_summary=False)
    if line_text:
        parsed = parse_receipt_text(line_text)
        if parsed.items:
            candidates.append(("line_items", parsed))

    labeled_text = expense_documents_to_text(documents, include_summary=True)
    if labeled_text and labeled_text != line_text:
        parsed = parse_receipt_text(labeled_text)
        if parsed.items:
            candidates.append(("labeled", parsed))

    blocks_text = expense_documents_blocks_to_text(documents)
    if blocks_text:
        parsed = parse_receipt_text(blocks_text)
        if parsed.items:
            candidates.append(("blocks", parsed))

    return candidates


def _run_bedrock(bucket: str, s3_key: str) -> tuple[str, ParseResult]:
    try:
        return extract_receipt_structured(bucket, s3_key)
    except Exception:
        raw_text = transcribe_receipt_image(bucket, s3_key)
        if not raw_text.strip():
            raise
        return raw_text, repair_parsed_receipt(parse_receipt(raw_text), raw_text)


def delete_s3_object(bucket: str, key: str) -> None:
    boto3.client("s3").delete_object(Bucket=bucket, Key=key)
