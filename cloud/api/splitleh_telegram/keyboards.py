"""Build inline keyboards for item claiming (group self-claim or proxy people)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

ITEMS_PER_PAGE = 6
CALLBACK_MAX = 64


def _claim_data(split_id: str, item_idx: int) -> str:
    data = f"c:{split_id}:{item_idx}"
    if len(data) > CALLBACK_MAX:
        raise ValueError("callback_data too long")
    return data


def _person_data(split_id: str, person_id: str) -> str:
    data = f"a:{split_id}:{person_id}"
    if len(data) > CALLBACK_MAX:
        raise ValueError("callback_data too long")
    return data


def _item_button_label(
    *,
    global_idx: int,
    item: dict,
    claim_counts: dict[str, int] | None,
    selected_ids: set[str] | None = None,
) -> str:
    item_id = item["id"]
    price = float(item["totalPrice"])
    name = item["name"][:20]
    picked_by = (claim_counts or {}).get(item_id, 0)
    mine = "✓ " if selected_ids and item_id in selected_ids else ""
    suffix = f" ×{picked_by}" if picked_by else ""
    return f"{mine}#{global_idx + 1} {name} ${price:.2f}{suffix}"


def build_item_keyboard(
    split_id: str,
    items: list[dict],
    *,
    page: int = 0,
    selected_ids: set[str] | None = None,
    claim_counts: dict[str, int] | None = None,
    people: list[dict] | None = None,
    active_person_id: str | None = None,
) -> InlineKeyboardMarkup:
    start = page * ITEMS_PER_PAGE
    page_items = items[start : start + ITEMS_PER_PAGE]
    rows: list[list[InlineKeyboardButton]] = []

    if people:
        person_row: list[InlineKeyboardButton] = []
        for person in people[:8]:
            pid = str(person["id"])
            label = str(person.get("name") or pid)[:14]
            mark = "● " if pid == active_person_id else ""
            person_row.append(
                InlineKeyboardButton(
                    text=f"{mark}{label}",
                    callback_data=_person_data(split_id, pid),
                )
            )
            if len(person_row) == 4:
                rows.append(person_row)
                person_row = []
        if person_row:
            rows.append(person_row)

    for local_idx, item in enumerate(page_items):
        global_idx = start + local_idx
        label = _item_button_label(
            global_idx=global_idx,
            item=item,
            claim_counts=claim_counts,
            selected_ids=selected_ids,
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=_claim_data(split_id, global_idx),
                )
            ]
        )

    nav: list[InlineKeyboardButton] = []
    total_pages = max(1, (len(items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="◀ Prev", callback_data=f"p:{split_id}:{page - 1}")
        )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(text="Next ▶", callback_data=f"p:{split_id}:{page + 1}")
        )
    if nav:
        rows.append(nav)

    if not people:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🙋 In group (no items)",
                    callback_data=f"j:{split_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="✅ Done picking", callback_data=f"d:{split_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
