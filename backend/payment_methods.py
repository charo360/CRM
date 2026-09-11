"""Payment methods as a customer should hear them.

Owners list how they get paid under Business Knowledge. Signup pre-fills a few
names with nothing attached -- "Bank Transfer", "Card" -- and owners add methods
without the number, like "Airtel Money". Every one of those was still offered
to customers as a way to pay: "you can pay by Bank Transfer", with no account to
pay into. Saying nothing is better than that.

A method is kept only if it carries something a customer can act on: details,
or filled-in fields for the multi-field kinds such as a Paybill. Cash is the
exception, since paying in cash needs no account to be told about.

This is only for what customers are told. The owner's own Business Knowledge
screen keeps every entry, empty ones included, because that is where they go
to fill them in.
"""
from typing import Any, Dict, List

# Whole names only. Matching the word "cash" anywhere would keep "Chipper Cash",
# a mobile-money app that is no use to a customer without a username.
_NO_DETAILS_NEEDED = {
    "cash", "pay cash", "cash payment",
    "cash on delivery", "pay on delivery", "cod",
    "cash on pickup", "pay on pickup", "pay at pickup",
}


def _as_list(raw: Any) -> list:
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        return list(raw)
    # A single method stored on its own rather than in a list.
    return [raw]


def _normalise(pm: Any) -> Dict[str, Any]:
    if isinstance(pm, dict):
        return pm
    return {"name": str(pm or ""), "details": ""}


def _field_values(pm: Dict[str, Any]) -> List[str]:
    out = []
    for f in pm.get("fields") or []:
        if not isinstance(f, dict):
            continue
        value = str(f.get("value") or "").strip()
        if value:
            label = str(f.get("label") or "").strip()
            out.append(f"{label}: {value}" if label else value)
    return out


def is_payable(pm: Any) -> bool:
    """Can a customer actually pay using this entry?"""
    pm = _normalise(pm)
    name = str(pm.get("name") or "").strip()
    if not name:
        return False
    if str(pm.get("details") or "").strip():
        return True
    if _field_values(pm):
        return True
    return " ".join(name.lower().split()) in _NO_DETAILS_NEEDED


def usable_payment_methods(raw: Any) -> List[Dict[str, Any]]:
    """The owner's methods that a customer can act on, as {name, details, ...}."""
    return [_normalise(pm) for pm in _as_list(raw) if is_payable(pm)]


def payment_method_line(pm: Any) -> str:
    """One method as a line: "M-Pesa: 0712 345 678"."""
    pm = _normalise(pm)
    name = str(pm.get("name") or "").strip()
    details = str(pm.get("details") or "").strip()
    if details:
        return f"{name}: {details}"
    fields = _field_values(pm)
    if fields:
        return f"{name}: " + ", ".join(fields)
    return name


def payment_method_lines(raw: Any) -> List[str]:
    """Every usable method as a line, in the owner's order."""
    return [payment_method_line(pm) for pm in usable_payment_methods(raw)]
