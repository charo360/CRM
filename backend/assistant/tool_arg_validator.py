"""
Tool argument validator — validates types, formats, and scans for sensitive PII.
"""
from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Basic PII Regex patterns
CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")


def scan_and_redact_pii(val: Any) -> Tuple[Any, List[str]]:
    """Scan values recursively for PII (Credit Cards, SSNs) and redact them.

    Returns:
        A tuple of (redacted_value, list_of_detected_pii_types)
    """
    detected = []
    if isinstance(val, str):
        redacted = val
        # Check Credit Cards
        if CREDIT_CARD_RE.search(redacted):
            # Verify Luhn-like or simple redaction
            redacted = CREDIT_CARD_RE.sub("[REDACTED_CREDIT_CARD]", redacted)
            detected.append("credit_card")
        # Check SSNs
        if SSN_RE.search(redacted):
            redacted = SSN_RE.sub("[REDACTED_SSN]", redacted)
            detected.append("ssn")
        return redacted, detected

    if isinstance(val, dict):
        new_dict = {}
        for k, v in val.items():
            # Skip keys that are meant to hold email/phone on purpose
            if k in ("email", "contact", "phone", "phone_number"):
                new_dict[k] = v
                continue
            red_v, det = scan_and_redact_pii(v)
            new_dict[k] = red_v
            detected.extend(det)
        return new_dict, list(set(detected))

    if isinstance(val, list):
        new_list = []
        for item in val:
            red_item, det = scan_and_redact_pii(item)
            new_list.append(red_item)
            detected.extend(det)
        return new_list, list(set(detected))

    return val, detected


def validate_tool_args(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate tool arguments against tool parameters schema and sanitize PII.

    Returns:
        The sanitized and validated args dict.
    """
    # 1. First redact any sensitive PII (except explicitly allowed fields)
    sanitized, PII_types = scan_and_redact_pii(args)
    if PII_types:
        logger.info("[PII_GUARD] Redacted sensitive PII %s in tool %s args", PII_types, name)

    # 2. Basic schema type checking based on registry parameters if available
    try:
        from assistant.tools import REGISTRY
        tool_spec = REGISTRY.get(name)
        if tool_spec and "parameters" in tool_spec:
            schema = tool_spec["parameters"]
            required = schema.get("required") or []
            properties = schema.get("properties") or {}

            # Check missing required fields
            for req in required:
                if req not in sanitized:
                    raise ValueError(f"Missing required parameter: '{req}'")

            # Check parameter types
            for prop_name, prop_val in properties.items():
                if prop_name in sanitized:
                    val = sanitized[prop_name]
                    expected_type = prop_val.get("type")

                    if expected_type == "string" and not isinstance(val, str) and val is not None:
                        sanitized[prop_name] = str(val)
                    elif expected_type == "integer" and not isinstance(val, int) and val is not None:
                        try:
                            sanitized[prop_name] = int(val)
                        except (ValueError, TypeError):
                            raise ValueError(f"Parameter '{prop_name}' must be an integer.")
                    elif expected_type == "number" and not isinstance(val, (int, float)) and val is not None:
                        try:
                            sanitized[prop_name] = float(val)
                        except (ValueError, TypeError):
                            raise ValueError(f"Parameter '{prop_name}' must be a number.")
                    elif expected_type == "boolean" and not isinstance(val, bool) and val is not None:
                        if str(val).lower() in ("true", "1", "yes"):
                            sanitized[prop_name] = True
                        elif str(val).lower() in ("false", "0", "no"):
                            sanitized[prop_name] = False
                        else:
                            raise ValueError(f"Parameter '{prop_name}' must be a boolean.")
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        logger.warning("[arg_validator] Schema inspection skipped for %s: %s", name, exc)

    return sanitized
