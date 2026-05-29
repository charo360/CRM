"""Document requirements, branding rules, and premium export defaults."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .presentation_plan import (
    _clean,
    _ctx_val,
    _substantive,
    _option,
    parse_requirements_submission,
)

CHECKLIST_VERSION = 2

# ── URL sanitization (documents must not invent websites) ─────────────────────

_DOCUMENT_URL_PATTERNS: List[re.Pattern] = [
    re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE),
    re.compile(r"\bwww\.[a-z0-9-]+\.[a-z]{2,}(?:/[^\s)>\]]*)?", re.IGNORECASE),
    re.compile(
        r"\b[a-z0-9][a-z0-9-]{0,62}\.(?:com|co|shop|io|net|org|app|store|biz|us|uk|in|me|dev|ai|pro|chat)\b",
        re.IGNORECASE,
    ),
]

_BLOCKED_DOMAINS = frozenset({
    "zilochat.com",
    "www.zilochat.com",
})
# CRM/platform domains the model often invents — never use unless explicitly saved in Settings.


def _url_host(raw: str) -> str:
    text = (raw or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^www\.", "", text)
    return text.split("/")[0].split("?")[0].split("#")[0].strip()


def _email_domain(email: str) -> str:
    e = (email or "").strip().lower()
    if "@" not in e:
        return ""
    return e.split("@", 1)[1].split(">", 1)[0].strip()


def _allowed_website_hosts(*, website_url: str = "", email: str = "") -> set[str]:
    hosts: set[str] = set()
    host = _url_host(website_url)
    if host:
        hosts.add(host)
    domain = _email_domain(email)
    if domain:
        hosts.add(domain)
    return hosts


def _url_is_allowed(match: str, allowed_hosts: set[str]) -> bool:
    if not allowed_hosts:
        return False
    host = _url_host(match)
    if not host:
        return False
    for allowed in allowed_hosts:
        if host == allowed or host.endswith(f".{allowed}") or allowed.endswith(f".{host}"):
            return True
    return False


def _cleanup_contact_separators(text: str) -> str:
    text = re.sub(r"\s*·\s*·+", " · ", text)
    text = re.sub(r"(?<=\S)\s+·\s+(?=\s|$)", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def sanitize_document_text(
    text: str,
    *,
    website_url: str = "",
    email: str = "",
) -> str:
    """Remove URLs/domains not matching Settings website or business email domain."""
    if not (text or "").strip():
        return text or ""
    from .document_generator import _fix_text_encoding

    text = _fix_text_encoding(text)
    allowed = _allowed_website_hosts(website_url=website_url, email=email)
    out = text
    for pattern in _DOCUMENT_URL_PATTERNS:
        def _repl(match: re.Match, _allowed: set[str] = allowed) -> str:
            token = match.group(0)
            host = _url_host(token)
            # Platform placeholders — strip unless the owner saved this exact host in Settings
            if host in _BLOCKED_DOMAINS:
                if _allowed and _url_is_allowed(token, _allowed):
                    return token
                return ""
            if _url_is_allowed(token, _allowed):
                return token
            return ""

        out = pattern.sub(_repl, out)
    return _cleanup_contact_separators(out)


def sanitize_document_style(
    style: Dict[str, Any],
    *,
    website_url: str = "",
    email: str = "",
) -> Dict[str, Any]:
    """Strip invented URLs from saved header/footer/signature fields."""
    out = dict(style or {})
    for key in ("header_text", "header_contact", "footer_text", "signature_contact"):
        if key in out and isinstance(out[key], str):
            out[key] = sanitize_document_text(
                out[key], website_url=website_url, email=email,
            )
    return out


def build_website_policy(owner: Dict[str, Any]) -> Dict[str, str]:
    website = _clean(owner.get("website_url"))
    if website:
        return {
            "website_url": website,
            "rule": "Use this website only. Never invent or guess another domain.",
        }
    return {
        "website_url": "",
        "rule": (
            "No website is saved in Settings — omit website/URL lines entirely. "
            "Never guess or invent a domain from the business name."
        ),
    }

# ISO / name / currency → country key for bank lists
_COUNTRY_ALIASES: Dict[str, str] = {
    "ke": "kenya", "kenya": "kenya", "kes": "kenya",
    "ng": "nigeria", "nigeria": "nigeria", "ngn": "nigeria",
    "za": "south_africa", "south africa": "south_africa", "zar": "south_africa",
    "ug": "uganda", "uganda": "uganda", "ugx": "uganda",
    "tz": "tanzania", "tanzania": "tanzania", "tzs": "tanzania",
    "gh": "ghana", "ghana": "ghana", "ghs": "ghana",
    "us": "usa", "usa": "usa", "united states": "usa", "usd": "usa",
    "gb": "uk", "uk": "uk", "united kingdom": "uk", "gbp": "uk",
    "in": "india", "india": "india", "inr": "india",
    "ae": "uae", "uae": "uae", "united arab emirates": "uae", "aed": "uae",
    "rw": "rwanda", "rwanda": "rwanda", "rwf": "rwanda",
    "et": "ethiopia", "ethiopia": "ethiopia", "etb": "ethiopia",
}

_BANKS_BY_COUNTRY: Dict[str, List[str]] = {
    "kenya": [
        "Equity Bank Kenya",
        "KCB Bank",
        "Co-operative Bank of Kenya",
        "Absa Bank Kenya",
        "NCBA Bank",
        "Stanbic Bank Kenya",
        "Diamond Trust Bank (DTB)",
        "I&M Bank",
        "Standard Chartered Kenya",
    ],
    "nigeria": [
        "Access Bank",
        "GTBank (Guaranty Trust Bank)",
        "Zenith Bank",
        "United Bank for Africa (UBA)",
        "First Bank of Nigeria",
        "Stanbic IBTC Bank",
        "Fidelity Bank",
        "Ecobank Nigeria",
    ],
    "south_africa": [
        "Standard Bank",
        "First National Bank (FNB)",
        "Absa Bank",
        "Nedbank",
        "Capitec Bank",
        "Investec",
    ],
    "uganda": [
        "Stanbic Bank Uganda",
        "Centenary Bank",
        "Equity Bank Uganda",
        "DFCU Bank",
        "Absa Bank Uganda",
        "Bank of Uganda (regulated lenders)",
    ],
    "tanzania": [
        "CRDB Bank",
        "NMB Bank",
        "NBC Bank",
        "Stanbic Bank Tanzania",
        "Equity Bank Tanzania",
    ],
    "ghana": [
        "GCB Bank",
        "Ecobank Ghana",
        "Standard Chartered Ghana",
        "Absa Bank Ghana",
        "Fidelity Bank Ghana",
    ],
    "usa": [
        "JPMorgan Chase",
        "Bank of America",
        "Wells Fargo",
        "Citibank",
        "U.S. Bank",
    ],
    "uk": [
        "Barclays",
        "HSBC UK",
        "Lloyds Bank",
        "NatWest",
        "Santander UK",
    ],
    "india": [
        "State Bank of India (SBI)",
        "HDFC Bank",
        "ICICI Bank",
        "Axis Bank",
        "Punjab National Bank",
    ],
    "uae": [
        "Emirates NBD",
        "First Abu Dhabi Bank (FAB)",
        "Abu Dhabi Commercial Bank (ADCB)",
        "Mashreq Bank",
        "Dubai Islamic Bank",
    ],
    "rwanda": [
        "Bank of Kigali",
        "Equity Bank Rwanda",
        "I&M Bank Rwanda",
        "Cogebanque",
    ],
    "ethiopia": [
        "Commercial Bank of Ethiopia",
        "Awash Bank",
        "Dashen Bank",
        "Bank of Abyssinia",
    ],
}

# ── Requirement catalog (owner-only facts the CRM cannot infer) ───────────────

_REQUIREMENT_CATALOG: Dict[str, Dict[str, str]] = {
    "recipient_name": {
        "label": "Recipient name",
        "question": "Who is this document addressed to? (Full name of the client, investor, or contact)",
    },
    "recipient_company": {
        "label": "Recipient company",
        "question": "What company or organisation is this for?",
    },
    "client_problem": {
        "label": "Client problem / goal",
        "question": "What specific problem, goal, or opportunity should this document address?",
    },
    "proposed_solution": {
        "label": "Proposed solution",
        "question": "What are you proposing to deliver or solve? Be specific.",
    },
    "pricing_offer": {
        "label": "Pricing / offer",
        "question": "What is the price, budget, or offer? Include currency and terms if known.",
    },
    "project_scope": {
        "label": "Project scope",
        "question": "What are the main deliverables and boundaries of this project?",
    },
    "timeline": {
        "label": "Timeline",
        "question": "What are the key dates or milestones? (e.g. start date, delivery in 6 weeks)",
    },
    "contract_party": {
        "label": "Other party",
        "question": "Who is the other party in this agreement? (Company name and contact)",
    },
    "contract_terms": {
        "label": "Key terms",
        "question": "What are the non-negotiable terms? (payment schedule, duration, deliverables)",
    },
    "bank_name": {
        "label": "Bank / lender",
        "question": "Which bank or lender is this application for? (Exact institution name)",
    },
    "loan_amount": {
        "label": "Loan amount",
        "question": "How much are you applying for? Include currency.",
    },
    "loan_purpose": {
        "label": "Loan purpose",
        "question": "What will the funds be used for? Be specific.",
    },
    "report_period": {
        "label": "Reporting period",
        "question": "What time period should this report cover? (e.g. Q1 2026, March 2026)",
    },
    "report_focus": {
        "label": "Report focus",
        "question": "What is the main question or focus of this report?",
    },
    "invoice_client": {
        "label": "Bill to",
        "question": "Who should be invoiced? (Client or company name)",
    },
    "invoice_items": {
        "label": "Line items",
        "question": "What products or services are you billing for? Include quantities and prices.",
    },
    "quote_client": {
        "label": "Quote for",
        "question": "Who is this quote for? (Client or company name)",
    },
    "quote_items": {
        "label": "Quoted items",
        "question": "What are you quoting? Include items, quantities, and prices.",
    },
    "partnership_terms": {
        "label": "Partnership terms",
        "question": "What do you offer and what do you expect from the partner?",
    },
    "funding_ask": {
        "label": "Funding ask",
        "question": "How much are you raising and what will the funds be used for?",
    },
    "meeting_context": {
        "label": "Meeting context",
        "question": "What meeting was this? (Date, attendees, purpose)",
    },
    "press_angle": {
        "label": "News angle",
        "question": "What is the announcement or news hook?",
    },
    "document_purpose": {
        "label": "Document purpose",
        "question": "In one sentence, what should this document achieve for the reader?",
    },
}

# Keys only the owner can answer — never guess or web-search
USER_ONLY_KEYS = frozenset({
    "recipient_name",
    "recipient_company",
    "bank_name",
    "loan_amount",
    "loan_purpose",
    "contract_party",
    "contract_terms",
    "pricing_offer",
    "invoice_client",
    "invoice_items",
    "quote_client",
    "quote_items",
    "partnership_terms",
    "funding_ask",
    "timeline",
    "project_scope",
    "client_problem",
    "proposed_solution",
    "meeting_context",
    "press_angle",
    "report_period",
    "report_focus",
    "document_purpose",
})

RESEARCHABLE_KEYS = frozenset({
    "industry_context",
    "market_context",
    "regulatory_context",
})

# ── Per document type: requirements + premium design defaults ─────────────────

DOCUMENT_TYPE_SPECS: Dict[str, Dict[str, Any]] = {
    "business_proposal": {
        "label": "Business Proposal",
        "template": "executive",
        "use_logo": True,
        "hero_image": True,
        "hero_hint": "Client-facing professional environment related to the industry, natural light, shot on 35mm, no text",
        "design_notes": (
            "Premium client proposal: executive dark header, logo top-left, optional hero banner, "
            "clear section hierarchy (Problem → Solution → Scope → Timeline → Investment → Next Steps), "
            "tables for pricing, signature block. Lead with the client's problem, not your company bio."
        ),
        "required_keys": [
            "recipient_name", "recipient_company", "client_problem",
            "proposed_solution", "pricing_offer", "timeline",
        ],
        "research_keys": ["industry_context"],
        "sections": [
            "Executive Summary", "Understanding Your Challenge", "Proposed Solution",
            "Scope of Work", "Timeline", "Investment", "Why Us", "Next Steps",
        ],
    },
    "business_plan": {
        "label": "Business Plan",
        "template": "executive",
        "use_logo": True,
        "hero_image": True,
        "hero_hint": "Aspirational wide business scene matching the industry, golden hour, real photography, no text",
        "design_notes": (
            "Investor-grade business plan: executive template, strong exec summary standalone, "
            "market section with TAM/SAM if available, financial tables, team section, appendix-ready structure."
        ),
        "required_keys": ["document_purpose", "funding_ask"],
        "research_keys": ["market_context", "industry_context"],
        "sections": [
            "Executive Summary", "Company Overview", "Market Analysis",
            "Products & Services", "Marketing Strategy", "Operations", "Financial Projections", "Team",
        ],
    },
    "sow": {
        "label": "Scope of Work",
        "template": "professional",
        "use_logo": True,
        "hero_image": False,
        "design_notes": (
            "Formal SOW: numbered deliverables, acceptance criteria, responsibilities matrix, "
            "timeline table, payment milestones, change-order clause. Logo in header only."
        ),
        "required_keys": [
            "recipient_company", "project_scope", "deliverables_detail",
            "timeline", "pricing_offer",
        ],
        "research_keys": [],
        "sections": [
            "Project Overview", "Deliverables", "Timeline", "Responsibilities",
            "Pricing & Payment", "Assumptions", "Acceptance", "Signatures",
        ],
    },
    "contract": {
        "label": "Contract / Agreement",
        "template": "minimal",
        "use_logo": True,
        "hero_image": False,
        "design_notes": (
            "Legal-style agreement: minimal template, numbered clauses, plain language, "
            "parties block, payment terms, termination, signatures. Logo as letterhead only — no decorative imagery."
        ),
        "required_keys": ["contract_party", "contract_terms", "pricing_offer", "timeline"],
        "research_keys": ["regulatory_context"],
        "sections": [
            "Parties", "Services", "Payment Terms", "Timeline", "Confidentiality",
            "Intellectual Property", "Termination", "Governing Law", "Signatures",
        ],
    },
    "invoice": {
        "label": "Invoice",
        "template": "minimal",
        "use_logo": True,
        "hero_image": False,
        "design_notes": (
            "Clean invoice: minimal layout, logo top-left, bill-to block, line-item table with totals, "
            "payment instructions, due date. No hero image or marketing copy."
        ),
        "required_keys": ["invoice_client", "invoice_items"],
        "research_keys": [],
        "sections": ["Bill To", "Line Items", "Totals", "Payment Details", "Notes"],
    },
    "quote": {
        "label": "Quote / Estimate",
        "template": "professional",
        "use_logo": True,
        "hero_image": False,
        "design_notes": (
            "Sales quote: professional template, logo, quote validity date, itemised pricing table, "
            "terms and acceptance line. Optional small brand accent — no hero image."
        ),
        "required_keys": ["quote_client", "quote_items"],
        "research_keys": [],
        "sections": ["Quote For", "Items & Pricing", "Terms", "Validity", "Acceptance"],
    },
    "report": {
        "label": "Report",
        "template": "professional",
        "use_logo": True,
        "hero_image": False,
        "design_notes": (
            "Data-led report: summary first, findings with tables/charts in markdown tables, "
            "recommendations section, appendix for raw data. Logo in header."
        ),
        "required_keys": ["report_period", "report_focus"],
        "research_keys": ["industry_context"],
        "sections": ["Executive Summary", "Methodology", "Findings", "Analysis", "Recommendations"],
    },
    "executive_summary": {
        "label": "Executive Summary",
        "template": "executive",
        "use_logo": True,
        "hero_image": False,
        "design_notes": (
            "One-to-two page exec summary: punchy headings, key metrics callout, "
            "decision-ready recommendation. Executive template with logo."
        ),
        "required_keys": ["document_purpose", "recipient_company"],
        "research_keys": ["industry_context"],
        "sections": ["Overview", "Key Highlights", "Financial Snapshot", "Recommendation", "Next Steps"],
    },
    "loan_application": {
        "label": "Loan Application",
        "template": "professional",
        "use_logo": True,
        "letterhead": True,
        "hero_image": False,
        "design_notes": (
            "Formal loan application letter: professional letterhead with logo, "
            "clear purpose statement, amount requested, use of funds, repayment plan, "
            "business overview from CRM data, supporting financials. No decorative images."
        ),
        "required_keys": ["bank_name", "loan_amount", "loan_purpose"],
        "research_keys": [],
        "sections": [
            "Applicant Details", "Loan Request", "Purpose of Funds",
            "Business Overview", "Financial Summary", "Repayment Plan", "Supporting Documents",
        ],
    },
    "sales_letter": {
        "label": "Sales Letter",
        "template": "professional",
        "use_logo": True,
        "hero_image": False,
        "design_notes": (
            "Direct-response sales letter: strong opening hook, problem agitation, offer, proof, CTA. "
            "Logo in header, personal sign-off."
        ),
        "required_keys": ["recipient_name", "client_problem", "pricing_offer"],
        "research_keys": [],
        "sections": ["Opening", "Problem", "Solution", "Proof", "Offer", "Call to Action"],
    },
    "partnership_proposal": {
        "label": "Partnership Proposal",
        "template": "executive",
        "use_logo": True,
        "hero_image": True,
        "hero_hint": "Two businesses collaborating, modern office handshake scene, warm natural light, no text",
        "design_notes": (
            "Partnership deck-as-document: mutual value proposition, what each party brings, "
            "proposed structure, terms, next steps. Executive template with hero."
        ),
        "required_keys": ["recipient_company", "partnership_terms"],
        "research_keys": ["industry_context"],
        "sections": ["Introduction", "Opportunity", "What We Bring", "What We Seek", "Proposed Terms", "Next Steps"],
    },
    "investment_memo": {
        "label": "Investment Memo",
        "template": "executive",
        "use_logo": True,
        "hero_image": False,
        "design_notes": (
            "VC-style memo: thesis, market, product, traction, team, risks, ask. "
            "Dense but scannable — tables for metrics. Logo, no hero."
        ),
        "required_keys": ["funding_ask", "document_purpose"],
        "research_keys": ["market_context", "industry_context"],
        "sections": ["Thesis", "Market", "Product", "Traction", "Team", "Risks", "Ask"],
    },
    "onboarding_letter": {
        "label": "Client Onboarding Letter",
        "template": "professional",
        "use_logo": True,
        "hero_image": False,
        "design_notes": "Warm professional welcome letter: what to expect, contacts, timeline, next steps.",
        "required_keys": ["recipient_name", "recipient_company", "timeline"],
        "research_keys": [],
        "sections": ["Welcome", "What to Expect", "Your Contacts", "Timeline", "Next Steps"],
    },
    "loi": {
        "label": "Letter of Intent",
        "template": "minimal",
        "use_logo": True,
        "hero_image": False,
        "design_notes": "Formal LOI: parties, intent, key terms, exclusivity/expiry, signatures. Minimal legal tone.",
        "required_keys": ["contract_party", "contract_terms", "timeline"],
        "research_keys": [],
        "sections": ["Parties", "Intent", "Key Terms", "Timeline", "Expiry", "Signatures"],
    },
    "press_release": {
        "label": "Press Release",
        "template": "minimal",
        "use_logo": True,
        "hero_image": False,
        "design_notes": (
            "AP-style press release: headline, dateline, lead paragraph, quotes, boilerplate, contact. "
            "Logo small in header."
        ),
        "required_keys": ["press_angle"],
        "research_keys": [],
        "sections": ["Headline", "Dateline", "Lead", "Body", "Quote", "Boilerplate", "Contact"],
    },
    "meeting_minutes": {
        "label": "Meeting Minutes",
        "template": "minimal",
        "use_logo": False,
        "hero_image": False,
        "design_notes": (
            "Internal minutes: no logo, minimal template, attendees, agenda, decisions, action items table."
        ),
        "required_keys": ["meeting_context"],
        "research_keys": [],
        "sections": ["Attendees", "Agenda", "Discussion", "Decisions", "Action Items"],
    },
    "memo": {
        "label": "Internal Memo",
        "template": "minimal",
        "use_logo": False,
        "hero_image": False,
        "design_notes": "Internal memo: no logo, clean minimal layout, to/from/date/subject, concise body.",
        "required_keys": ["document_purpose"],
        "research_keys": [],
        "sections": ["Subject", "Background", "Discussion", "Recommendation", "Action Required"],
    },
    "company_profile": {
        "label": "Company Profile",
        "template": "executive",
        "use_logo": True,
        "hero_image": True,
        "hero_hint": "Professional wide-angle business environment matching the industry, natural light, real photography, no text",
        "design_notes": (
            "Client-ready company profile: executive template, logo letterhead, optional hero banner, "
            "Company Overview, Products & Services, Team, Traction/metrics from CRM, Contact. "
            "Pull business name, tagline, products, team, and revenue from CRM — do not re-ask."
        ),
        "required_keys": [],
        "research_keys": ["industry_context"],
        "sections": [
            "Company Overview", "Products & Services", "Team", "Traction & Metrics", "Contact",
        ],
    },
    "other": {
        "label": "Business Document",
        "template": "professional",
        "use_logo": True,
        "hero_image": False,
        "design_notes": "Professional business document with brand colors, logo, and clear section structure.",
        "required_keys": ["document_purpose"],
        "research_keys": ["industry_context"],
        "sections": [],
    },
}

# Extra key used by SOW
_REQUIREMENT_CATALOG["deliverables_detail"] = {
    "label": "Deliverables",
    "question": "List the specific deliverables (outputs) for this project.",
}

_DOC_TYPE_ALIASES: Dict[str, str] = {
    "proposal": "business_proposal",
    "client_proposal": "business_proposal",
    "pitch": "business_proposal",
    "plan": "business_plan",
    "agreement": "contract",
    "nda": "contract",
    "invoice": "invoice",
    "bill": "invoice",
    "estimate": "quote",
    "quotation": "quote",
    "loan": "loan_application",
    "bank_loan": "loan_application",
    "minutes": "meeting_minutes",
    "press": "press_release",
    "partnership": "partnership_proposal",
    "memo": "memo",
    "internal_memo": "memo",
    "sow": "sow",
    "scope_of_work": "sow",
    "company_profile": "company_profile",
    "business_profile": "company_profile",
    "corporate_profile": "company_profile",
    "company_overview": "company_profile",
    "business_overview": "company_profile",
}


def resolve_document_type(raw: str) -> str:
    key = _clean(raw).lower().replace(" ", "_").replace("-", "_")
    if key in DOCUMENT_TYPE_SPECS:
        return key
    return _DOC_TYPE_ALIASES.get(key, "other")


def infer_document_type_from_title(title: str) -> str:
    """Guess doc_type when the agent omits it — ensures logo/letterhead rules still apply."""
    t = _clean(title).lower()
    if not t:
        return "other"
    if "loan" in t or "credit facility" in t or "financing request" in t:
        return "loan_application"
    if "invoice" in t or "bill" in t:
        return "invoice"
    if "quote" in t or "quotation" in t or "estimate" in t:
        return "quote"
    if "proposal" in t:
        return "business_proposal"
    if "contract" in t or "agreement" in t:
        return "contract"
    if "memo" in t or "minutes" in t:
        return "memo" if "memo" in t else "meeting_minutes"
    if "report" in t:
        return "report"
    if "company profile" in t or "business profile" in t or "company overview" in t:
        return "company_profile"
    return "other"


def get_document_type_spec(doc_type: str) -> Dict[str, Any]:
    return DOCUMENT_TYPE_SPECS.get(resolve_document_type(doc_type), DOCUMENT_TYPE_SPECS["other"])


def researchable_keys_for_document(doc_type: str) -> frozenset:
    spec = get_document_type_spec(doc_type)
    return frozenset(spec.get("research_keys") or [])


def _field_satisfied(
    key: str,
    *,
    owner: Dict[str, Any],
    analytics: Dict[str, Any],
    products: List[Dict[str, Any]],
    user_context: Dict[str, Any],
) -> Tuple[bool, str]:
    if _substantive(_ctx_val(user_context, key), min_len=3):
        return True, "user"

    if key == "recipient_name":
        return False, "missing"
    if key == "recipient_company":
        return False, "missing"
    if key == "client_problem":
        if _substantive(owner.get("business_description_hint"), min_len=30):
            return True, "crm"
        return False, "missing"
    if key == "proposed_solution":
        if products:
            return True, "products"
        if _substantive(owner.get("products_services_hint")):
            return True, "crm"
        return False, "missing"
    if key == "pricing_offer":
        priced = [p for p in products if p.get("price") or p.get("discount_price")]
        if priced:
            return True, "products"
        return False, "missing"
    if key == "invoice_items":
        if products:
            return True, "products"
        return False, "missing"
    if key == "quote_items":
        if products:
            return True, "products"
        return False, "missing"
    if key in USER_ONLY_KEYS:
        return False, "missing"
    if key == "industry_context":
        return False, "missing"
    if key == "market_context":
        return False, "missing"
    if key == "regulatory_context":
        return False, "missing"
    return False, "missing"


def seed_document_context_from_crm(
    *,
    owner: Dict[str, Any],
    analytics: Dict[str, Any],
    products: List[Dict[str, Any]],
    user_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    ctx = dict(user_context or {})
    biz = _clean(owner.get("business_name"))
    if biz and not _ctx_val(ctx, "business_identity"):
        ctx["business_identity"] = biz
    owner_name = _clean(owner.get("owner_name"))
    if owner_name and not _ctx_val(ctx, "signature_name"):
        ctx.setdefault("signature_name", owner_name)
    phone = _clean(
        owner.get("phone_number")
        or owner.get("whatsapp_number")
        or owner.get("phone")
        or owner.get("business_phone")
    )
    email = _clean(owner.get("email") or owner.get("business_email"))
    contact = " · ".join(x for x in (email, phone) if x)
    if contact and not _ctx_val(ctx, "signature_contact"):
        ctx.setdefault("signature_contact", contact)

    doc_style = owner.get("document_style") if isinstance(owner.get("document_style"), dict) else {}
    if doc_style.get("signature_name") and not _ctx_val(ctx, "signature_name"):
        ctx.setdefault("signature_name", _clean(doc_style.get("signature_name")))
    if doc_style.get("signature_contact") and not _ctx_val(ctx, "signature_contact"):
        ctx.setdefault("signature_contact", _clean(doc_style.get("signature_contact")))

    currency = _clean(owner.get("currency"))
    if currency:
        ctx.setdefault("currency", currency)

    country = _clean(owner.get("country") or owner.get("business_location"))
    if country:
        ctx.setdefault("business_country", country)

    tagline = _clean(owner.get("tagline") or doc_style.get("header_text"))
    if tagline and not _ctx_val(ctx, "document_purpose"):
        ctx.setdefault("value_proposition", tagline[:220])

    website = _clean(owner.get("website_url"))
    if website:
        ctx.setdefault("website_url", website)

    desc = _clean(owner.get("business_description") or owner.get("business_description_hint"))
    if desc and not _ctx_val(ctx, "document_purpose"):
        ctx.setdefault("document_purpose", desc[:220])

    pricing_info = _clean(owner.get("pricing_info"))
    if pricing_info and not _ctx_val(ctx, "pricing_offer"):
        ctx.setdefault("pricing_offer", pricing_info[:220])

    if products and not _ctx_val(ctx, "pricing_offer"):
        lines = []
        cur = currency or "KES"
        for p in products[:5]:
            name = _clean(p.get("name"))
            price = p.get("discount_price") or p.get("price")
            if name:
                lines.append(f"{name}: {cur} {price}" if price else name)
        if lines:
            ctx.setdefault("pricing_offer", "; ".join(lines))
    if int(analytics.get("customers_count") or 0) >= 1 and not _ctx_val(ctx, "traction"):
        ctx.setdefault("traction", f"{analytics['customers_count']} customers on file")
    return ctx


async def enrich_doc_style(
    db,
    business_id: str,
    doc_style: Optional[Dict[str, Any]],
    doc_type: str,
    owner: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Merge brand kit + document type rules into export style."""
    from saved_designs import get_brand_settings, get_primary_logo_url

    owner = owner or {}
    spec = get_document_type_spec(doc_type)
    style = dict(doc_style or {})
    brand = await get_brand_settings(db, business_id)
    if not style.get("primary_color") and brand.get("brand_primary_color"):
        style["primary_color"] = brand["brand_primary_color"]
    if not style.get("font_style") and brand.get("brand_font"):
        style["font_style"] = brand["brand_font"]

    if spec.get("letterhead"):
        style["letterhead"] = True

    contact_bits = [
        _clean(owner.get("email")),
        _clean(owner.get("phone_number") or owner.get("whatsapp_number")),
    ]
    website = _clean(owner.get("website_url"))
    if website:
        contact_bits.append(re.sub(r"^https?://(www\.)?", "", website, flags=re.I).rstrip("/"))
    if not any(contact_bits):
        contact_bits = [_clean(style.get("signature_contact"))]
    style.setdefault("header_contact", " · ".join(x for x in contact_bits if x))

    style = sanitize_document_style(
        style,
        website_url=website,
        email=_clean(owner.get("email")),
    )
    if spec.get("use_logo"):
        logo = await get_primary_logo_url(db, business_id)
        if not logo:
            logo = _clean(owner.get("default_logo_url"))
        if logo:
            style["logo_url"] = logo
    else:
        style.pop("logo_url", None)
        style.pop("default_logo_url", None)
    return style, spec


def build_export_config(doc_type: str, spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    spec = spec or get_document_type_spec(doc_type)
    return {
        "doc_type": resolve_document_type(doc_type),
        "doc_type_label": spec.get("label", "Document"),
        "template": spec.get("template", "professional"),
        "use_logo": bool(spec.get("use_logo")),
        "hero_image": bool(spec.get("hero_image")),
        "hero_hint": spec.get("hero_hint", ""),
        "design_notes": spec.get("design_notes", ""),
        "recommended_sections": spec.get("sections") or [],
    }


def assess_document_requirements(
    *,
    doc_type: str,
    owner: Optional[Dict[str, Any]] = None,
    analytics: Optional[Dict[str, Any]] = None,
    products: Optional[List[Dict[str, Any]]] = None,
    user_context: Optional[Dict[str, Any]] = None,
    research_keys: Optional[set] = None,
) -> Dict[str, Any]:
    owner = owner or {}
    analytics = analytics or {}
    products = products or []
    user_context = user_context or {}
    research_keys = research_keys or set()
    resolved = resolve_document_type(doc_type)
    spec = get_document_type_spec(resolved)
    required_keys = list(spec.get("required_keys") or [])
    purpose_researchable = researchable_keys_for_document(resolved)

    found: Dict[str, Any] = {}
    missing: List[Dict[str, str]] = []

    for key in required_keys:
        ok, source = _field_satisfied(
            key,
            owner=owner,
            analytics=analytics,
            products=products,
            user_context=user_context,
        )
        meta = _REQUIREMENT_CATALOG.get(key, {})
        if ok:
            val = _ctx_val(user_context, key)
            found[key] = {"source": "web" if key in research_keys else source, "preview": (val or source)[:120]}
        elif key in purpose_researchable or key in research_keys:
            continue
        else:
            missing.append({
                "key": key,
                "label": meta.get("label", key.replace("_", " ").title()),
                "question": meta.get("question", f"Please provide: {key.replace('_', ' ')}."),
            })

    export_cfg = build_export_config(resolved, spec)
    return {
        "ready": len(missing) == 0,
        "doc_type": resolved,
        "doc_type_label": spec.get("label"),
        "found": found,
        "missing": missing,
        "missing_count": len(missing),
        "export_config": export_cfg,
        "design_notes": spec.get("design_notes", ""),
        "recommended_sections": spec.get("sections") or [],
        "logo_policy": "include_logo" if spec.get("use_logo") else "no_logo",
        "hero_image_policy": "allow_hero" if spec.get("hero_image") else "no_hero",
    }


def resolve_business_country(owner: Dict[str, Any]) -> str:
    """Normalised country key from CRM owner profile (country setting or currency)."""
    country = _clean(owner.get("country")).lower()
    currency = _clean(owner.get("currency")).lower()
    for raw in (country, currency):
        if not raw:
            continue
        key = _COUNTRY_ALIASES.get(raw.replace(".", "").strip())
        if key:
            return key
        for alias, resolved in _COUNTRY_ALIASES.items():
            if alias in raw or raw in alias:
                return resolved
    return ""


def bank_names_for_country(country_key: str, *, max_items: int = 5) -> List[str]:
    """Top banks for a country — suggestions only; owner can always pick Other."""
    names = _BANKS_BY_COUNTRY.get(country_key, [])
    return names[:max_items]


def field_options_for_key(
    key: str,
    *,
    owner: Dict[str, Any],
    currency: str = "",
) -> List[Dict[str, str]]:
    """Selectable chip options for checklist fields (country-aware where possible)."""
    cur = _clean(currency or owner.get("currency")).upper()
    country_key = resolve_business_country(owner)

    if key == "bank_name":
        banks = bank_names_for_country(country_key)
        opts: List[Dict[str, str]] = []
        for i, name in enumerate(banks):
            opts.append(_option(f"bank_{i}", name, name))
        if country_key and banks:
            country_label = country_key.replace("_", " ").title()
            opts.append(_option(
                "bank_other",
                f"Other bank (not listed — type name)",
                "",
            ))
        else:
            opts.extend([
                _option("lender_commercial", "Commercial / retail bank", "Commercial bank"),
                _option("lender_mfi", "Microfinance institution", "Microfinance institution"),
                _option("lender_dfi", "Development finance institution", "Development finance institution"),
                _option("bank_other", "Other — type the bank or lender name", ""),
            ])
        return opts

    if key == "loan_amount" and cur:
        if cur == "KES":
            presets = ["KES 500,000", "KES 1,000,000", "KES 2,500,000", "KES 5,000,000"]
        elif cur == "NGN":
            presets = ["NGN 5,000,000", "NGN 10,000,000", "NGN 25,000,000", "NGN 50,000,000"]
        elif cur == "USD":
            presets = ["USD 25,000", "USD 50,000", "USD 100,000", "USD 250,000"]
        elif cur == "GBP":
            presets = ["GBP 25,000", "GBP 50,000", "GBP 100,000", "GBP 250,000"]
        else:
            presets = [f"{cur} 100,000", f"{cur} 500,000", f"{cur} 1,000,000", f"{cur} 5,000,000"]
        opts = [_option(f"amt_{i}", p, p) for i, p in enumerate(presets)]
        opts.append(_option("amt_other", "Other amount — I'll specify", ""))
        return opts

    return []


def _format_chip_options(options: List[Dict[str, str]]) -> str:
    """Lettered A/B/C lines for chat tap-to-send buttons."""
    lines: List[str] = []
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for i, opt in enumerate(options):
        if i >= len(letters):
            break
        label = _clean(opt.get("label"))
        if not label:
            continue
        lines.append(f"{letters[i]}. {label}")
    return "\n".join(lines)


def build_document_checklist(
    assessment: Dict[str, Any],
    *,
    owner: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    owner = owner or {}
    country_key = resolve_business_country(owner)
    items: List[Dict[str, Any]] = []
    for row in assessment.get("missing") or []:
        key = row.get("key", "")
        options = field_options_for_key(key, owner=owner)
        items.append({
            "key": key,
            "label": row.get("label", key),
            "question": row.get("question", ""),
            "required": True,
            "input_type": "text",
            "options": options,
            "country_hint": country_key.replace("_", " ").title() if country_key else "",
        })
    return items


def build_document_chat_reply(
    assessment: Dict[str, Any],
    *,
    owner: Optional[Dict[str, Any]] = None,
) -> str:
    missing = assessment.get("missing") or []
    if not missing:
        return ""
    first = missing[0]
    label = first.get("label", "detail")
    question = first.get("question", "")
    remaining = len(missing) - 1
    tail = f" ({remaining} more after this)" if remaining > 0 else ""
    spec = get_document_type_spec(str(assessment.get("doc_type") or "other"))
    design = (spec.get("design_notes") or "")[:200]

    owner = owner or {}
    country_key = resolve_business_country(owner)
    options = field_options_for_key(first.get("key", ""), owner=owner)
    country_note = ""
    if first.get("key") == "bank_name" and country_key:
        country_note = f"\n\n_Suggestions for **{country_key.replace('_', ' ').title()}** based on your business profile — pick one or type another:_"

    chip_block = ""
    if options:
        chip_block = country_note + "\n\n" + _format_chip_options(options)

    return (
        f"Before I draft your **{spec.get('label', 'document')}**, I need one detail{tail}:\n\n"
        f"**{label}** — {question}{chip_block}\n\n"
        f"_Design approach: {design}_"
    )


def build_document_agent_note(assessment: Dict[str, Any], researched: Dict[str, str]) -> str:
    if assessment.get("ready"):
        cfg = assessment.get("export_config") or {}
        logo = "include brand logo in header" if cfg.get("use_logo") else "do NOT include a logo"
        hero = "add a hero cover image via image_prompt" if cfg.get("hero_image") else "no hero image"
        return (
            f"Requirements complete. Draft the full document using sections: "
            f"{', '.join(assessment.get('recommended_sections') or [])}. "
            f"Export with template={cfg.get('template', 'professional')}, {logo}, {hero}. "
            f"Premium design: {assessment.get('design_notes', '')}. "
            f"Website policy: { (assessment.get('website_policy') or {}).get('rule', '') }"
        )
    missing = assessment.get("missing") or []
    if not missing:
        return "Gather missing document details from the owner."
    m = missing[0]
    return (
        f"Ask ONLY for '{m.get('label')}': {m.get('question')} "
        "Present each option on its own line (A. … then B. … on separate lines) so tap chips render."
    )


def build_research_queries(doc_type: str, topic: str, owner: Dict[str, Any]) -> Dict[str, str]:
    biz = _clean(owner.get("business_name")) or "business"
    industry = _clean(owner.get("business_type") or owner.get("industry")) or "industry"
    resolved = resolve_document_type(doc_type)
    queries: Dict[str, str] = {}
    keys = researchable_keys_for_document(resolved)
    if "industry_context" in keys:
        queries["industry_context"] = f"{industry} industry trends challenges {topic} 2025 2026"
    if "market_context" in keys:
        queries["market_context"] = f"{industry} market size TAM growth statistics {topic}"
    if "regulatory_context" in keys:
        queries["regulatory_context"] = f"{industry} contract legal requirements standard clauses"
    return queries


async def auto_research_document_context(
    *,
    doc_type: str,
    topic: str,
    owner: Dict[str, Any],
    user_context: Dict[str, str],
    search_fn,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Web-search public context for document drafting."""
    out: Dict[str, str] = {}
    sources: Dict[str, str] = {}
    queries = build_research_queries(doc_type, topic, owner)
    for key, query in queries.items():
        if _ctx_val(user_context, key):
            continue
        try:
            data = await search_fn(query)
            answer = _clean((data or {}).get("answer"))
            if not answer and (data or {}).get("results"):
                snippets = [
                    _clean(r.get("snippet"))
                    for r in (data.get("results") or [])[:3]
                    if isinstance(r, dict)
                ]
                answer = " ".join(s for s in snippets if s)[:600]
            if _substantive(answer, min_len=40):
                out[key] = answer[:800]
                sources[key] = "web"
        except Exception:
            continue
    return out, sources


__all__ = [
    "CHECKLIST_VERSION",
    "DOCUMENT_TYPE_SPECS",
    "assess_document_requirements",
    "auto_research_document_context",
    "bank_suggestions_for_country",
    "build_document_agent_note",
    "build_document_chat_reply",
    "build_document_checklist",
    "build_export_config",
    "enrich_doc_style",
    "get_document_type_spec",
    "parse_requirements_submission",
    "infer_document_type_from_title",
    "researchable_keys_for_document",
    "resolve_business_country",
    "resolve_document_type",
    "seed_document_context_from_crm",
    "sanitize_document_text",
    "sanitize_document_style",
    "build_website_policy",
]
