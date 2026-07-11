from shared.split_store import (
    claim_counts,
    proxy_person_id,
    resolve_claimer_id,
    toggle_claim,
)
from splitleh_telegram.keyboards import build_item_keyboard
from splitleh_telegram.split_builder import build_session, compute_split


def test_keyboard_shows_shared_count():
    kb = build_item_keyboard(
        "abc123",
        [{"id": "i1", "name": "Guinness", "totalPrice": 13.0}],
        claim_counts={"i1": 2},
    )
    label = kb.inline_keyboard[0][0].text
    assert "×2" in label


def test_keyboard_shows_people_row_and_active_mark():
    kb = build_item_keyboard(
        "abc123",
        [{"id": "i1", "name": "Beer", "totalPrice": 10.0}],
        people=[{"id": "p:alice", "name": "Alice"}, {"id": "p:bob", "name": "Bob"}],
        active_person_id="p:alice",
        selected_ids={"i1"},
    )
    person_labels = [btn.text for btn in kb.inline_keyboard[0]]
    assert any(t.startswith("● ") and "Alice" in t for t in person_labels)
    assert any("Bob" in t and not t.startswith("● ") for t in person_labels)
    assert kb.inline_keyboard[1][0].text.startswith("✓ ")


def test_proxy_person_id_unique():
    used: set[str] = set()
    a = proxy_person_id("Alice", used)
    used.add(a)
    b = proxy_person_id("Alice!", used)
    assert a == "p:alice"
    assert b != a
    assert b.startswith("p:")


def test_resolve_claimer_uses_active_proxy():
    split = {"claimMode": "proxy", "activePersonId": "p:bob"}
    assert resolve_claimer_id(split, 999) == "p:bob"
    assert resolve_claimer_id({"claimMode": "self"}, 999) == "999"


def test_claim_counts_aggregates_users():
    users = [
        {"claimedItemIds": ["i1", "i2"]},
        {"claimedItemIds": ["i1"]},
    ]
    assert claim_counts(users) == {"i1": 2, "i2": 1}


def test_two_people_same_item_splits_cost():
    items = [
        {"id": "i1", "name": "Beer", "unitPrice": 10, "quantity": 1, "totalPrice": 10},
    ]
    users = [
        {"SK": "SPLIT#s1#USER#p:alice", "claimedItemIds": ["i1"], "displayName": "Alice"},
        {"SK": "SPLIT#s1#USER#p:bob", "claimedItemIds": ["i1"], "displayName": "Bob"},
    ]
    result = compute_split("s1", items, [], users)
    assert len(result.person_results) == 2
    names = {pr.person.name for pr in result.person_results}
    assert names == {"Alice", "Bob"}
    for pr in result.person_results:
        assert pr.total == 5.0


def test_unclaimed_items_split_among_all_participants():
    items = [
        {"id": "i1", "name": "Beer", "unitPrice": 10, "quantity": 1, "totalPrice": 10},
        {"id": "i2", "name": "Wine", "unitPrice": 20, "quantity": 1, "totalPrice": 20},
    ]
    users = [
        {
            "SK": "SPLIT#s1#USER#p:alice",
            "claimedItemIds": ["i1"],
            "displayName": "Alice",
        },
        {
            "SK": "SPLIT#s1#USER#p:bob",
            "claimedItemIds": [],
            "displayName": "Bob",
        },
    ]
    session = build_session("s1", items, [], users)
    wine = next(a for a in session.assignments if a.item_id == "i2")
    assert set(wine.person_ids) == {"p:alice", "p:bob"}
