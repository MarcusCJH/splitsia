"""Dataclasses matching @splitleh/core TypeScript types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ── Parse receipt (parseReceipt.ts) ──────────────────────────────────────────

Confidence = Literal["high", "medium", "low"]

ParsedChargeType = Literal[
    "subtotal",
    "gst",
    "service_charge",
    "discount",
    "rounding",
    "total",
]


@dataclass
class ParsedItem:
    name: str
    unit_price: float
    quantity: int
    total_price: float
    confidence: Confidence


@dataclass
class ParsedCharge:
    type: ParsedChargeType
    label: str
    amount: float


@dataclass
class ParseResult:
    items: list[ParsedItem] = field(default_factory=list)
    charges: list[ParsedCharge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── Receipt (types/receipt.ts) ───────────────────────────────────────────────

ChargeType = Literal["gst", "service_charge", "discount", "rounding", "other"]
ChargeSplitStrategy = Literal["proportional", "equal", "none"]


@dataclass
class Charge:
    id: str
    type: ChargeType
    label: str
    amount: float
    split_strategy: ChargeSplitStrategy
    rate: float | None = None


@dataclass
class ReceiptItem:
    id: str
    name: str
    unit_price: float
    quantity: int
    total_price: float
    notes: str | None = None


@dataclass
class Receipt:
    items: list[ReceiptItem]
    charges: list[Charge]
    subtotal: float
    total: float
    currency: str
    merchant: str | None = None
    date: str | None = None
    raw_image_data_url: str | None = None
    raw_text: str | None = None


# ── People (types/people.ts) ─────────────────────────────────────────────────

@dataclass
class Person:
    id: str
    name: str
    color: str


# ── Split (types/split.ts) ───────────────────────────────────────────────────

SplitMode = Literal["itemized", "equal"]


@dataclass
class ItemAssignment:
    item_id: str
    person_ids: list[str]


@dataclass
class SplitSession:
    id: str
    title: str
    receipt: Receipt
    people: list[Person]
    assignments: list[ItemAssignment]
    split_mode: SplitMode
    created_at: int
    updated_at: int


@dataclass
class ItemShare:
    item: ReceiptItem
    amount: float
    out_of: int


@dataclass
class ChargeShare:
    charge: Charge
    amount: float


@dataclass
class PersonResult:
    person: Person
    item_shares: list[ItemShare]
    charge_shares: list[ChargeShare]
    subtotal: float
    charges_total: float
    total: float


@dataclass
class SplitResult:
    person_results: list[PersonResult]
    unassigned_items: list[ReceiptItem]
    assigned_total: float
    receipt_total: float
