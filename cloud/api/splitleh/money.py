"""Integer-cent and rounding helpers - mirrors lite/core/src/money.ts and calculateSplit.ts."""


def round2(n: float) -> float:
    return round(n * 100) / 100


def to_cents(dollars: float) -> int:
    return round(dollars * 100)
