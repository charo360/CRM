"""Shared helpers for the presentation plan → approve → generate loop."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_PLACEHOLDER_RE = re.compile(
    r"\[(?:insert|add|your|tbd|xxx|placeholder)[^\]]*\]|^x+%$|^tbd$|^n/a$",
    re.I,
)

# Fields the agent must resolve (CRM + user answers) before planning
_REQUIREMENT_CATALOG: Dict[str, Dict[str, str]] = {
    "business_identity": {
        "label": "Business name & contact",
        "question": "What's your business name and best contact email or phone for the closing slide?",
    },
    "value_proposition": {
        "label": "Value proposition",
        "question": "In one sentence, what does your business do and who is it for?",
    },
    "problem_statement": {
        "label": "Problem / pain point",
        "question": "What specific problem or pain point does your audience face that this deck addresses?",
    },
    "solution": {
        "label": "Solution / offering",
        "question": "What is your product or service, and how does it solve that problem?",
    },
    "market_size": {
        "label": "Market size",
        "question": "What are your TAM, SAM, and SOM (or best estimates)? e.g. '$4B TAM · $800M SAM · $120M SOM'.",
    },
    "traction": {
        "label": "Traction / proof",
        "question": "Share 2–3 proof points — revenue, customers, growth rate, retention, or key wins.",
    },
    "team": {
        "label": "Team",
        "question": "Who are the key people on the team? Name, role, and one credential each.",
    },
    "funding_ask": {
        "label": "Funding ask",
        "question": "How much are you raising, at what stage, and what will you use the funds for?",
    },
    "client_pain": {
        "label": "Client pain",
        "question": "What pain or goal does your target client have that you're pitching against?",
    },
    "proof_roi": {
        "label": "Proof / ROI",
        "question": "What results, case studies, or ROI can you cite? Include numbers if you have them.",
    },
    "pricing_offer": {
        "label": "Pricing / offer",
        "question": "What are you offering and at what price (or pricing tiers)?",
    },
    "meeting_topic": {
        "label": "Meeting focus",
        "question": "What's the main topic or decision for this internal deck?",
    },
    "key_updates": {
        "label": "Key updates / data",
        "question": "What are the main updates, metrics, or findings to cover?",
    },
    "next_steps": {
        "label": "Next steps",
        "question": "What actions or decisions should the audience take after this meeting?",
    },
    "learning_objectives": {
        "label": "Learning objectives",
        "question": "What should the audience know or be able to do after this training?",
    },
    "training_content": {
        "label": "Training content",
        "question": "What are the 2–3 core concepts or modules to teach?",
    },
    "target_audience": {
        "label": "Audience",
        "question": "Who is this training for (role, experience level)?",
    },
}

_PURPOSE_REQUIRED_KEYS: Dict[str, List[str]] = {
    "investor_pitch": [
        "business_identity",
        "value_proposition",
        "problem_statement",
        "solution",
        "market_size",
        "traction",
        "team",
        "funding_ask",
    ],
    "sales": [
        "business_identity",
        "value_proposition",
        "client_pain",
        "solution",
        "proof_roi",
        "pricing_offer",
    ],
    "internal": [
        "business_identity",
        "meeting_topic",
        "key_updates",
        "next_steps",
    ],
    "training": [
        "business_identity",
        "learning_objectives",
        "training_content",
        "target_audience",
    ],
    "other": [
        "business_identity",
        "value_proposition",
        "meeting_topic",
    ],
}

# Filled automatically via web search — never show in the user checklist
RESEARCHABLE_KEYS = frozenset({
    "market_size",
    "problem_statement",
    "client_pain",
    "proof_roi",
})

CHECKLIST_VERSION = 3  # bump when checklist rules change (UI can ignore stale cards)


def researchable_keys_for_purpose(purpose: str) -> frozenset:
    """Which requirement keys web search can fill for this deck type — not one-size-fits-all."""
    _MAP: Dict[str, frozenset] = {
        "investor_pitch": frozenset({"market_size", "problem_statement"}),
        "sales": frozenset({"client_pain", "proof_roi"}),
        "internal": frozenset(),
        "training": frozenset(),
        "other": frozenset({"problem_statement"}),
    }
    return _MAP.get(purpose, frozenset({"problem_statement"}))


def requirement_label(key: str) -> str:
    return _REQUIREMENT_CATALOG.get(key, {}).get("label") or key.replace("_", " ").title()

# Must come from the user — never guess
USER_ONLY_KEYS = frozenset({
    "funding_ask",
    "next_steps",
    "learning_objectives",
    "target_audience",
})

# Default photographic backgrounds when the model omits image_prompt
_LAYOUT_SCENES: Dict[str, str] = {
    "title": "wide modern city skyline at golden hour, clean and aspirational, real photography",
    "stat_callout": "dark polished marble desk surface, minimal executive mood, real photography",
    "two_column": "bright modern office with floor-to-ceiling windows, natural light, real photography",
    "icon_grid": "clean white architectural interior, soft daylight, uncluttered, real photography",
    "flow": "overhead view of a organised workspace with notebook and coffee, calm tone, real photography",
    "comparison_table": "minimal conference room with blurred background, professional, real photography",
    "timeline": "aerial view of a growing city at dusk, forward momentum mood, real photography",
    "closing": "calm ocean horizon at sunset, open and confident mood, real photography",
    "content": "sunlit co-working space with plants, warm and professional, real photography",
}

# Recommended narrative arc by deck purpose (for agent guidance strings)
DECK_ARCHETYPES: Dict[str, List[str]] = {
    "investor_pitch": [
        "Hook / vision",
        "Problem + market pain (with stat)",
        "Solution / product",
        "How it works",
        "Market size (TAM/SAM/SOM)",
        "Traction or business model",
        "Team",
        "The ask",
        "Closing CTA",
    ],
    "sales": [
        "Title + value promise",
        "Prospect's pain",
        "Your solution",
        "Proof / ROI / case outcome",
        "Offer & pricing",
        "Closing CTA",
    ],
    "internal": [
        "Title",
        "Context / goal",
        "Key updates or data",
        "Plan / next steps",
        "Closing",
    ],
    "training": [
        "Title",
        "Learning objective",
        "Core concept 1",
        "Core concept 2",
        "Summary & resources",
        "Closing",
    ],
}


def _clean(text: Any) -> str:
    s = str(text or "").strip()
    if not s or _PLACEHOLDER_RE.search(s):
        return ""
    return s


def _substantive(text: Any, *, min_len: int = 20) -> bool:
    return len(_clean(text)) >= min_len


def _ctx_val(user_context: Dict[str, Any], key: str) -> str:
    return _clean(user_context.get(key))


def _resolve_deck_purpose(deck_purpose: str, audience: str = "") -> str:
    p = (deck_purpose or "").strip().lower()
    if p in _PURPOSE_REQUIRED_KEYS:
        return p
    aud = (audience or "").lower()
    if "investor" in aud or "fund" in aud or "pitch" in aud:
        return "investor_pitch"
    if "client" in aud or "sales" in aud or "proposal" in aud:
        return "sales"
    if "train" in aud or "onboard" in aud:
        return "training"
    if "team" in aud or "internal" in aud:
        return "internal"
    return "other"


_GENERIC_TOPICS = frozenset({
    "",
    "presentation",
    "pitch deck",
    "slide deck",
    "slides",
    "deck",
    "my presentation",
})


def resolve_presentation_topic(topic: str, owner: Dict[str, Any]) -> str:
    """Prefer CRM business identity over generic placeholders for web research."""
    t = _clean(topic)
    if t.lower() not in _GENERIC_TOPICS and len(t) >= 4:
        return t
    biz = _clean(owner.get("business_name"))
    hint = _clean(owner.get("business_description_hint") or owner.get("products_services_hint"))
    bt = _clean(owner.get("business_type"))
    if biz and hint:
        return f"{biz}: {hint[:100]}"
    if biz and bt:
        return f"{biz} ({bt})"
    if biz:
        return biz
    if hint:
        return hint[:120]
    return t or "Presentation"


def seed_user_context_from_crm(
    *,
    owner: Dict[str, Any],
    analytics: Dict[str, Any],
    products: List[Dict[str, Any]],
    team: List[Dict[str, Any]],
    user_context: Dict[str, Any],
) -> Dict[str, str]:
    """Pre-fill requirement keys from CRM so research + checklist only ask for true gaps."""
    out: Dict[str, str] = {
        k: _clean(v) for k, v in (user_context or {}).items() if _clean(v)
    }

    biz = _clean(owner.get("business_name"))
    contact = _clean(owner.get("email")) or _clean(owner.get("phone_number"))
    if not _ctx_val(out, "business_identity") and biz:
        out["business_identity"] = f"{biz}" + (f" · {contact}" if contact else "")

    hint = _clean(owner.get("business_description_hint") or owner.get("products_services_hint"))
    if not _ctx_val(out, "value_proposition") and _substantive(hint):
        out["value_proposition"] = hint[:220]

    if not _ctx_val(out, "solution"):
        names = [_clean(p.get("name")) for p in products[:4] if _clean(p.get("name"))]
        if names:
            out["solution"] = ", ".join(names)
        elif _substantive(owner.get("products_services_hint")):
            out["solution"] = _clean(owner.get("products_services_hint"))[:220]

    if not _ctx_val(out, "traction"):
        parts: List[str] = []
        customers = int(analytics.get("customers_count") or 0)
        if customers >= 1:
            parts.append(f"{customers} customers in CRM")
        rev = float(analytics.get("sales_revenue_today") or 0)
        if rev > 0:
            parts.append(f"Revenue today {rev:,.0f}")
        orders = int(analytics.get("active_orders") or 0)
        if orders:
            parts.append(f"{orders} active orders")
        if parts:
            out["traction"] = "; ".join(parts)

    if not _ctx_val(out, "team"):
        tm = _team_options(team, owner)
        if tm:
            out["team"] = "; ".join(o["value"] for o in tm[:4])
        elif _clean(owner.get("owner_name")):
            out["team"] = f"{_clean(owner.get('owner_name'))} — Founder"

    if not _ctx_val(out, "pricing_offer"):
        priced = _product_pricing_options(products)
        if priced:
            out["pricing_offer"] = "; ".join(o["value"] for o in priced[:4])

    return out


def build_business_profile(
    owner: Dict[str, Any],
    *,
    topic: str,
    deck_purpose: str,
    audience: str,
) -> Dict[str, str]:
    return {
        "business_name": _clean(owner.get("business_name")),
        "business_type": _clean(owner.get("business_type")),
        "topic": topic,
        "deck_purpose": deck_purpose,
        "audience": audience,
    }


def build_readiness_summary(
    found: Dict[str, Any],
    auto_researched: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Human-readable list of what was gathered before planning."""
    auto_researched = auto_researched or {}
    lines: List[str] = []
    seen: set = set()
    for key, val in auto_researched.items():
        if not _clean(val) or key in seen:
            continue
        seen.add(key)
        lines.append(f"{requirement_label(key)} (web research)")
    for key, meta in (found or {}).items():
        if key in seen:
            continue
        seen.add(key)
        src = str((meta or {}).get("source") or "crm")
        lines.append(f"{requirement_label(key)} ({src})")
    return lines


def _field_satisfied(
    key: str,
    *,
    owner: Dict[str, Any],
    analytics: Dict[str, Any],
    products: List[Dict[str, Any]],
    team: List[Dict[str, Any]],
    user_context: Dict[str, Any],
    topic: str,
    audience: str,
) -> Tuple[bool, str]:
    """Return (satisfied, source_hint) for one requirement key."""
    uc = _ctx_val(user_context, key)
    if uc:
        return True, "user"

    if key == "business_identity":
        biz = _clean(owner.get("business_name"))
        contact = _clean(owner.get("email")) or _clean(owner.get("phone_number"))
        if biz and contact:
            return True, "crm"
        if biz:
            return True, "crm"
        if contact:
            return False, "partial_crm"
        return False, "missing"

    if key == "value_proposition":
        if _substantive(owner.get("business_description_hint")):
            return True, "crm"
        if _substantive(owner.get("products_services_hint")):
            return True, "crm"
        if _substantive(topic):
            return True, "topic"
        return False, "missing"

    if key == "problem_statement":
        if _substantive(owner.get("business_description_hint"), min_len=40):
            return True, "crm"
        return False, "missing"

    if key == "solution":
        if products:
            return True, "products"
        if _substantive(owner.get("products_services_hint")):
            return True, "crm"
        return False, "missing"

    if key == "market_size":
        return False, "missing"

    if key == "traction":
        customers = int(analytics.get("customers_count") or 0)
        if customers >= 1:
            return True, "analytics"
        if float(analytics.get("sales_revenue_today") or 0) > 0:
            return True, "analytics"
        if int(analytics.get("active_orders") or 0) >= 1:
            return True, "analytics"
        return False, "missing"

    if key == "team":
        if team:
            return True, "crm"
        if _clean(owner.get("owner_name")):
            return True, "owner"
        return False, "missing"

    if key == "funding_ask":
        return False, "missing"

    if key == "client_pain":
        if _substantive(audience):
            return True, "audience"
        return False, "missing"

    if key == "proof_roi":
        if int(analytics.get("customers_count") or 0) >= 1:
            return True, "analytics"
        return False, "missing"

    if key == "pricing_offer":
        priced = [p for p in products if p.get("price") or p.get("discount_price")]
        if priced:
            return True, "products"
        return False, "missing"

    if key == "meeting_topic":
        if _substantive(topic):
            return True, "topic"
        return False, "missing"

    if key == "key_updates":
        if analytics:
            return True, "analytics"
        return False, "missing"

    if key == "next_steps":
        return False, "missing"

    if key == "learning_objectives":
        if _substantive(topic):
            return True, "topic"
        return False, "missing"

    if key == "training_content":
        if products:
            return True, "products"
        return False, "missing"

    if key == "target_audience":
        if _substantive(audience):
            return True, "audience"
        return False, "missing"

    return False, "missing"


def _search_text(data: Dict[str, Any]) -> str:
    parts: List[str] = []
    ans = _clean(data.get("answer"))
    if ans:
        parts.append(ans)
    for row in data.get("results") or []:
        if isinstance(row, dict):
            parts.append(_clean(row.get("snippet")))
            parts.append(_clean(row.get("title")))
    return " ".join(p for p in parts if p)


def _parse_market_size(text: str, topic: str) -> str:
    if not text:
        return ""
    tam = re.search(r"(?:TAM|total addressable market)\s*[:\-–—]?\s*([^.;|\n]{4,90})", text, re.I)
    sam = re.search(r"(?:SAM|serviceable addressable market)\s*[:\-–—]?\s*([^.;|\n]{4,90})", text, re.I)
    som = re.search(r"(?:SOM|serviceable obtainable market)\s*[:\-–—]?\s*([^.;|\n]{4,90})", text, re.I)
    parts: List[str] = []
    if tam:
        parts.append(f"TAM {tam.group(1).strip()}")
    if sam:
        parts.append(f"SAM {sam.group(1).strip()}")
    if som:
        parts.append(f"SOM {som.group(1).strip()}")
    if parts:
        return " · ".join(parts)[:220]

    money = re.findall(
        r"\$[\d,.]+\s*(?:billion|million|trillion|B|M|T|bn|mn)?|\b[\d,.]+\s*(?:billion|million)\b",
        text,
        re.I,
    )
    if money:
        return f"{topic}: market research ~{money[0].strip()} addressable opportunity"[:220]

    if re.search(r"\b(market size|addressable market|industry worth|valued at)\b", text, re.I):
        snippet = re.split(r"[.\n|]", text, maxsplit=1)[0].strip()
        if len(snippet) > 25:
            return snippet[:220]
    return ""


def _parse_industry_narrative(text: str, topic: str, *, kind: str) -> str:
    if not text:
        return ""
    if kind == "problem":
        m = re.search(
            r"(?:challenge|pain point|problem|struggle|bottleneck)[s]?[:\s-]+([^.;|\n]{20,160})",
            text,
            re.I,
        )
        if m:
            return m.group(1).strip()[:200]
    if kind == "roi":
        m = re.search(
            r"(?:ROI|return on investment|save[s]?|reduce[s]?|increase[s]?)[^.]{10,120}\.",
            text,
            re.I,
        )
        if m:
            return m.group(0).strip()[:200]
    answer = _clean(text.split("\n")[0])
    if _substantive(answer, min_len=45):
        return answer[:200]
    return ""


def _research_queries(
    key: str,
    *,
    topic: str,
    audience: str,
    owner: Dict[str, Any],
) -> List[str]:
    biz = _clean(owner.get("business_name"))
    bt = _clean(owner.get("business_type"))
    niche = " ".join(x for x in [topic, bt, biz] if x).strip() or topic
    if key == "market_size":
        return [
            f"{niche} market size TAM SAM SOM statistics",
            f"{topic} total addressable market revenue",
            f"{bt or topic} industry market size forecast",
        ]
    if key == "problem_statement":
        return [
            f"{niche} industry challenges pain points",
            f"{topic} market problems trends",
            f"why {bt or topic} businesses struggle",
        ]
    if key == "client_pain":
        return [
            f"{audience or 'buyers'} {topic} pain points challenges",
            f"{niche} customer problems cost of inaction",
        ]
    if key == "proof_roi":
        return [
            f"{niche} ROI benchmark case study outcomes",
            f"{topic} industry results statistics",
        ]
    return [f"{niche} {key.replace('_', ' ')}"]


def _research_fallback(key: str, *, topic: str, owner: Dict[str, Any]) -> str:
    """Deprecated — do not inject generic industry copy when search fails."""
    return ""


async def auto_research_requirements(
    *,
    deck_purpose: str,
    topic: str,
    audience: str,
    owner: Dict[str, Any],
    user_context: Dict[str, Any],
    keys: List[str],
    search_fn,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Use web search to fill researchable requirement keys.
    Returns (values to merge into user_context, source per key).
    """
    out: Dict[str, str] = {}
    sources: Dict[str, str] = {}
    parsers = {
        "market_size": lambda t: _parse_market_size(t, topic),
        "problem_statement": lambda t: _parse_industry_narrative(t, topic, kind="problem"),
        "client_pain": lambda t: _parse_industry_narrative(t, topic, kind="problem"),
        "proof_roi": lambda t: _parse_industry_narrative(t, topic, kind="roi"),
    }

    for key in keys:
        if key not in RESEARCHABLE_KEYS:
            continue
        if _ctx_val(user_context, key) or _ctx_val(out, key):
            continue
        parser = parsers.get(key)
        if not parser:
            continue
        for query in _research_queries(key, topic=topic, audience=audience, owner=owner):
            try:
                data = await search_fn(query)
            except Exception:
                data = {}
            if not isinstance(data, dict) or data.get("error"):
                continue
            blob = _search_text(data)
            val = parser(blob) if parser else ""
            if not val:
                answer = _clean(data.get("answer"))
                if _substantive(answer, min_len=25):
                    val = answer[:220]
            if not val and _substantive(blob, min_len=40):
                val = blob[:220]
            if val:
                out[key] = val
                sources[key] = _clean(data.get("source")) or "web"
                break
    return out, sources


def assess_presentation_requirements(
    *,
    deck_purpose: str = "",
    topic: str = "",
    audience: str = "",
    owner: Optional[Dict[str, Any]] = None,
    analytics: Optional[Dict[str, Any]] = None,
    products: Optional[List[Dict[str, Any]]] = None,
    team: Optional[List[Dict[str, Any]]] = None,
    user_context: Optional[Dict[str, Any]] = None,
    research_keys: Optional[set] = None,
) -> Dict[str, Any]:
    """
    Check CRM + user-provided context against deck-type requirements.
    Returns ready=True only when every required field is satisfied.
    """
    owner = owner or {}
    analytics = analytics or {}
    products = products or []
    team = team or []
    user_context = user_context or {}
    research_keys = research_keys or set()

    purpose = _resolve_deck_purpose(deck_purpose, audience)
    required_keys = _PURPOSE_REQUIRED_KEYS.get(purpose, _PURPOSE_REQUIRED_KEYS["other"])
    purpose_researchable = researchable_keys_for_purpose(purpose)

    found: Dict[str, Any] = {}
    missing: List[Dict[str, str]] = []

    for key in required_keys:
        ok, source = _field_satisfied(
            key,
            owner=owner,
            analytics=analytics,
            products=products,
            team=team,
            user_context=user_context,
            topic=topic,
            audience=audience,
        )
        meta = _REQUIREMENT_CATALOG.get(key, {})
        if ok:
            val = _ctx_val(user_context, key)
            src = "web" if key in research_keys else source
            if not val:
                if key == "business_identity":
                    val = _clean(owner.get("business_name"))
                elif key == "traction" and analytics.get("customers_count"):
                    val = f"{analytics['customers_count']} customers on file"
                elif key == "solution" and products:
                    val = ", ".join(_clean(p.get("name")) for p in products[:3] if _clean(p.get("name")))
            found[key] = {"source": src, "preview": (val or src)[:120]}
        elif key in purpose_researchable or key in research_keys or key in RESEARCHABLE_KEYS:
            # Web-searchable for this deck type — never prompt the user
            continue
        else:
            missing.append({
                "key": key,
                "label": meta.get("label", key.replace("_", " ").title()),
                "question": meta.get("question", f"Please provide: {key.replace('_', ' ')}."),
            })

    return {
        "ready": len(missing) == 0,
        "deck_purpose": purpose,
        "topic": _clean(topic),
        "audience": _clean(audience),
        "found": found,
        "missing": missing,
        "missing_count": len(missing),
        "instruction": build_agent_requirements_note(
            {"ready": len(missing) == 0, "missing": missing},
            {k: _ctx_val(user_context, k) for k in research_keys if _ctx_val(user_context, k)},
        ),
    }


def finalize_presentation_requirements_assessment(
    assessment: Dict[str, Any],
    *,
    owner: Dict[str, Any],
    auto_researched: Dict[str, str],
    user_context: Dict[str, str],
    topic: str,
    audience: str,
    deck_purpose: str,
) -> Dict[str, Any]:
    """Attach business profile + readiness summary for UI and agent."""
    out = dict(assessment)
    out["topic"] = topic
    out["audience"] = audience
    out["user_context"] = user_context
    out["business_profile"] = build_business_profile(
        owner,
        topic=topic,
        deck_purpose=str(out.get("deck_purpose") or deck_purpose),
        audience=audience,
    )
    out["readiness_summary"] = build_readiness_summary(
        out.get("found") or {},
        auto_researched,
    )
    if out.get("ready"):
        out["chat_reply"] = (
            "All set — I've loaded your business profile, researched what's public, "
            "and collected your details. Building your slide plan now."
        )
    return out


def _option(option_id: str, label: str, value: str) -> Dict[str, str]:
    return {"id": option_id, "label": label, "value": value}


def _product_pricing_options(products: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    opts: List[Dict[str, str]] = []
    for i, p in enumerate(products[:6]):
        name = _clean(p.get("name"))
        if not name:
            continue
        price = p.get("discount_price") or p.get("price")
        price_txt = f" — {price}" if price not in (None, "", 0) else ""
        opts.append(_option(f"product_{i}", f"{name}{price_txt}", f"{name}{price_txt}"))
    return opts


def _team_options(team: List[Dict[str, Any]], owner: Dict[str, Any]) -> List[Dict[str, str]]:
    opts: List[Dict[str, str]] = []
    for i, m in enumerate(team[:6]):
        name = _clean(m.get("name") or m.get("full_name"))
        role = _clean(m.get("role") or m.get("title"))
        if not name:
            continue
        label = f"{name} — {role}" if role else name
        opts.append(_option(f"member_{i}", label, label))
    owner_name = _clean(owner.get("owner_name"))
    if owner_name and not any(owner_name in o["label"] for o in opts):
        opts.insert(0, _option("founder", f"{owner_name} — Founder", f"{owner_name} — Founder"))
    return opts


def _traction_options(analytics: Dict[str, Any]) -> List[Dict[str, str]]:
    opts: List[Dict[str, str]] = []
    customers = int(analytics.get("customers_count") or 0)
    if customers:
        opts.append(_option("customers", f"{customers} customers in CRM", f"{customers} customers"))
    orders = int(analytics.get("active_orders") or 0)
    if orders:
        opts.append(_option("orders", f"{orders} active orders", f"{orders} active orders"))
    rev = float(analytics.get("sales_revenue_today") or 0)
    if rev > 0:
        opts.append(_option("revenue_today", f"Revenue today: {rev:,.0f}", f"Revenue today: {rev:,.0f}"))
    bookings = int(analytics.get("bookings_today") or 0)
    if bookings:
        opts.append(_option("bookings", f"{bookings} bookings today", f"{bookings} bookings today"))
    return opts


def _pain_options(deck_purpose: str, business_type: str) -> List[Dict[str, str]]:
    bt = (business_type or "").lower()
    if deck_purpose == "sales":
        base = [
            "Leads go cold from slow follow-up",
            "Current tools are too expensive or complex",
            "Team wastes time on manual admin",
            "Hard to prove ROI to stakeholders",
            "Poor visibility into pipeline and performance",
        ]
    else:
        base = [
            "Large underserved market with broken incumbents",
            "Customers lose money from slow or manual processes",
            "Existing solutions are too expensive or fragmented",
            "Regulation or compliance creates urgent need",
            "AI/automation unlocks a step-change in efficiency",
        ]
    if "retail" in bt or "shop" in bt:
        base.insert(0, "Inventory and sales channels are disconnected")
    if "service" in bt or "consult" in bt:
        base.insert(0, "Client delivery doesn't scale without hiring")
    opts = [_option(f"pain_{i}", text, text) for i, text in enumerate(base[:5])]
    return opts


def parse_requirements_submission(content: str) -> Dict[str, str]:
    """Parse `- **key**: value` lines from checklist submission messages."""
    out: Dict[str, str] = {}
    for line in (content or "").split("\n"):
        m = re.match(r"^\s*[-*]?\s*\*\*([a-z_]+)\*\*:\s*(.+)\s*$", line.strip(), re.I)
        if not m:
            continue
        val = _clean(m.group(2))
        if val:
            out[m.group(1).lower()] = val
    return out


PRESENTATION_CONTEXT_TOOLS = frozenset({
    "check_presentation_requirements",
    "plan_visual_presentation",
})


def collect_presentation_user_context(
    *,
    args_user_context: Optional[Dict[str, Any]] = None,
    user_message: str = "",
    conversation_messages: Optional[List[Dict[str, Any]]] = None,
    full_history: Optional[List[Dict[str, Any]]] = None,
    prior_steps: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, str]:
    """Merge checklist answers from chat history so re-checks don't lose user input."""
    merged: Dict[str, str] = {}

    for msg in full_history or []:
        if msg.get("role") != "user":
            continue
        merged.update(parse_requirements_submission(str(msg.get("content") or "")))

    for msg in conversation_messages or []:
        if msg.get("role") != "user":
            continue
        merged.update(parse_requirements_submission(str(msg.get("content") or "")))

    merged.update(parse_requirements_submission(user_message))

    for step in reversed(prior_steps or []):
        if step.get("tool") != "check_presentation_requirements":
            continue
        prev = (step.get("result") or {}).get("user_context") or {}
        for key, val in prev.items():
            cleaned = _clean(val)
            if cleaned:
                merged[key] = cleaned
        break

    for key, val in (args_user_context or {}).items():
        cleaned = _clean(val)
        if cleaned:
            merged[key] = cleaned

    return merged


def enrich_presentation_tool_args(
    tool_name: str,
    args: Optional[Dict[str, Any]],
    *,
    user_message: str = "",
    conversation_messages: Optional[List[Dict[str, Any]]] = None,
    full_history: Optional[List[Dict[str, Any]]] = None,
    prior_steps: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if tool_name not in PRESENTATION_CONTEXT_TOOLS:
        return dict(args or {})
    out = dict(args or {})
    out["user_context"] = collect_presentation_user_context(
        args_user_context=out.get("user_context"),
        user_message=user_message,
        conversation_messages=conversation_messages,
        full_history=full_history,
        prior_steps=prior_steps,
    )
    return out


_SLIDE_COUNT_RE = re.compile(r"\b(\d+)\s*slides?\b", re.I)
_PURPOSE_PATTERNS = (
    (re.compile(r"investor|fundraising|fund.?raise|pitch deck", re.I), "investor_pitch"),
    (re.compile(r"sales|client proposal|proposal", re.I), "sales"),
    (re.compile(r"internal|team meeting", re.I), "internal"),
    (re.compile(r"training|onboarding|event", re.I), "training"),
)


def infer_slide_count_from_text(text: str, *, default: int = 8) -> int:
    for blob in (text or "").split("\n"):
        m = _SLIDE_COUNT_RE.search(blob)
        if m:
            n = int(m.group(1))
            if 3 <= n <= 20:
                return n
    return default


def infer_deck_purpose_from_text(text: str, *, default: str = "other") -> str:
    for pattern, purpose in _PURPOSE_PATTERNS:
        if pattern.search(text or ""):
            return purpose
    return default


def infer_presentation_session(
    *,
    deck_purpose: str = "",
    topic: str = "",
    audience: str = "",
    slide_count: int = 0,
    messages: Optional[List[Dict[str, Any]]] = None,
    prior_user_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Recover deck metadata from API args + recent chat when the agent omitted fields."""
    transcript = "\n".join(
        str(m.get("content") or "")
        for m in (messages or [])
        if m.get("role") in ("user", "assistant")
    )
    purpose = (deck_purpose or "").strip().lower()
    if purpose not in _PURPOSE_REQUIRED_KEYS:
        purpose = infer_deck_purpose_from_text(transcript, default="investor_pitch")
    count = slide_count or infer_slide_count_from_text(transcript, default=5)
    top = (topic or "").strip()
    if not top:
        top = _clean((prior_user_context or {}).get("topic")) or "Presentation"
    aud = (audience or "").strip()
    if not aud:
        if purpose == "investor_pitch":
            aud = "investors"
        elif purpose == "sales":
            aud = "prospective clients"
    return {
        "deck_purpose": purpose,
        "topic": top,
        "audience": aud,
        "slide_count": count,
    }


def build_agent_requirements_note(
    assessment: Dict[str, Any],
    auto_researched: Optional[Dict[str, str]] = None,
) -> str:
    missing = assessment.get("missing") or []
    if assessment.get("ready"):
        return (
            "All requirements satisfied. Call plan_visual_presentation immediately using "
            "user_context from this tool result. Do NOT ask any more questions."
        )
    labels = [
        requirement_label(str(m.get("key") or ""))
        for m in missing
        if (m.get("key") or "") not in RESEARCHABLE_KEYS
    ]
    researched_labels = [
        requirement_label(k) for k in (auto_researched or {}) if _clean((auto_researched or {}).get(k))
    ]
    if not labels:
        if researched_labels:
            return (
                f"Context gathered via CRM + web search ({', '.join(researched_labels)}). "
                "Proceed to plan_visual_presentation — do NOT re-ask for those topics."
            )
        return (
            "Proceed to plan_visual_presentation using CRM data and web search for any "
            "industry context still missing from user_context."
        )
    researched_txt = ", ".join(researched_labels) if researched_labels else "topic-relevant public data"
    return (
        f"Checklist UI only — user must fill: {', '.join(labels)}. "
        f"Already gathered from CRM/web (do NOT ask in chat): {researched_txt}."
    )


def build_requirements_chat_reply(
    assessment: Dict[str, Any],
    checklist: List[Dict[str, Any]],
    auto_researched: Optional[Dict[str, str]] = None,
) -> str:
    """Deterministic user-facing reply — points to checklist only; researched data lives in the UI card."""
    if assessment.get("ready"):
        return "All set — building your slide plan now."
    labels = [str(c.get("label") or c.get("key") or "").strip() for c in checklist if c.get("label") or c.get("key")]
    if not labels:
        return "Building your slide plan now."
    if len(labels) == 1:
        return f"One detail left in the checklist below: **{labels[0]}**."
    return (
        f"Please complete the {len(labels)} items in the checklist below: "
        f"{', '.join(labels)}."
    )


def strip_researchable_checklist_items(
    checklist: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Remove auto-researched fields — user should never see TAM/SAM/SOM prompts."""
    return [item for item in checklist if (item.get("key") or "") not in RESEARCHABLE_KEYS]


def build_requirements_checklist(
    assessment: Dict[str, Any],
    *,
    owner: Optional[Dict[str, Any]] = None,
    analytics: Optional[Dict[str, Any]] = None,
    products: Optional[List[Dict[str, Any]]] = None,
    team: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Turn missing requirements into UI checklist items with selectable options
    where CRM data or common choices apply.
    """
    owner = owner or {}
    analytics = analytics or {}
    products = products or []
    team = team or []
    purpose = assessment.get("deck_purpose") or "other"
    business_type = _clean(owner.get("business_type"))

    checklist: List[Dict[str, Any]] = []
    for m in assessment.get("missing") or []:
        key = m.get("key") or ""
        if key in RESEARCHABLE_KEYS:
            continue
        item: Dict[str, Any] = {
            "key": key,
            "label": m.get("label") or key,
            "question": m.get("question") or "",
            "input_type": "text",
            "required": True,
            "options": [],
            "allow_custom": True,
            "custom_placeholder": "",
            "select_all_hint": False,
        }

        if key == "business_identity":
            item["input_type"] = "text"
            if not _clean(owner.get("business_name")):
                item["custom_placeholder"] = "Business name"
            elif not (_clean(owner.get("email")) or _clean(owner.get("phone_number"))):
                item["question"] = "Best contact email or phone for the closing slide?"
                item["custom_placeholder"] = "email@company.com or +1 555 0100"

        elif key in ("problem_statement", "client_pain"):
            pains = _pain_options(purpose if key == "client_pain" else "investor_pitch", business_type)
            item["input_type"] = "multi_choice"
            item["select_all_hint"] = True
            item["options"] = pains
            item["custom_placeholder"] = "Or describe the pain in your own words…"

        elif key == "value_proposition":
            hint = _clean(owner.get("business_description_hint") or owner.get("products_services_hint"))
            if hint:
                item["input_type"] = "single_choice"
                item["options"] = [
                    _option("crm_hint", f"Use from profile: {hint[:80]}", hint[:200]),
                    _option("custom", "Write a different one-liner", ""),
                ]
                item["allow_custom"] = True
                item["custom_placeholder"] = "One sentence — what you do and for whom"
            else:
                item["custom_placeholder"] = "One sentence — what you do and for whom"

        elif key == "solution":
            prod_opts = [
                _option(f"prod_{i}", _clean(p.get("name")), _clean(p.get("name")))
                for i, p in enumerate(products[:5])
                if _clean(p.get("name"))
            ]
            if prod_opts:
                item["input_type"] = "multi_choice"
                item["select_all_hint"] = True
                item["options"] = prod_opts
                item["custom_placeholder"] = "Add how it solves the problem…"
            else:
                item["custom_placeholder"] = "What you offer and how it helps"

        elif key == "market_size":
            item["input_type"] = "text"
            item["custom_placeholder"] = "e.g. $4B TAM · $800M SAM · $120M SOM"

        elif key == "traction" or key == "proof_roi":
            tr = _traction_options(analytics)
            if tr:
                item["input_type"] = "multi_choice"
                item["select_all_hint"] = True
                item["options"] = tr
                item["custom_placeholder"] = "Add growth rate, retention, case studies, or ROI…"
            else:
                item["custom_placeholder"] = "2–3 proof points with numbers if possible"

        elif key == "team":
            tm = _team_options(team, owner)
            if tm:
                item["input_type"] = "multi_choice"
                item["select_all_hint"] = True
                item["options"] = tm
                item["custom_placeholder"] = "Add other key people (name, role, credential)…"
            else:
                item["custom_placeholder"] = "Name, role, and one credential each"

        elif key == "funding_ask":
            item["input_type"] = "single_choice"
            item["options"] = [
                _option("pre_seed", "Pre-seed — $250K–$500K", "Raising $250K–$500K pre-seed"),
                _option("seed", "Seed — $1M–$2M", "Raising $1M–$2M seed round"),
                _option("series_a", "Series A — $3M–$8M", "Raising $3M–$8M Series A"),
                _option("custom", "Different amount — I'll specify", ""),
            ]
            item["allow_custom"] = True
            item["custom_placeholder"] = "Amount, stage, and use of funds"

        elif key == "pricing_offer":
            priced = _product_pricing_options(products)
            if priced:
                item["input_type"] = "multi_choice"
                item["select_all_hint"] = True
                item["options"] = priced
                item["custom_placeholder"] = "Add packages, discounts, or terms…"
            else:
                item["custom_placeholder"] = "Packages, prices, and what's included"

        elif key == "meeting_topic":
            item["custom_placeholder"] = "Main topic or decision for this deck"

        elif key == "key_updates":
            upd = _traction_options(analytics)
            if upd:
                item["input_type"] = "multi_choice"
                item["select_all_hint"] = True
                item["options"] = upd
                item["custom_placeholder"] = "Other updates, metrics, or findings…"
            else:
                item["custom_placeholder"] = "Main updates or data to cover"

        elif key == "next_steps":
            item["input_type"] = "multi_choice"
            item["select_all_hint"] = True
            item["options"] = [
                _option("approve", "Approve the plan / budget", "Approve the proposed plan"),
                _option("assign", "Assign owners and deadlines", "Assign owners and deadlines"),
                _option("pilot", "Run a pilot or trial", "Run a pilot next quarter"),
                _option("followup", "Schedule a follow-up review", "Schedule follow-up review"),
            ]
            item["custom_placeholder"] = "Other next steps…"

        elif key == "learning_objectives":
            item["input_type"] = "multi_choice"
            item["select_all_hint"] = True
            item["options"] = [
                _option("understand", "Understand core concepts", "Understand core concepts"),
                _option("apply", "Apply skills on the job", "Apply skills on the job"),
                _option("comply", "Meet compliance requirements", "Meet compliance requirements"),
                _option("onboard", "Complete onboarding successfully", "Complete onboarding successfully"),
            ]
            item["custom_placeholder"] = "Other learning goals…"

        elif key == "training_content":
            prod_opts = [
                _option(f"mod_{i}", _clean(p.get("name")), _clean(p.get("name")))
                for i, p in enumerate(products[:4])
                if _clean(p.get("name"))
            ]
            if prod_opts:
                item["input_type"] = "multi_choice"
                item["select_all_hint"] = True
                item["options"] = prod_opts
            item["custom_placeholder"] = "Modules or concepts to teach"

        elif key == "target_audience":
            item["input_type"] = "single_choice"
            item["options"] = [
                _option("new_hires", "New hires / onboarding", "New hires during onboarding"),
                _option("sales_team", "Sales team", "Sales team"),
                _option("ops_team", "Operations / support", "Operations and support staff"),
                _option("leadership", "Leadership / managers", "Leadership and managers"),
                _option("custom", "Other audience", ""),
            ]
            item["allow_custom"] = True
            item["custom_placeholder"] = "Role and experience level"

        checklist.append(item)
    return strip_researchable_checklist_items(checklist)


def _synthesize_body(sd: Dict[str, Any]) -> List[str]:
    """Build display bullets from structured slide fields when body is thin."""
    body = [_clean(b) for b in (sd.get("body") or []) if _clean(b)]
    if len(body) >= 2:
        return body[:3]

    layout = (sd.get("layout") or "content").lower()
    out: List[str] = list(body)

    if layout == "stat_callout":
        for st in (sd.get("stats") or [])[:3]:
            num = _clean(st.get("number"))
            label = _clean(st.get("label"))
            sub = _clean(st.get("sublabel") or st.get("sub"))
            if num and label:
                line = f"{num} — {label}"
                if sub:
                    line += f" ({sub})"
                out.append(line[:80])

    elif layout == "icon_grid":
        for it in (sd.get("items") or [])[:3]:
            label = _clean(it.get("label"))
            desc = _clean(it.get("description"))
            if label:
                out.append(f"{label}: {desc}"[:80] if desc else label[:80])

    elif layout == "flow":
        for st in (sd.get("steps") or [])[:3]:
            label = _clean(st.get("label"))
            desc = _clean(st.get("description"))
            if label:
                out.append(f"{label} — {desc}"[:80] if desc else label[:80])

    elif layout == "two_column":
        for side in (sd.get("left_items") or sd.get("left") or [])[:2]:
            if _clean(side):
                out.append(_clean(side)[:80])
        for side in (sd.get("right_items") or sd.get("right") or [])[:1]:
            if isinstance(side, dict):
                num = _clean(side.get("number"))
                label = _clean(side.get("label"))
                if num and label:
                    out.append(f"{num} {label}"[:80])
            elif _clean(side):
                out.append(_clean(side)[:80])

    elif layout == "comparison_table":
        for row in (sd.get("features") or [])[:3]:
            feat = _clean(row.get("feature"))
            vals = row.get("values") or []
            if feat and vals:
                out.append(f"{feat}: {vals[0]}"[:80])

    elif layout == "timeline":
        for ms in (sd.get("milestones") or [])[:3]:
            label = _clean(ms.get("label"))
            desc = _clean(ms.get("description"))
            if label:
                out.append(f"{label} — {desc}"[:80] if desc else label[:80])

    title = _clean(sd.get("title"))
    if len(out) < 2 and title:
        out.append(title[:80])

    return out[:3]


def _default_image_prompt(sd: Dict[str, Any], topic: str, idx: int) -> str:
    layout = (sd.get("layout") or ("title" if idx == 0 else "content")).lower()
    base = _LAYOUT_SCENES.get(layout, _LAYOUT_SCENES["content"])
    title = _clean(sd.get("title"))
    if title and layout not in ("title", "closing"):
        return f"{base}, mood suited to '{title[:40]}'"
    if topic and layout == "title":
        return f"{base}, fitting a presentation about {topic[:50]}"
    return base


def enrich_slide_plan(
    slides: List[Dict[str, Any]],
    *,
    topic: str,
    audience: str = "",
    deck_purpose: str = "",
    owner: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Fill gaps from CRM owner profile and structured fields so the UI plan
    is client-ready with minimal user edits.
    """
    owner = owner or {}
    biz = _clean(owner.get("business_name"))
    owner_name = _clean(owner.get("owner_name"))
    phone = _clean(owner.get("phone_number") or owner.get("phone") or owner.get("business_phone"))
    email = _clean(owner.get("email") or owner.get("business_email"))
    website = _clean(owner.get("website") or owner.get("business_website"))
    tagline = _clean(
        owner.get("tagline")
        or owner.get("business_tagline")
        or (owner.get("business_description_hint") or "")[:100]
    )

    contact_parts = [p for p in (email, phone) if p]
    contact = " · ".join(contact_parts)

    out: List[Dict[str, Any]] = []
    for i, raw in enumerate(slides):
        sd = dict(raw or {})
        layout = (_clean(sd.get("layout")) or ("title" if i == 0 else "closing" if i == len(slides) - 1 else "content")).lower()
        sd["layout"] = layout
        sd["is_title"] = i == 0

        if layout == "title":
            if not _clean(sd.get("title")) and biz:
                sd["title"] = biz
            # Fill tagline only if it's not already the company name
            _biz_lower = (biz or "").strip().lower()
            _existing_tag = _clean(sd.get("tagline") or "")
            if _existing_tag and _existing_tag.lower() == _biz_lower:
                sd["tagline"] = ""  # AI set it to company name — clear it
            if not _clean(sd.get("tagline")):
                if tagline and tagline.strip().lower() != _biz_lower:
                    sd["tagline"] = tagline
                elif topic and topic.strip().lower() != _biz_lower:
                    sd["tagline"] = topic[:100]
            if not _clean(sd.get("website")) and website:
                sd["website"] = website
            if not _clean(sd.get("founder")) and owner_name:
                sd["founder"] = owner_name

        if layout == "closing":
            if not _clean(sd.get("contact")) and contact:
                sd["contact"] = contact
            if not _clean(sd.get("cta")):
                purpose = (deck_purpose or "").lower()
                aud = audience.lower()
                if purpose == "investor_pitch" or "investor" in aud:
                    sd["cta"] = "Let's talk."
                elif purpose == "sales" or "client" in aud or "sales" in aud:
                    sd["cta"] = "Book a call."
                elif purpose == "training":
                    sd["cta"] = "Start learning."
                else:
                    sd["cta"] = "Let's connect."
            if not _clean(sd.get("tagline")) and tagline and tagline.strip().lower() != _biz_lower:
                sd["tagline"] = tagline
            if not _clean(sd.get("title")) and biz:
                sd["title"] = biz

        sd["body"] = existing_body[:3] if (existing_body := [_clean(b) for b in (sd.get("body") or []) if _clean(b)]) else _synthesize_body(sd)

        prompt = _clean(sd.get("image_prompt") or sd.get("image_concept"))
        if not prompt:
            prompt = _default_image_prompt(sd, topic, i)
        sd["image_prompt"] = prompt
        sd["image_concept"] = prompt

        if not _clean(sd.get("title")):
            sd["title"] = f"Slide {i + 1}"

        out.append(sd)

    return out


def load_plan_from_conversation_message(
    messages: List[Dict[str, Any]],
    message_index: int,
) -> Tuple[List[Dict[str, Any]], str, bool]:
    """Load the saved slide plan from an assistant message (source of truth after Update plan)."""
    if message_index < 0 or message_index >= len(messages):
        return [], "", False
    msg = messages[message_index]
    if msg.get("role") != "assistant":
        return [], "", False
    for step in reversed(msg.get("steps") or []):
        if step.get("tool") != "plan_visual_presentation":
            continue
        result = step.get("result") or {}
        slides = result.get("slides")
        if result.get("plan_ready") and isinstance(slides, list) and slides:
            return (
                [dict(s) for s in slides],
                str(result.get("topic") or "").strip(),
                bool(result.get("user_edited")),
            )
    return [], "", False


def resolve_slides_for_generation(
    *,
    client_slides: List[Dict[str, Any]],
    messages: Optional[List[Dict[str, Any]]] = None,
    message_index: Optional[int] = None,
    client_edited: bool = False,
) -> Tuple[List[Dict[str, Any]], str, bool]:
    """
    Prefer the plan saved on the conversation message when the user tapped Update plan.
    Falls back to the slides sent from the UI.
    """
    db_topic = ""
    if messages is not None and message_index is not None:
        db_slides, db_topic, db_edited = load_plan_from_conversation_message(messages, message_index)
        if db_edited and db_slides:
            return db_slides, db_topic, True
        if db_slides and not client_slides:
            return db_slides, db_topic, db_edited
    if client_slides:
        return list(client_slides), db_topic, client_edited
    return [], db_topic, False


def finalize_slides_for_generation(
    slides: List[Dict[str, Any]],
    *,
    topic: str = "",
    user_edited: bool = False,
) -> List[Dict[str, Any]]:
    """
    Prepare slides for Gemini. When user_edited=True, use ONLY the saved title/body
    (ignore stats/items/etc. so old structured data cannot override edits).
    """
    normalized = normalize_slide_plan(slides)
    if not user_edited:
        for i, sd in enumerate(normalized):
            if len(sd.get("body") or []) < 2:
                sd["body"] = _synthesize_body(sd)
            prompt = _clean(sd.get("image_prompt") or sd.get("image_concept"))
            if not prompt:
                sd["image_prompt"] = _default_image_prompt(sd, topic, i)
                sd["image_concept"] = sd["image_prompt"]
        return normalized

    out: List[Dict[str, Any]] = []
    for i, sd in enumerate(normalized):
        prompt = _default_image_prompt(sd, topic, i)
        out.append({
            "title": sd["title"],
            "layout": sd["layout"],
            "body": sd.get("body") or [],
            "is_title": sd["is_title"],
            "image_prompt": prompt,
            "image_concept": prompt,
        })
    return out


def normalize_slide_plan(slides: List[Dict[str, Any]], *, max_slides: int = 20) -> List[Dict[str, Any]]:
    """Normalize slide dicts before Gemini generation."""
    out: List[Dict[str, Any]] = []
    for i, raw in enumerate(slides[:max_slides]):
        sd = dict(raw or {})
        body = sd.get("body") or []
        if isinstance(body, str):
            body = [body]
        sd["body"] = [str(b).strip()[:80] for b in body if str(b).strip()][:3]
        sd["title"] = str(sd.get("title") or f"Slide {i + 1}").strip()
        layout = (sd.get("layout") or "").strip().lower()
        if not layout:
            layout = "title" if i == 0 else "content"
        sd["layout"] = layout
        sd["is_title"] = i == 0
        prompt = (sd.get("image_prompt") or sd.get("image_concept") or "").strip()
        if prompt:
            sd["image_prompt"] = prompt
            sd["image_concept"] = prompt
        out.append(sd)
    return out


def prepare_slide_plan(
    slides: List[Dict[str, Any]],
    *,
    topic: str,
    audience: str = "",
    deck_purpose: str = "",
    owner: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Enrich then normalize — single entry for plan + generate paths."""
    enriched = enrich_slide_plan(
        slides, topic=topic, audience=audience, deck_purpose=deck_purpose, owner=owner
    )
    return normalize_slide_plan(enriched)


def build_generation_reply(result: Dict[str, Any], slide_count: int) -> str:
    if result.get("error"):
        return f"Sorry — presentation generation failed: {result['error']}"
    if result.get("success") and result.get("url"):
        count = result.get("slide_count") or slide_count
        return (
            f"Your presentation is ready — **{count} slides** with AI-designed visuals.\n\n"
            f"📄 **[Download presentation]({result['url']})**"
        )
    return "Presentation generation did not complete. Please try again."
