"""Money and order states for the Shop screens: whole paise everywhere, never a decimal, the same arithmetic prism-wa uses (commerce.py), so a screen can show an order's total
before the server confirms it and never disagree with it by a paisa.

STDLIB ONLY (the demo layer imports it too).
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

STATES = ("draft", "awaiting_payment", "paid", "processing", "shipped", "completed", "cancelled", "failed", "refunded")
NEXT = {
    "draft": ("awaiting_payment", "cancelled"),
    "awaiting_payment": ("paid", "failed", "cancelled", "draft"),
    "failed": ("awaiting_payment", "cancelled", "draft"),
    "paid": ("processing", "shipped", "completed", "refunded", "cancelled"),
    "processing": ("shipped", "completed", "refunded", "cancelled"),
    "shipped": ("completed", "refunded"),
    "completed": ("refunded",),
    "cancelled": (),
    "refunded": (),
}


class MoneyError(ValueError):
    pass


def paise(value, *, what: str = "amount") -> int:
    """Rupees (a number or text like "499", "1,299.50", "Rs 499") -> whole paise. Raises MoneyError, in words, for anything that is not a non-negative amount."""
    if isinstance(value, bool):
        raise MoneyError("the %s is not a number" % what)
    if isinstance(value, int):
        d = Decimal(value)
    else:
        text = re.sub(r"(?i)rs\.?|inr|₹|,|\s", "", str(value if value is not None else "")).strip()
        try:
            d = Decimal(text)
        except InvalidOperation:
            raise MoneyError("the %s is not a number" % what) from None
    if d < 0 or d > Decimal("100000000"):
        raise MoneyError("the %s must be between 0 and 100,000,000" % what)
    return int((d * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def rupees(amount_paise) -> str:
    return "{:,.2f}".format(Decimal(int(amount_paise or 0)) / 100)


def money_text(amount_paise, currency: str = "INR") -> str:
    """"Rs 1,299.50" (Rs rather than the rupee sign, which not every font on a customer's machine has)."""
    return ("Rs " if currency in ("INR", "", None) else currency + " ") + rupees(amount_paise)


def totals(items: list, *, tax_percent=0, shipping_paise: int = 0, discount_paise: int = 0) -> dict:
    subtotal = sum(int(i["line_paise"]) for i in items)
    discount = max(0, min(int(discount_paise or 0), subtotal))
    tax = int((Decimal(subtotal - discount) * Decimal(str(tax_percent or 0)) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    shipping = max(0, int(shipping_paise or 0))
    return {"subtotal_paise": subtotal, "discount_paise": discount, "tax_paise": tax, "shipping_paise": shipping, "total_paise": subtotal - discount + tax + shipping}


def state_words(status: str) -> tuple:
    """(plain words, tone) for an order's state, tone being a Pill tone."""
    return {"draft": ("Cart", "quiet"), "awaiting_payment": ("Waiting for payment", "warn"), "paid": ("Paid", "ok"), "processing": ("Being prepared", "info"),
            "shipped": ("Shipped", "info"), "completed": ("Done", "ok"), "cancelled": ("Cancelled", "quiet"), "failed": ("Payment failed", "err"),
            "refunded": ("Refunded", "quiet")}.get(status, (status, "quiet"))


def payment_words(status: str) -> tuple:
    return {"created": ("Not sent", "quiet"), "pending": ("Waiting", "warn"), "captured": ("Received", "ok"), "failed": ("Failed", "err"), "expired": ("Ran out of time", "quiet"),
            "cancelled": ("Cancelled", "quiet"), "refunded": ("Refunded", "quiet"), "partially_refunded": ("Part refunded", "info")}.get(status, (status, "quiet"))
