"""Format split results for Telegram messages."""

from __future__ import annotations

import html
from decimal import Decimal

from splitleh.types import PersonResult, SplitResult


def _esc(text: str) -> str:
    return html.escape(str(text))


def _money(value: float | Decimal | int) -> str:
    return f"{float(value):.2f}"


def format_item_list(
    items: list[dict],
    charges: list[dict],
    *,
    active_person_name: str | None = None,
    proxy_mode: bool = False,
) -> str:
    lines = ["📋 <b>Items detected:</b>"]
    if proxy_mode and active_person_name:
        lines.append(f"Assigning for: <b>{_esc(active_person_name)}</b>")
        lines.append("<i>Tap a name, then tap items. Shared dishes → ×2.</i>")
    for idx, item in enumerate(items, start=1):
        lines.append(
            f"{idx}. {_esc(item['name'])} - ${_money(item['totalPrice'])}"
        )
    if charges:
        lines.append("")
        lines.append("<b>Charges:</b>")
        for c in charges:
            label = c.get("label") or c["type"]
            lines.append(f"• {_esc(label)}: ${_money(c['amount'])}")
    lines.append("")
    if proxy_mode:
        lines.append("When done: <b>Done picking</b>.")
    else:
        lines.append(
            "Tap your items - <b>×2</b> means shared. "
            "Or <code>/people Alice Bob</code> to assign for others."
        )
    return "\n".join(lines)


def format_item_list_plain(
    items: list[dict],
    charges: list[dict],
    *,
    active_person_name: str | None = None,
    proxy_mode: bool = False,
) -> str:
    """Fallback when HTML/Markdown parsing fails."""
    lines = ["📋 Items detected:"]
    if proxy_mode and active_person_name:
        lines.append(f"Assigning for: {active_person_name}")
        lines.append("Tap a name, then tap items. Shared dishes → ×2.")
    for idx, item in enumerate(items, start=1):
        lines.append(f"{idx}. {item['name']} - ${_money(item['totalPrice'])}")
    if charges:
        lines.append("")
        lines.append("Charges:")
        for c in charges:
            label = c.get("label") or c["type"]
            lines.append(f"• {label}: ${_money(c['amount'])}")
    lines.append("")
    if proxy_mode:
        lines.append("When done: Done picking.")
    else:
        lines.append(
            "Tap your items - ×2 means shared. "
            "Or /people Alice Bob to assign for others."
        )
    return "\n".join(lines)


def format_split_result(result: SplitResult) -> str:
    lines = ["💰 <b>Split results:</b>"]
    for pr in result.person_results:
        mention = _esc(_person_label(pr))
        item_names = ", ".join(_esc(s.item.name) for s in pr.item_shares) or "-"
        lines.append(f"\n{mention} - <b>${pr.total:.2f}</b>")
        lines.append(f"  Items: {item_names}")
        if pr.charge_shares:
            chg = ", ".join(
                f"{_esc(cs.charge.label)} ${cs.amount:.2f}" for cs in pr.charge_shares
            )
            lines.append(f"  Charges: {chg}")

    if result.unassigned_items:
        lines.append("\n⚠️ <b>Unassigned:</b>")
        for item in result.unassigned_items:
            lines.append(f"  • {_esc(item.name)} ${item.total_price:.2f}")

    return "\n".join(lines)


def _person_label(pr: PersonResult) -> str:
    return pr.person.name
