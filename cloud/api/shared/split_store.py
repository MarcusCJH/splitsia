"""DynamoDB helpers for Telegram group splits."""

from __future__ import annotations

import os
import re
import uuid
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from shared.dynamodb import now_iso, to_dynamo

_table = None


def table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["SPLITLEH_SESSIONS_TABLE"])
    return _table


def chat_pk(chat_id: int | str) -> str:
    return f"CHAT#{chat_id}"


def split_sk(split_id: str) -> str:
    return f"SPLIT#{split_id}"


def user_sk(split_id: str, user_id: int | str) -> str:
    return f"SPLIT#{split_id}#USER#{user_id}"


def meta_sk() -> str:
    return "META#active"


def new_split_id() -> str:
    return uuid.uuid4().hex[:12]


def get_active_split_id(chat_id: int | str) -> str | None:
    resp = table().get_item(Key={"PK": chat_pk(chat_id), "SK": meta_sk()})
    item = resp.get("Item")
    return item.get("splitId") if item else None


def set_active_split(chat_id: int | str, split_id: str) -> None:
    table().put_item(
        Item=to_dynamo(
            {
                "PK": chat_pk(chat_id),
                "SK": meta_sk(),
                "splitId": split_id,
                "updatedAt": now_iso(),
            }
        )
    )


def clear_active_split(chat_id: int | str) -> None:
    table().delete_item(Key={"PK": chat_pk(chat_id), "SK": meta_sk()})


def create_split(
    chat_id: int | str,
    *,
    scanner_user_id: int,
    status: str = "scanning",
) -> str:
    split_id = new_split_id()
    table().put_item(
        Item=to_dynamo(
            {
                "PK": chat_pk(chat_id),
                "SK": split_sk(split_id),
                "splitId": split_id,
                "status": status,
                "scannerUserId": scanner_user_id,
                "items": [],
                "charges": [],
                "rawText": "",
                "createdAt": now_iso(),
                "updatedAt": now_iso(),
            }
        )
    )
    set_active_split(chat_id, split_id)
    return split_id


def get_split(chat_id: int | str, split_id: str) -> dict[str, Any] | None:
    resp = table().get_item(Key={"PK": chat_pk(chat_id), "SK": split_sk(split_id)})
    return resp.get("Item")


def update_split(chat_id: int | str, split_id: str, **fields: Any) -> None:
    fields["updatedAt"] = now_iso()
    names: dict[str, str] = {}
    values: dict[str, Any] = {}
    parts: list[str] = []
    for idx, (key, value) in enumerate(fields.items()):
        nk, vk = f"#k{idx}", f":v{idx}"
        names[nk] = key
        values[vk] = to_dynamo(value)
        parts.append(f"{nk} = {vk}")
    table().update_item(
        Key={"PK": chat_pk(chat_id), "SK": split_sk(split_id)},
        UpdateExpression="SET " + ", ".join(parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def get_user_claims(chat_id: int | str, split_id: str, user_id: int | str) -> dict[str, Any]:
    resp = table().get_item(
        Key={"PK": chat_pk(chat_id), "SK": user_sk(split_id, user_id)},
    )
    return resp.get("Item") or {
        "claimedItemIds": [],
        "displayName": "",
        "username": None,
    }


def save_user_claims(
    chat_id: int | str,
    split_id: str,
    user_id: int | str,
    *,
    claimed_item_ids: list[str],
    display_name: str,
    username: str | None,
) -> None:
    table().put_item(
        Item=to_dynamo(
            {
                "PK": chat_pk(chat_id),
                "SK": user_sk(split_id, user_id),
                "claimedItemIds": claimed_item_ids,
                "displayName": display_name,
                "username": username,
                "updatedAt": now_iso(),
            }
        )
    )


def list_split_users(chat_id: int | str, split_id: str) -> list[dict[str, Any]]:
    resp = table().query(
        KeyConditionExpression=Key("PK").eq(chat_pk(chat_id))
        & Key("SK").begins_with(f"SPLIT#{split_id}#USER#"),
    )
    return resp.get("Items", [])


def is_proxy_person_id(person_id: str) -> bool:
    return str(person_id).startswith("p:")


def proxy_person_id(name: str, used: set[str]) -> str:
    """Stable id for a named proxy person (solo assign-for-others mode)."""
    base = re.sub(r"[^a-z0-9]+", "", name.lower())[:10] or "person"
    slug = base
    n = 2
    while f"p:{slug}" in used:
        slug = f"{base}{n}"[:12]
        n += 1
    return f"p:{slug}"


def delete_user_row(chat_id: int | str, split_id: str, user_id: int | str) -> None:
    table().delete_item(Key={"PK": chat_pk(chat_id), "SK": user_sk(split_id, user_id)})


def replace_proxy_people(
    chat_id: int | str,
    split_id: str,
    names: list[str],
) -> list[dict[str, str]]:
    """
    Replace proxy people for a split. Returns [{id, name}, ...].
    Clears previous proxy USER rows; leaves real Telegram user rows alone.
    """
    cleaned = [n.strip() for n in names if n and n.strip()]
    if not cleaned:
        raise ValueError("Need at least one name")

    for row in list_split_users(chat_id, split_id):
        uid = str(row.get("SK", "").split("#USER#")[-1])
        if is_proxy_person_id(uid):
            delete_user_row(chat_id, split_id, uid)

    used: set[str] = set()
    people: list[dict[str, str]] = []
    for name in cleaned:
        pid = proxy_person_id(name, used)
        used.add(pid)
        people.append({"id": pid, "name": name.strip()[:32]})
        save_user_claims(
            chat_id,
            split_id,
            pid,
            claimed_item_ids=[],
            display_name=name.strip()[:32],
            username=None,
        )

    update_split(
        chat_id,
        split_id,
        claimMode="proxy",
        activePersonId=people[0]["id"],
        people=people,
    )
    return people


def resolve_claimer_id(split: dict[str, Any], telegram_user_id: int) -> str:
    """Who receives the next item tap - active proxy, or the Telegram user."""
    if split.get("claimMode") == "proxy" and split.get("activePersonId"):
        return str(split["activePersonId"])
    return str(telegram_user_id)


def claim_counts(user_rows: list[dict]) -> dict[str, int]:
    """How many participants picked each item (shared items > 1)."""
    counts: dict[str, int] = {}
    for row in user_rows:
        for item_id in normalize_claimed_ids(row.get("claimedItemIds")):
            counts[item_id] = counts.get(item_id, 0) + 1
    return counts


def toggle_claim(claimed_ids: list[str], item_id: str) -> list[str]:
    if item_id in claimed_ids:
        return [i for i in claimed_ids if i != item_id]
    return [*claimed_ids, item_id]


def normalize_claimed_ids(raw: list | None) -> list[str]:
    if not raw:
        return []
    return [str(item_id) for item_id in raw]
