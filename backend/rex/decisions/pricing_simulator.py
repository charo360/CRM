"""
Pricing scenario estimates for Decision Room sparring.

Conservative illustrative math from CRM metrics — always tagged medium/low confidence.
"""

from __future__ import annotations

import re
from typing import Any

from rex.decisions.models import DataFact

_PRICING_RE = re.compile(
    r"\b(pricing|price|usage[- ]?based|flat|retainer|subscription|tier|"
    r"monthly fee|per[- ]?seat|raise|discount|freemium|mrr|arr)\b",
    re.I,
)


def is_pricing_question(question: str, founder_lean: str = "") -> bool:
    blob = f"{question} {founder_lean}"
    return bool(_PRICING_RE.search(blob))


def simulate_pricing_scenarios(
    ctx: dict[str, Any],
    question: str,
    founder_lean: str = "",
) -> list[DataFact]:
    """Return hard-number facts to prepend to spar your_data."""
    if not is_pricing_question(question, founder_lean):
        return []

    currency = ctx.get("currency") or "USD"
    customers = int(ctx.get("customer_count") or 0)
    revenue_30d = float(ctx.get("revenue_30d") or 0)
    sales_n = int(ctx.get("sales_count_30d") or 0)
    stalled = int(ctx.get("stalled_deals") or 0)
    conv = ctx.get("followup_conversion_30d")

    facts: list[DataFact] = []

    if revenue_30d > 0:
        facts.append(
            DataFact(
                fact=f"Trailing 30d revenue: {currency} {revenue_30d:,.0f} across {sales_n or 'unknown'} recorded sales.",
                source="sales",
                confidence="high",
            )
        )

    if customers > 0 and revenue_30d > 0:
        implied_mrr = revenue_30d  # monthly window proxy
        per_customer = implied_mrr / max(customers, 1)
        facts.append(
            DataFact(
                fact=f"Implied ~{currency} {per_customer:,.0f}/customer/month at current mix ({customers} customers).",
                source="simulation",
                confidence="medium",
            )
        )

        # Flat +10% price scenario (same customer count)
        uplift_flat = implied_mrr * 1.10
        facts.append(
            DataFact(
                fact=f"Flat +10% on existing base → ~{currency} {uplift_flat:,.0f}/mo if no churn (illustrative).",
                source="simulation",
                confidence="low",
            )
        )

        # Usage-based downside: 15% more logos at 25% lower ARPU
        usage_mrr = implied_mrr * 1.15 * 0.75
        facts.append(
            DataFact(
                fact=f"Usage-based stress case (+15% customers, -25% ARPU) → ~{currency} {usage_mrr:,.0f}/mo before support costs.",
                source="simulation",
                confidence="low",
            )
        )

    if stalled > 0:
        facts.append(
            DataFact(
                fact=f"{stalled} deals stalled >7 days — pricing moves won't close these without follow-up.",
                source="customers",
                confidence="high",
            )
        )

    if conv is not None:
        facts.append(
            DataFact(
                fact=f"Follow-up conversion last 30d: {conv}% — pricing clarity may affect reply rate.",
                source="followups",
                confidence="medium",
            )
        )

    bk = ctx.get("business_knowledge") or {}
    if bk.get("pricing_info"):
        facts.append(
            DataFact(
                fact=f"Your stated pricing notes are on file — spar should align with what you already sell.",
                source="business_knowledge",
                confidence="high",
            )
        )

    if not facts:
        facts.append(
            DataFact(
                fact="Not enough revenue/customer data to model pricing scenarios — connect sales or Stripe.",
                source="simulation",
                confidence="low",
            )
        )

    return facts
