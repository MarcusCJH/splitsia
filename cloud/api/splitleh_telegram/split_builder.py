"""Build SplitSession from Telegram split + user claims."""

from __future__ import annotations

from splitleh.types import (
    ItemAssignment,
    Person,
    Receipt,
    ReceiptItem,
    SplitSession,
)
from splitleh.calculate_split import calculate_split
from splitleh.receipt_reconcile import charges_from_parsed_dicts


def parsed_to_receipt(items: list[dict], charges: list[dict]) -> Receipt:
    receipt_items = [
        ReceiptItem(
            id=it["id"],
            name=it["name"],
            unit_price=float(it["unitPrice"]),
            quantity=int(it.get("quantity", 1)),
            total_price=float(it["totalPrice"]),
        )
        for it in items
    ]
    receipt_charges = charges_from_parsed_dicts(charges)
    detected_subtotal = next(
        (float(c["amount"]) for c in charges if c["type"] == "subtotal"),
        None,
    )
    subtotal = detected_subtotal if detected_subtotal is not None else sum(
        i.total_price for i in receipt_items
    )
    total_charge = next((float(c["amount"]) for c in charges if c["type"] == "total"), None)
    charge_sum = sum(c.amount for c in receipt_charges)
    total = total_charge if total_charge is not None else subtotal + charge_sum
    return Receipt(
        items=receipt_items,
        charges=receipt_charges,
        subtotal=subtotal,
        total=total,
        currency="SGD",
    )


def build_session(
    split_id: str,
    items: list[dict],
    charges: list[dict],
    user_rows: list[dict],
) -> SplitSession:
    people = [
        Person(
            id=str(row.get("SK", "").split("#USER#")[-1] or row.get("userId", "")),
            name=_display_name(row),
            color="#000000",
        )
        for row in user_rows
    ]
    participant_ids = [p.id for p in people]

    assignments = [
        ItemAssignment(item_id=item_id, person_ids=[])
        for item_id in {it["id"] for it in items}
    ]
    id_to_assignment = {a.item_id: a for a in assignments}
    for row in user_rows:
        user_id = str(row.get("SK", "").split("#USER#")[-1])
        for item_id in row.get("claimedItemIds", []):
            if item_id in id_to_assignment:
                id_to_assignment[item_id].person_ids.append(user_id)

    if participant_ids:
        for assignment in assignments:
            if not assignment.person_ids:
                assignment.person_ids = participant_ids[:]

    return SplitSession(
        id=split_id,
        title="Telegram split",
        split_mode="itemized",
        created_at=0,
        updated_at=0,
        people=people,
        assignments=list(assignments),
        receipt=parsed_to_receipt(items, charges),
    )


def compute_split(
    split_id: str,
    items: list[dict],
    charges: list[dict],
    user_rows: list[dict],
):
    session = build_session(split_id, items, charges, user_rows)
    return calculate_split(session)


def _display_name(row: dict) -> str:
    username = row.get("username")
    if username:
        return f"@{username}"
    return row.get("displayName") or "Someone"
