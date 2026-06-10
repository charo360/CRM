"""
PayHero Kenya rate card (M-Pesa payment tiers + SMS / WhatsApp per message).

Versioned so tiers can be updated without touching payment logic.
Source: PayHero Kenya published brackets (MPESA → BANK / PAYBILL / TILL).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Literal, Optional, TypedDict

RATE_CARD_VERSION = "kenya-mpesa-v1"

# (min_kes inclusive, max_kes inclusive, transaction_fee_kes)
MPESA_PAYMENT_TIERS: List[tuple[int, int, int]] = [
    (1, 49, 1),
    (50, 499, 6),
    (500, 999, 10),
    (1_000, 1_499, 15),
    (1_500, 2_499, 20),
    (2_500, 3_499, 25),
    (3_500, 4_999, 30),
    (5_000, 7_499, 40),
    (7_500, 9_999, 45),
    (10_000, 14_999, 50),
    (15_000, 19_999, 55),
    (20_000, 34_999, 80),
    (35_000, 49_999, 105),
    (50_000, 149_999, 130),
    (150_000, 249_999, 160),
    # Upper tiers: extend last published step until PayHero publishes more
    (250_000, 349_999, 180),
    (350_000, 549_999, 210),
    (550_000, 749_999, 240),
    (750_000, 999_999, 270),
]

CHANNEL_MESSAGE_FEE_KES: dict[str, Decimal] = {
    "sms": Decimal("1.80"),
    "whatsapp": Decimal("0.60"),
}

MessageChannel = Literal["sms", "whatsapp"]


class MpesaTierRow(TypedDict):
    min_kes: int
    max_kes: int
    fee_kes: int


class RateCardPublic(TypedDict):
    version: str
    currency: str
    mpesa_tiers: List[MpesaTierRow]
    sms_per_message_kes: float
    whatsapp_per_message_kes: float


@dataclass(frozen=True)
class FeeQuote:
    gross_kes: float
    payhero_fee_kes: int
    merchant_receives_kes: float
    tier_min_kes: int
    tier_max_kes: int


def mpesa_transaction_fee_kes(amount: float) -> int:
    """PayHero transaction fee for a successful M-Pesa collection (KES)."""
    if amount <= 0:
        return 0
    amt = int(round(amount))
    for lo, hi, fee in MPESA_PAYMENT_TIERS:
        if lo <= amt <= hi:
            return fee
    # Above published max: use highest tier fee
    return MPESA_PAYMENT_TIERS[-1][2]


def mpesa_fee_quote(amount: float) -> FeeQuote:
    """Estimate fees; merchant typically receives full gross, PayHero bills fee separately."""
    fee = mpesa_transaction_fee_kes(amount)
    amt = max(0.0, float(amount))
    lo, hi = _tier_bounds_for_amount(amt)
    return FeeQuote(
        gross_kes=amt,
        payhero_fee_kes=fee,
        merchant_receives_kes=amt,
        tier_min_kes=lo,
        tier_max_kes=hi,
    )


def _tier_bounds_for_amount(amount: float) -> tuple[int, int]:
    amt = int(round(amount))
    for lo, hi, _ in MPESA_PAYMENT_TIERS:
        if lo <= amt <= hi:
            return lo, hi
    if amt > MPESA_PAYMENT_TIERS[-1][1]:
        return MPESA_PAYMENT_TIERS[-1][0], MPESA_PAYMENT_TIERS[-1][1]
    return 0, 0


def channel_message_fee_kes(channel: MessageChannel) -> Decimal:
    return CHANNEL_MESSAGE_FEE_KES[channel]


def public_rate_card() -> RateCardPublic:
    return RateCardPublic(
        version=RATE_CARD_VERSION,
        currency="KES",
        mpesa_tiers=[
            MpesaTierRow(min_kes=lo, max_kes=hi, fee_kes=fee)
            for lo, hi, fee in MPESA_PAYMENT_TIERS
        ],
        sms_per_message_kes=float(CHANNEL_MESSAGE_FEE_KES["sms"]),
        whatsapp_per_message_kes=float(CHANNEL_MESSAGE_FEE_KES["whatsapp"]),
    )
