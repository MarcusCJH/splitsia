import pytest

from splitleh.calculate_split import calculate_split
from splitleh.types import Charge, ItemAssignment, Person, Receipt, ReceiptItem, SplitSession


def _item(iid: str, name: str, price: float, qty: int = 1) -> ReceiptItem:
    return ReceiptItem(
        id=iid,
        name=name,
        unit_price=price / qty,
        quantity=qty,
        total_price=price,
    )


def _person(pid: str, name: str) -> Person:
    return Person(id=pid, name=name, color="#000")


def _charge(
    cid: str,
    ctype: str,
    amount: float,
    strategy: str = "proportional",
) -> Charge:
    return Charge(
        id=cid,
        type=ctype,
        label=cid,
        amount=amount,
        split_strategy=strategy,
    )


def _session(**kwargs) -> SplitSession:
    items = kwargs.get("items", [])
    charges = kwargs.get("charges", [])
    subtotal = sum(i.total_price for i in items)
    total = subtotal + sum(c.amount for c in charges)
    receipt = kwargs.get(
        "receipt",
        Receipt(
            items=items,
            charges=charges,
            subtotal=subtotal,
            total=total,
            currency="SGD",
        ),
    )
    return SplitSession(
        id="test",
        title="Test",
        split_mode=kwargs.get("split_mode", "itemized"),
        created_at=0,
        updated_at=0,
        people=kwargs.get("people", []),
        assignments=kwargs.get("assignments", []),
        receipt=receipt,
    )


@pytest.mark.parametrize(
    "people,assignments,items,charges,expected_totals",
    [
        pytest.param(
            [_person("p1", "Alice"), _person("p2", "Bob")],
            [{"itemId": "i1", "personIds": ["p1", "p2"]}],
            [_item("i1", "Pizza", 9.0)],
            [],
            [4.5, 4.5],
            id="shared_item_two_ways",
        ),
        pytest.param(
            [_person("p1", "A"), _person("p2", "B"), _person("p3", "C")],
            [{"itemId": "i1", "personIds": ["p1", "p2", "p3"]}],
            [_item("i1", "Shared", 10.0)],
            [],
            [3.34, 3.33, 3.33],
            id="shared_item_three_way_remainder",
        ),
        pytest.param(
            [_person("p1", "Alice"), _person("p2", "Bob")],
            [
                {"itemId": "iA", "personIds": ["p1"]},
                {"itemId": "iB", "personIds": ["p2"]},
            ],
            [_item("iA", "Burger", 10.0), _item("iB", "Fries", 5.0)],
            [_charge("disc", "discount", -3.0)],
            [8.0, 4.0],
            id="discount_proportional",
        ),
    ],
)
def test_calculate_split_cases(people, assignments, items, charges, expected_totals):
    s = _session(
        people=people,
        items=items,
        charges=charges,
        assignments=[
            ItemAssignment(item_id=a["itemId"], person_ids=a["personIds"])
            for a in assignments
        ],
    )
    result = calculate_split(s)
    totals = [round(r.total, 2) for r in result.person_results]
    assert totals == expected_totals


def test_no_people_returns_empty():
    s = _session(
        people=[],
        items=[_item("i1", "X", 5.0)],
        assignments=[],
    )
    result = calculate_split(s)
    assert result.person_results == []
    assert len(result.unassigned_items) == 1


def test_rounding_charge_not_distributed():
    s = _session(
        people=[_person("p1", "Alice")],
        items=[_item("i1", "Burger", 10.0)],
        charges=[_charge("rnd", "rounding", -0.02, "none")],
        assignments=[ItemAssignment(item_id="i1", person_ids=["p1"])],
    )
    result = calculate_split(s)
    assert result.person_results[0].total == pytest.approx(10.0)
    assert result.person_results[0].charge_shares == []


def test_equal_mode_splits_evenly():
    s = _session(
        split_mode="equal",
        people=[_person("p1", "A"), _person("p2", "B"), _person("p3", "C")],
        items=[_item("i1", "Pizza", 10.01)],
        charges=[],
        assignments=[],
    )
    totals = [r.total for r in calculate_split(s).person_results]
    assert round(sum(totals) * 100) == 1001
    assert max(totals) - min(totals) <= 0.01
