"""Port of lite/core/src/calculateSplit.ts."""

from __future__ import annotations

from splitleh.money import to_cents
from splitleh.types import (
    ChargeShare,
    ItemShare,
    PersonResult,
    ReceiptItem,
    SplitResult,
    SplitSession,
)


def distribute_in_cents(total_cents: int, weights: list[int | float]) -> list[int]:
    n = len(weights)
    if n == 0:
        return []
    if n == 1:
        return [total_cents]

    weight_sum = sum(weights)
    if weight_sum == 0:
        base = total_cents // n
        rem = total_cents - base * n
        return [base + (1 if i < rem else 0) for i in range(n)]

    exact = [(total_cents * w) / weight_sum for w in weights]
    floors = [int(x // 1) for x in exact]
    remainder = total_cents - sum(floors)

    ranked = sorted(
        enumerate(exact),
        key=lambda pair: (-(pair[1] - int(pair[1] // 1)), pair[0]),
    )
    result = floors[:]
    sign = 1 if remainder >= 0 else -1
    for k in range(abs(remainder)):
        result[ranked[k][0]] += sign
    return result


def calculate_split(session: SplitSession) -> SplitResult:
    receipt = session.receipt
    people = session.people
    assignments = session.assignments
    split_mode = session.split_mode

    assigned_ids = {
        a.item_id for a in assignments if a.person_ids
    }
    unassigned = [i for i in receipt.items if i.id not in assigned_ids]

    if not people:
        return SplitResult(
            person_results=[],
            unassigned_items=unassigned,
            assigned_total=0.0,
            receipt_total=receipt.total,
        )

    if split_mode == "equal":
        return _equal_split(session, unassigned)
    return _itemized_split(session, unassigned)


def _equal_split(session: SplitSession, unassigned: list[ReceiptItem]) -> SplitResult:
    receipt = session.receipt
    people = session.people
    n = len(people)
    even = [1] * n

    subtotal_per = distribute_in_cents(to_cents(receipt.subtotal), even)
    charge_per_charge = [
        distribute_in_cents(to_cents(c.amount), even) for c in receipt.charges
    ]

    person_results: list[PersonResult] = []
    for i, person in enumerate(people):
        charge_shares = [
            ChargeShare(charge=c, amount=charge_per_charge[ci][i] / 100)
            for ci, c in enumerate(receipt.charges)
        ]
        charges_total_cents = sum(charge_per_charge[ci][i] for ci in range(len(receipt.charges)))
        subtotal_cents = subtotal_per[i]
        person_results.append(
            PersonResult(
                person=person,
                item_shares=[],
                charge_shares=charge_shares,
                subtotal=subtotal_cents / 100,
                charges_total=charges_total_cents / 100,
                total=(subtotal_cents + charges_total_cents) / 100,
            )
        )

    return SplitResult(
        person_results=person_results,
        unassigned_items=unassigned,
        assigned_total=receipt.total,
        receipt_total=receipt.total,
    )


def _itemized_split(session: SplitSession, unassigned: list[ReceiptItem]) -> SplitResult:
    receipt = session.receipt
    people = session.people
    assignments = session.assignments

    item_shares: dict[str, list[tuple[ReceiptItem, int, int]]] = {p.id: [] for p in people}
    subtotal_cents: dict[str, int] = {p.id: 0 for p in people}

    for assignment in assignments:
        if not assignment.person_ids:
            continue
        item = next((i for i in receipt.items if i.id == assignment.item_id), None)
        if item is None:
            continue
        n = len(assignment.person_ids)
        shares = distribute_in_cents(to_cents(item.total_price), [1] * n)
        for idx, person_id in enumerate(assignment.person_ids):
            item_shares[person_id].append((item, shares[idx], n))
            subtotal_cents[person_id] += shares[idx]

    subtotal_weights = [subtotal_cents[p.id] for p in people]
    even = [1] * len(people)
    charge_shares: dict[str, list[tuple[object, int]]] = {p.id: [] for p in people}

    for charge in receipt.charges:
        if charge.split_strategy == "none":
            continue
        weights = even if charge.split_strategy == "equal" else subtotal_weights
        amounts = distribute_in_cents(to_cents(charge.amount), weights)
        for i, person in enumerate(people):
            charge_shares[person.id].append((charge, amounts[i]))

    person_results: list[PersonResult] = []
    for person in people:
        raw_items = item_shares[person.id]
        raw_charges = charge_shares[person.id]
        item_share_objs = [
            ItemShare(item=it, amount=amt / 100, out_of=out_of)
            for it, amt, out_of in raw_items
        ]
        charge_share_objs = [
            ChargeShare(charge=c, amount=amt / 100) for c, amt in raw_charges
        ]
        sub_c = sum(amt for _, amt, _ in raw_items)
        chg_c = sum(amt for _, amt in raw_charges)
        person_results.append(
            PersonResult(
                person=person,
                item_shares=item_share_objs,
                charge_shares=charge_share_objs,
                subtotal=sub_c / 100,
                charges_total=chg_c / 100,
                total=(sub_c + chg_c) / 100,
            )
        )

    assigned_total_cents = sum(to_cents(r.total) for r in person_results)
    return SplitResult(
        person_results=person_results,
        unassigned_items=unassigned,
        assigned_total=assigned_total_cents / 100,
        receipt_total=receipt.total,
    )
