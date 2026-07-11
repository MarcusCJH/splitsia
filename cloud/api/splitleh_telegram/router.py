"""Telegram bot command and callback handlers."""

from __future__ import annotations

import json
import os

import boto3
import httpx
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from shared.split_store import (
    clear_active_split,
    claim_counts as split_claim_counts,
    create_split,
    get_active_split_id,
    get_split,
    get_user_claims,
    list_split_users,
    normalize_claimed_ids,
    replace_proxy_people,
    resolve_claimer_id,
    save_user_claims,
    toggle_claim,
    update_split,
)

try:
    from formatters import format_item_list, format_item_list_plain, format_split_result
    from keyboards import build_item_keyboard
    from split_builder import compute_split
except ImportError:
    from splitleh_telegram.formatters import (
        format_item_list,
        format_item_list_plain,
        format_split_result,
    )
    from splitleh_telegram.keyboards import build_item_keyboard
    from splitleh_telegram.split_builder import compute_split

router = Router()

BUCKET = os.environ.get("SPLITLEH_RECEIPTS_BUCKET", "")
OCR_FUNCTION = os.environ.get("SPLITLEH_OCR_FUNCTION", "splitleh_ocr")
LITE_URL = "https://marcuscjh.github.io/splitleh/"

HELP_TEXT = (
    "👋 *SplitLeh Bot* - scan a receipt, assign items, split fairly.\n\n"
    "*Group (everyone taps their own):*\n"
    "/scan → photo → tap items → Done\n\n"
    "*Solo (you assign for friends):*\n"
    "/scan → photo → `/people Alice Bob Charlie`\n"
    "Tap a name, then tap their dishes → Done\n\n"
    "*Commands:*\n"
    "/scan /people /status /done /cancel\n\n"
    "⚠️ Photos go to AWS for OCR (unlike Lite).\n"
    f"On-device OCR: {LITE_URL}"
)


@router.message(Command("start", "help"))
async def cmd_start(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="Markdown")


@router.message(Command("scan"))
async def cmd_scan(message: Message) -> None:
    if not message.chat:
        return
    split_id = create_split(message.chat.id, scanner_user_id=message.from_user.id)
    await message.answer(
        f"📸 Send a receipt photo for split `{split_id}`.\n"
        "Images are processed on AWS and deleted after OCR.\n\n"
        "Solo tip: after items appear, send `/people Alice Bob` to assign for others.",
        parse_mode="Markdown",
    )


@router.message(Command("people"))
async def cmd_people(message: Message, bot: Bot) -> None:
    if not message.chat or not message.from_user or not message.text:
        return
    chat_id = message.chat.id
    split_id = get_active_split_id(chat_id)
    if not split_id:
        await message.answer("No active split. Use /scan first.")
        return
    split = get_split(chat_id, split_id)
    if not split or split.get("status") != "claiming":
        await message.answer("Wait until items are posted, then /people Name1 Name2 …")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Usage: `/people Alice Bob Charlie`\n"
            "Include yourself if you ate too, e.g. `/people Marcus Alice Bob`",
            parse_mode="Markdown",
        )
        return

    names = parts[1].replace(",", " ").split()
    try:
        people = replace_proxy_people(chat_id, split_id, names)
    except ValueError as exc:
        await message.answer(str(exc))
        return

    labels = ", ".join(p["name"] for p in people)
    await message.answer(
        f"👥 People set: *{labels}*\n"
        f"Active: *{people[0]['name']}* - tap dishes for them, then switch names.",
        parse_mode="Markdown",
    )
    await _refresh_claim_message(bot, chat_id=chat_id, split_id=split_id)


@router.message(F.photo)
async def on_photo(message: Message, bot: Bot) -> None:
    if not message.chat or not message.from_user:
        return

    chat_id = message.chat.id
    split_id = get_active_split_id(chat_id)
    if not split_id:
        split_id = create_split(chat_id, scanner_user_id=message.from_user.id)

    split = get_split(chat_id, split_id)
    if split and split.get("status") not in ("scanning", None):
        await message.answer("A split is already in progress. Use /cancel first.")
        return

    update_split(chat_id, split_id, status="scanning")
    await message.answer("⏳ Scanning receipt…")

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    if not file.file_path:
        await message.answer("Could not download photo from Telegram.")
        return

    url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.content

    s3_key = f"splitleh_receipts/{chat_id}/{split_id}/{photo.file_unique_id}.jpg"
    boto3.client("s3").put_object(
        Bucket=BUCKET,
        Key=s3_key,
        Body=data,
        ContentType="image/jpeg",
    )

    payload = {"chatId": chat_id, "splitId": split_id, "s3Key": s3_key, "bucket": BUCKET}
    if os.environ.get("SPLITLEH_OCR_SYNC", "false").lower() == "true":
        from splitleh_ocr.lambda_function import handler as ocr_handler

        ocr_handler(payload, None)
    else:
        boto3.client("lambda").invoke(
            FunctionName=OCR_FUNCTION,
            InvocationType="Event",
            Payload=json.dumps(payload).encode(),
        )
        await message.answer("OCR started - I'll post items when ready.")
        return

    await _post_claiming_message(bot, chat_id, split_id)


def _proxy_context(split: dict) -> tuple[bool, list[dict], str | None, str | None]:
    people = list(split.get("people") or [])
    proxy = split.get("claimMode") == "proxy" and bool(people)
    active_id = str(split["activePersonId"]) if split.get("activePersonId") else None
    active_name = None
    if active_id:
        active_name = next(
            (str(p.get("name")) for p in people if str(p.get("id")) == active_id),
            active_id,
        )
    return proxy, people, active_id, active_name


async def _post_claiming_message(bot: Bot, chat_id: int, split_id: str) -> None:
    split = get_split(chat_id, split_id)
    if not split or not split.get("items"):
        await bot.send_message(chat_id, "Could not parse items from receipt.")
        return

    items = split["items"]
    charges = split.get("charges", [])
    proxy, people, active_id, active_name = _proxy_context(split)
    selected: set[str] = set()
    if proxy and active_id:
        row = get_user_claims(chat_id, split_id, active_id)
        selected = set(normalize_claimed_ids(row.get("claimedItemIds")))
    counts = split_claim_counts(list_split_users(chat_id, split_id))
    keyboard = build_item_keyboard(
        split_id,
        items,
        selected_ids=selected,
        claim_counts=counts,
        people=people if proxy else None,
        active_person_id=active_id,
    )
    text = format_item_list(
        items, charges, active_person_name=active_name, proxy_mode=proxy
    )
    try:
        sent = await bot.send_message(
            chat_id,
            text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except TelegramBadRequest:
        sent = await bot.send_message(
            chat_id,
            format_item_list_plain(
                items, charges, active_person_name=active_name, proxy_mode=proxy
            ),
            reply_markup=keyboard,
        )
    update_split(chat_id, split_id, claimMessageId=sent.message_id)


async def _refresh_claim_message(
    bot: Bot,
    *,
    chat_id: int,
    split_id: str,
    page: int = 0,
) -> None:
    split = get_split(chat_id, split_id)
    if not split or not split.get("items"):
        return
    message_id = split.get("claimMessageId")
    if not message_id:
        await _post_claiming_message(bot, chat_id, split_id)
        return

    items = split["items"]
    charges = split.get("charges", [])
    proxy, people, active_id, active_name = _proxy_context(split)
    selected: set[str] = set()
    if proxy and active_id:
        row = get_user_claims(chat_id, split_id, active_id)
        selected = set(normalize_claimed_ids(row.get("claimedItemIds")))
    counts = split_claim_counts(list_split_users(chat_id, split_id))
    keyboard = build_item_keyboard(
        split_id,
        items,
        page=page,
        selected_ids=selected,
        claim_counts=counts,
        people=people if proxy else None,
        active_person_id=active_id,
    )
    text = format_item_list(
        items, charges, active_person_name=active_name, proxy_mode=proxy
    )
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=int(message_id),
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except TelegramBadRequest as exc:
        err = str(exc).lower()
        if "message is not modified" in err:
            return
        if "can't parse entities" in err or "parse" in err:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(message_id),
                text=format_item_list_plain(
                    items, charges, active_person_name=active_name, proxy_mode=proxy
                ),
                reply_markup=keyboard,
            )
            return
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=int(message_id),
                reply_markup=keyboard,
            )
        except TelegramBadRequest as inner:
            if "message is not modified" not in str(inner).lower():
                raise


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not message.chat:
        return
    split_id = get_active_split_id(message.chat.id)
    if not split_id:
        await message.answer("No active split. Use /scan to start.")
        return
    users = list_split_users(message.chat.id, split_id)
    if not users:
        await message.answer("Nobody has picks yet. Use /people or tap items.")
        return
    split = get_split(message.chat.id, split_id) or {}
    active = split.get("activePersonId")
    lines = ["*Picked so far:*"]
    for row in users:
        name = row.get("displayName") or row.get("username") or "User"
        uid = str(row.get("SK", "").split("#USER#")[-1])
        count = len(row.get("claimedItemIds", []))
        mark = " ← active" if uid == active else ""
        lines.append(f"• {name}: {count} item(s){mark}")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("done"))
async def cmd_done(message: Message) -> None:
    if not message.chat:
        return
    await finalize_split(message.chat.id, message)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    if not message.chat or not message.from_user:
        return
    split_id = get_active_split_id(message.chat.id)
    if not split_id:
        await message.answer("Nothing to cancel.")
        return
    split = get_split(message.chat.id, split_id)
    if split and split.get("scannerUserId") != message.from_user.id:
        await message.answer("Only the person who started the scan can /cancel.")
        return
    clear_active_split(message.chat.id)
    update_split(message.chat.id, split_id, status="cancelled")
    await message.answer("Split cancelled.")


@router.callback_query(F.data.startswith("a:"))
async def on_select_person(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.message or not callback.data:
        return
    _, split_id, person_id = callback.data.split(":", 2)
    chat_id = callback.message.chat.id
    split = get_split(chat_id, split_id)
    if not split or split.get("status") != "claiming":
        await callback.answer("Split no longer active.")
        return
    people = list(split.get("people") or [])
    if not any(str(p.get("id")) == person_id for p in people):
        await callback.answer("Unknown person.")
        return
    update_split(chat_id, split_id, activePersonId=person_id, claimMode="proxy")
    name = next(str(p["name"]) for p in people if str(p["id"]) == person_id)
    await callback.answer(f"Assigning for {name}")
    await _refresh_claim_message(bot, chat_id=chat_id, split_id=split_id)


@router.callback_query(F.data.startswith("c:"))
async def on_claim(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.message or not callback.from_user or not callback.data:
        return
    _, split_id, idx_str = callback.data.split(":", 2)
    chat_id = callback.message.chat.id
    split = get_split(chat_id, split_id)
    if not split or split.get("status") != "claiming":
        await callback.answer("Split no longer active.")
        return

    items = split.get("items", [])
    item_idx = int(idx_str)
    if item_idx < 0 or item_idx >= len(items):
        await callback.answer("Invalid item.")
        return

    claimer_id = resolve_claimer_id(split, callback.from_user.id)
    row = get_user_claims(chat_id, split_id, claimer_id)
    item_id = str(items[item_idx]["id"])
    claimed = toggle_claim(normalize_claimed_ids(row.get("claimedItemIds")), item_id)

    display_name = row.get("displayName") or callback.from_user.full_name
    if split.get("claimMode") == "proxy":
        people = list(split.get("people") or [])
        display_name = next(
            (str(p["name"]) for p in people if str(p["id"]) == claimer_id),
            display_name,
        )

    save_user_claims(
        chat_id,
        split_id,
        claimer_id,
        claimed_item_ids=claimed,
        display_name=str(display_name),
        username=callback.from_user.username
        if not str(claimer_id).startswith("p:")
        else None,
    )

    # Keep claim message id in sync if user taps an older keyboard.
    update_split(chat_id, split_id, claimMessageId=callback.message.message_id)

    picked = "Added ✓" if item_id in claimed else "Removed"
    others = split_claim_counts(list_split_users(chat_id, split_id)).get(item_id, 0)
    who = display_name
    if item_id in claimed and others > 1:
        await callback.answer(f"{picked} for {who} - {others} sharing.")
    else:
        await callback.answer(f"{picked} for {who} ({len(claimed)} items).")
    await _refresh_claim_message(bot, chat_id=chat_id, split_id=split_id)


@router.callback_query(F.data.startswith("j:"))
async def on_join(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.message or not callback.from_user or not callback.data:
        return
    split_id = callback.data.split(":", 1)[1]
    chat_id = callback.message.chat.id
    split = get_split(chat_id, split_id)
    if not split or split.get("status") != "claiming":
        await callback.answer("Split no longer active.")
        return
    if split.get("claimMode") == "proxy":
        await callback.answer("Proxy mode - use /people and tap names instead.")
        return

    user_id = callback.from_user.id
    row = get_user_claims(chat_id, split_id, user_id)
    save_user_claims(
        chat_id,
        split_id,
        user_id,
        claimed_item_ids=normalize_claimed_ids(row.get("claimedItemIds")),
        display_name=callback.from_user.full_name,
        username=callback.from_user.username,
    )
    update_split(chat_id, split_id, claimMessageId=callback.message.message_id)
    await callback.answer("You're in - shared items will be split equally.")
    await _refresh_claim_message(bot, chat_id=chat_id, split_id=split_id)


@router.callback_query(F.data.startswith("p:"))
async def on_page(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.message or not callback.data:
        return
    _, split_id, page_str = callback.data.split(":", 2)
    chat_id = callback.message.chat.id
    split = get_split(chat_id, split_id)
    if not split:
        await callback.answer("Split not found.")
        return
    update_split(chat_id, split_id, claimMessageId=callback.message.message_id)
    await _refresh_claim_message(
        bot, chat_id=chat_id, split_id=split_id, page=int(page_str)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("d:"))
async def on_done_button(callback: CallbackQuery) -> None:
    if not callback.message or not callback.data:
        return
    split_id = callback.data.split(":", 1)[1]
    await finalize_split(callback.message.chat.id, callback.message, split_id)
    await callback.answer()


async def finalize_split(chat_id: int, reply_target: Message, split_id: str | None = None) -> None:
    split_id = split_id or get_active_split_id(chat_id)
    if not split_id:
        await reply_target.answer("No active split.")
        return

    split = get_split(chat_id, split_id)
    if not split or not split.get("items"):
        await reply_target.answer("No items to split.")
        return

    users = list_split_users(chat_id, split_id)
    if not users:
        await reply_target.answer(
            "Nobody joined yet. Tap items, or `/people Alice Bob`, then Done.",
            parse_mode="Markdown",
        )
        return

    result = compute_split(split_id, split["items"], split.get("charges", []), users)
    text = format_split_result(result)
    update_split(chat_id, split_id, status="done")
    clear_active_split(chat_id)
    try:
        await reply_target.answer(text, parse_mode="HTML")
    except TelegramBadRequest:
        await reply_target.answer(text)
