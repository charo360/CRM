"""
IntentAnalyzer — One fast AI call that understands the message in full business context.

Uses threaded-context architecture:
  Layer 1: THE current message (what to reply to)
  Layer 2: Immediate thread (last 2-3 messages within 30 min)
  Layer 3: Relationship signal (follow-up / new conversation / continuation)
  Layer 4: Older context summarized in 1-2 lines
"""
import json
import re
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Intents that map to specific agents
SALES_INTENTS = {"PRODUCT_INQUIRY", "PRICE_INQUIRY", "CATALOG_REQUEST", "STOCK_CHECK", "NEGOTIATION", "BULK_ORDER"}
ORDER_INTENTS = {"ORDER_STATUS", "DELIVERY_INQUIRY", "TRACKING", "ORDER_CANCEL", "ORDER_MODIFY"}
PAYMENT_INTENTS = {"PAYMENT_CONFIRM", "PAYMENT_METHOD", "PAYMENT_ISSUE", "REFUND_REQUEST"}
COMPLAINT_INTENTS = {"COMPLAINT", "NEGATIVE_FEEDBACK", "DAMAGED_ITEM", "WRONG_ITEM", "ESCALATION"}
CHAT_INTENTS = {"GENERAL_CHAT", "PERSONAL_CHAT", "GREETING", "SMALL_TALK", "OFF_TOPIC"}
BOOKING_INTENTS = {"BOOKING_REQUEST", "AVAILABILITY_CHECK", "BOOKING_STATUS", "BOOKING_CANCEL", "RESCHEDULE", "RESET_CONVERSATION"}

# Intents that must always escalate — AI should never handle alone
ALWAYS_ESCALATE_INTENTS = {"LEGAL_THREAT", "FRAUD_CLAIM", "ESCALATION"}

ESCALATE_THRESHOLD = 0.65   # needs_escalation: True below this confidence
UNKNOWN_THRESHOLD = 0.50    # classify as UNKNOWN below this (non-chat intents)

# Time thresholds for conversation threading
THREAD_GAP_MINUTES = 30       # messages within 30 min = same thread
NEW_CONVERSATION_HOURS = 24   # gap > 24h = brand new conversation


def build_threaded_context(history: list) -> Dict[str, Any]:
    """
    Split flat history into threaded layers with a relationship signal.
    
    Returns:
        {
            "immediate_thread": [last 2-3 msgs within 30 min of latest],
            "older_context": [remaining older messages],
            "relationship": "follow_up" | "new_conversation" | "continuation",
            "gap_description": "Customer is replying 2 minutes after last message" | etc,
            "hours_since_last": float or None,
        }
    """
    if not history:
        return {
            "immediate_thread": [],
            "older_context": [],
            "relationship": "new_conversation",
            "gap_description": "First message — no prior conversation.",
            "hours_since_last": None,
        }

    now = datetime.now(timezone.utc)
    
    # Parse timestamps from history (most recent is last)
    last_msg = history[-1]
    last_ts = _parse_ts(last_msg.get("created_at"))
    
    if not last_ts:
        # No timestamp — treat all recent as immediate thread
        immediate = history[-3:] if len(history) >= 3 else history
        older = history[:-len(immediate)] if len(history) > len(immediate) else []
        return {
            "immediate_thread": immediate,
            "older_context": older,
            "relationship": "continuation",
            "gap_description": "Ongoing conversation (timestamps unavailable).",
            "hours_since_last": None,
        }

    # Calculate gap between now and last message
    gap = now - last_ts
    hours_since = gap.total_seconds() / 3600.0

    # Build immediate thread: walk backwards, include messages within THREAD_GAP_MINUTES
    immediate = []
    older = []
    thread_cutoff = last_ts - timedelta(minutes=THREAD_GAP_MINUTES)
    
    for m in reversed(history):
        m_ts = _parse_ts(m.get("created_at"))
        if m_ts and m_ts >= thread_cutoff and len(immediate) < 4:
            immediate.insert(0, m)
        else:
            older.insert(0, m)

    # If no timestamps parsed, just take last 3
    if not immediate:
        immediate = history[-3:]
        older = history[:-3] if len(history) > 3 else []

    # Determine relationship
    if hours_since >= NEW_CONVERSATION_HOURS:
        relationship = "new_conversation"
        if hours_since >= 48:
            gap_desc = f"Customer is messaging again after {int(hours_since / 24)} days of silence. Treat as a FRESH conversation."
        else:
            gap_desc = f"Customer is messaging again after {int(hours_since)} hours. Likely a new topic."
    elif hours_since <= 0.5:  # within 30 min
        relationship = "follow_up"
        minutes = max(1, int(hours_since * 60))
        gap_desc = f"Customer replied {minutes} minute(s) after the last message. This is a DIRECT FOLLOW-UP to the conversation above."
    else:
        relationship = "continuation"
        gap_desc = f"Customer is continuing a conversation from {int(hours_since)} hours ago."

    return {
        "immediate_thread": immediate,
        "older_context": older,
        "relationship": relationship,
        "gap_description": gap_desc,
        "hours_since_last": round(hours_since, 2),
    }


def _parse_ts(ts_val) -> datetime | None:
    """Parse a timestamp value into a timezone-aware datetime."""
    if ts_val is None:
        return None
    if isinstance(ts_val, datetime):
        if ts_val.tzinfo is None:
            return ts_val.replace(tzinfo=timezone.utc)
        return ts_val
    if isinstance(ts_val, str):
        try:
            dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None
    return None


def format_threaded_history(threaded: Dict[str, Any]) -> str:
    """Format threaded context into a structured prompt section."""
    parts = []
    
    # Older context — summarized
    older = threaded.get("older_context", [])
    if older:
        older_lines = []
        for m in older[-6:]:  # max 6 older messages
            role = "Customer" if m.get("direction") == "incoming" else "Business"
            content = (m.get("content", "") or "")[:120]
            older_lines.append(f"  {role}: {content}")
        parts.append("Earlier in the conversation:\n" + "\n".join(older_lines))
    
    # Immediate thread — full detail
    immediate = threaded.get("immediate_thread", [])
    if immediate:
        thread_lines = []
        for m in immediate:
            role = "Customer" if m.get("direction") == "incoming" else "Business"
            content = m.get("content", "") or ""
            thread_lines.append(f"  {role}: {content}")
        parts.append("Recent thread (most relevant):\n" + "\n".join(thread_lines))
    
    # Relationship signal
    gap_desc = threaded.get("gap_description", "")
    if gap_desc:
        parts.append(f"⚡ CONTEXT: {gap_desc}")
    
    return "\n\n".join(parts) if parts else "(no prior history)"


_AVAILABILITY_EXACT_KEYWORDS = {
    "availability", "available", "available?", "availability?",
    "check availability", "what's available", "whats available",
    "what is available", "available dates", "check available",
    "show availability", "see availability",
}

_PAYMENT_CONFIRM_KEYWORDS = {
    "i've paid", "i have paid", "i paid", "payment done", "payment made",
    "sent the money", "money sent", "mpesa sent", "i sent", "transferred",
    "i transferred", "done paying", "check your mpesa", "paid",
    "i've made the payment", "payment complete", "transaction done",
    # Swahili
    "nimelipa", "nimetuma pesa", "nimetuma", "pesa imekwenda", "malipo yamefanyika",
    "angalia mpesa", "nimesend", "lipa imefanyika",
    # French
    "j'ai payé", "paiement effectué", "j'ai envoyé l'argent", "virement fait",
    "transaction faite", "j'ai fait le virement",
    # Spanish
    "ya pagué", "hice el pago", "transferí", "pago realizado", "te mandé el dinero",
    # Portuguese
    "já paguei", "fiz o pagamento", "transferi", "enviei o dinheiro",
    # Hausa
    "na biya", "na aika kudi", "biya ya yi",
    # Pidgin
    "i don pay", "i don send the money", "payment don go", "money don enter",
    # Hindi/Hinglish
    "pay kar diya", "paise bhej diye", "payment ho gaya", "transfer kar diya",
}

_CATALOG_EXACT_KEYWORDS = {
    "catalog", "catalogue", "menu", "products", "what do you sell",
    "show me products", "what do you have", "show me what you have",
    "show catalog", "show catalogue", "show menu", "price list",
    "what are your products", "what do you offer", "your products",
    "send catalog", "send catalogue", "send menu", "list products",
    "i want to buy", "i want to order", "order something", "buy something",
    # Swahili / Sheng
    "bidhaa", "orodha", "bei", "nini mnacho", "mnauza nini",
    "unacho nini", "unauzaje", "unauza nini", "nataka kununua",
    "nataka kubuy", "nataka buy", "buy kitu", "nataka kubuy kitu",
    "nipe orodha", "niambie bei", "mnauza nini", "una nini",
    # French
    "catalogue", "produits", "prix", "qu'est-ce que vous vendez",
    "montrez-moi vos produits", "liste des produits", "je veux acheter",
    "je veux commander", "qu'avez-vous", "vos produits",
    # Spanish
    "catálogo", "productos", "qué vendes", "qué tienen", "lista de precios",
    "quiero comprar", "quiero pedir", "qué tienes", "muéstrame",
    # Portuguese
    "catálogo", "produtos", "o que você vende", "lista de preços",
    "quero comprar", "quero pedir", "o que tem",
    # Hausa
    "kaya", "abin da kuke da shi", "farashin kaya", "nuna mini kayan",
    # Yoruba
    "ohun ti e ta", "elo ni", "fi han mi",
    # Igbo
    "ihe i na-ere", "ego ole", "gosi m",
    # Pidgin
    "wetin you dey sell", "show me wetin you get", "wetin dey",
    "price list abeg", "send me your tings",
    # Hindi/Hinglish
    "kya hai", "price batao", "products dikhao", "kya milega", "list bhejo",
}

_BOOKING_EXACT_KEYWORDS = {
    "book", "booking", "i want to book", "book me", "make a booking",
    "make appointment", "i need an appointment", "schedule",
    "i want an appointment", "book appointment", "reserve",
    # Swahili
    "nipangie", "nataka kupanga", "nataka kuhifadhi", "panga appointment",
    "hifadhi nafasi", "nataka nafasi", "panga nafasi",
    # French
    "réserver", "prendre rendez-vous", "je veux réserver", "une réservation",
    "fixer un rendez-vous", "prendre un créneau",
    # Spanish
    "reservar", "quiero reservar", "hacer una cita", "necesito una cita",
    "una reserva", "agendar", "hacer una reservación",
    # Portuguese
    "reservar", "quero reservar", "fazer uma reserva", "marcar consulta",
    "agendar", "uma consulta",
    # Hausa
    "ina son alƙawari", "yi alƙawari", "ɗauki lokaci",
    # Pidgin
    "i wan book", "book me abeg", "make appointment abeg",
    # Hindi/Hinglish
    "booking chahiye", "appointment chahiye", "book karna hai", "reserve karo",
}

_PRICE_PATTERNS = [
    r'\bhow\s+much\b',
    r'\bwhat.*price\b',
    r'\bwhat.*cost\b',
    r'\bhow\s+much\s+(is|are|does|do|for)\b',
    r'\bbei\s+(ya|gani)\b',  # Swahili
]

_RESET_EXACT_KEYWORDS = {
    "start over", "reset", "begin again", "restart", "start afresh", "afresh",
    "clear", "forget it", "nevermind", "never mind", "go back", "back",
    "tuanze upya", "anza upya", "safisha",  # Swahili
    "recommencer", "annuler", "retour",    # French
}

def _detect_language(message: str) -> str:
    """
    Fast keyword-based language detection for deterministic overrides.
    Returns a language name string. Falls back to 'English' if unknown.
    Covers 15+ languages including African, Asian, and European variants.
    """
    msg = message.lower()

    # Arabic script — check character range first (fast)
    if any('\u0600' <= c <= '\u06ff' for c in message):
        return "Arabic"
    # Amharic/Ethiopic script
    if any('\u1200' <= c <= '\u137f' for c in message):
        return "Amharic"
    # Hindi/Devanagari script
    if any('\u0900' <= c <= '\u097f' for c in message):
        return "Hindi"

    # Sheng — check BEFORE Swahili because they share words like "niaje", "mambo"
    # Sheng is identified by slang markers absent from standard Swahili
    _sheng_markers = {"manze", "buda", "dame", "si unajua", "fiti", "nilikuwa naomba", "maze",
                      "gani hii", "mtu wangu", "naomba hiyo", "uko poa", "niko poa", "wacha", "kweli kabisa"}
    if any(kw in msg for kw in _sheng_markers):
        return "Sheng"

    # Swahili indicators (standard)
    _sw_words = {"habari", "mambo", "niaje", "sasa", "shikamoo", "asante", "pole", "karibu",
                 "samahani", "bidhaa", "nataka", "mpesa", "nzuri", "poa", "nipe", "tuma", "lipa",
                 "nunua", "kununua", "niambie", "orodha", "unacho", "mnauza", "nakuomba",
                 "naomba", "sawa", "bei", "gani", "chakula", "huduma", "agiza", "amri"}
    _sw_substrings = ("nataka", "bidhaa", "mpesa", "habari", "karibu", "asante", "niambie", "bei gani")
    if any(w in msg.split() for w in _sw_words) or any(kw in msg for kw in _sw_substrings):
        return "Swahili"

    # Hausa (West Africa — Nigeria, Niger, Ghana)
    _ha = {"sannu", "ina kwana", "yaya", "kaya", "sayi", "tsada", "nawa", "farashin",
           "ina son", "abin da kuke da shi", "nemo", "littafin farashi", "don allah"}
    if any(w in msg.split() for w in _ha) or any(kw in msg for kw in ("ina kwana", "don allah", "ina son")):
        return "Hausa"

    # Yoruba (Nigeria)
    _yo = {"ẹ jọ", "e jo", "bawo", "jọwọ", "nibo", "elo", "daadaa", "ẹ káàbọ̀", "e kaabo",
           "mo fẹ", "mo fe", "ki lo ni", "kini owo re", "wa fun mi"}
    if any(kw in msg for kw in _yo):
        return "Yoruba"

    # Igbo (Nigeria)
    _ig = {"biko", "kedu", "olee", "ego ole", "achọrọ m", "achoro m", "ọ dị mma",
           "o di mma", "gwa m", "ihe ị na-ere"}
    if any(kw in msg for kw in _ig):
        return "Igbo"

    # Somali
    _so = {"salaan", "mahadsanid", "waa maxay", "intee", "fadlan", "rabanahay", "waxaan rabo",
           "qiimaha", "liiska", "buug", "ballan"}
    if any(w in msg.split() for w in _so) or any(kw in msg for kw in ("waxaan rabo", "qiimaha", "mahadsanid")):
        return "Somali"

    # Luganda (Uganda)
    _lg = {"gyebale", "webale", "ssebo", "nnyabo", "nsaba", "nyiga", "ffene", "wasuze otya",
           "ndi", "nkwagala", "kiki", "wadde"}
    if any(w in msg.split() for w in _lg):
        return "Luganda"

    # Pidgin English (West/Central Africa — Nigeria, Ghana, Cameroon)
    _pid = {"abeg", "oya", "wetin", "how far", "no wahala", "i dey", "na wetin",
            "make i", "shey", "e dey", "na im", "dey find", "how e dey", "dey sell"}
    if any(kw in msg for kw in _pid):
        return "Pidgin"

    # French indicators
    _fr_words = {"bonjour", "bonsoir", "salut", "merci", "produits", "catalogue",
                 "combien", "réserver", "disponible", "annuler", "je veux", "je cherche",
                 "s'il vous plaît", "qu'est-ce", "pouvez-vous", "quel est"}
    _fr_sub = ("je veux", "je cherche", "combien", "s'il vous", "bonjour", "bonsoir")
    if any(w in msg.split() for w in _fr_words) or any(kw in msg for kw in _fr_sub):
        return "French"

    # Spanish indicators
    _es_words = {"hola", "buenos", "buenas", "gracias", "por favor", "cuánto", "cuanto",
                 "quiero", "necesito", "tienes", "tienen", "precio", "catálogo", "reservar",
                 "disponible", "cuándo", "cuando", "puedo", "puedes"}
    _es_sub = ("hola", "buenos", "quiero", "por favor", "cuánto", "necesito")
    if any(w in msg.split() for w in _es_words) or any(kw in msg for kw in _es_sub):
        return "Spanish"

    # Portuguese indicators
    _pt_words = {"olá", "ola", "bom dia", "boa tarde", "obrigado", "obrigada", "quanto",
                 "produto", "preço", "reservar", "disponível", "quero", "preciso",
                 "quanto custa", "tem", "qual"}
    _pt_sub = ("bom dia", "boa tarde", "quanto custa", "obrigado", "preciso")
    if any(w in msg.split() for w in _pt_words) or any(kw in msg for kw in _pt_sub):
        return "Portuguese"

    # Hinglish (Hindi–English code-switching, Latin script)
    _hi_latin = {"kya", "kitna", "hai", "nahi", "karo", "chahiye", "milega", "dedo",
                 "bata", "price batao", "kab", "kaise", "kyun", "thik hai", "sahi hai"}
    if any(w in msg.split() for w in _hi_latin) or any(kw in msg for kw in ("price batao", "kitna hai", "kya hai", "chahiye")):
        return "Hinglish"

    return "English"


def _deterministic_intent_override(message: str) -> dict | None:
    """
    Fast rules-only pre-check before the LLM is called.
    Returns a result dict if the intent is unambiguous, else None.
    This is the primary stability mechanism — these keywords NEVER touch the LLM.
    Language is auto-detected from the message so non-English speakers get replies in their language.
    """
    msg = message.strip().lower()
    lang = _detect_language(message)

    # Catalog/product request → always CATALOG_REQUEST
    if msg in _CATALOG_EXACT_KEYWORDS or any(msg.startswith(kw) for kw in _CATALOG_EXACT_KEYWORDS if len(kw) > 3):
        return {
            "intent": "CATALOG_REQUEST",
            "sentiment": "neutral",
            "language": lang,
            "entities": {"products": [], "amounts": [], "dates": [], "other": []},
            "conversation_state": "ongoing",
            "confidence": 1.0,
            "needs_escalation": False,
            "escalation_reason": None,
            "keywords": ["catalog"],
            "contact_signal": {"type": "customer", "confidence": 0.95, "reason": "business keyword detected"},
        }

    # Booking request → always BOOKING_REQUEST
    if msg in _BOOKING_EXACT_KEYWORDS or any(msg.startswith(kw) for kw in _BOOKING_EXACT_KEYWORDS if len(kw) > 3):
        return {
            "intent": "BOOKING_REQUEST",
            "sentiment": "neutral",
            "language": lang,
            "entities": {"products": [], "amounts": [], "dates": [], "other": []},
            "conversation_state": "ongoing",
            "confidence": 1.0,
            "needs_escalation": False,
            "escalation_reason": None,
            "keywords": ["booking"],
            "contact_signal": {"type": "customer", "confidence": 0.95, "reason": "business keyword detected"},
        }

    # Price inquiry → always PRICE_INQUIRY (routes to sales)
    for pattern in _PRICE_PATTERNS:
        if re.search(pattern, msg):
            return {
                "intent": "PRICE_INQUIRY",
                "sentiment": "neutral",
                "language": lang,
                "entities": {"products": [], "amounts": [], "dates": [], "other": []},
                "conversation_state": "ongoing",
                "confidence": 1.0,
                "needs_escalation": False,
                "escalation_reason": None,
                "keywords": ["price"],
                "contact_signal": {"type": "customer", "confidence": 0.95, "reason": "business keyword detected"},
            }

    # Availability keywords → always AVAILABILITY_CHECK, never misrouted to payment
    if msg in _AVAILABILITY_EXACT_KEYWORDS or msg.startswith("availability") or msg.startswith("check availability"):
        return {
            "intent": "AVAILABILITY_CHECK",
            "sentiment": "neutral",
            "language": lang,
            "entities": {"products": [], "amounts": [], "dates": [], "other": []},
            "conversation_state": "ongoing",
            "confidence": 1.0,
            "needs_escalation": False,
            "escalation_reason": None,
            "keywords": ["availability"],
            "contact_signal": {"type": "customer", "confidence": 0.95, "reason": "business keyword detected"},
        }
    # Only classify as PAYMENT_CONFIRM if the message actually looks like one
    # Prevent short ambiguous words from being misrouted to PaymentAgent
    _has_payment_kw = any(msg == kw or msg.startswith(kw) for kw in _PAYMENT_CONFIRM_KEYWORDS)
    _looks_like_payment = _has_payment_kw or any(
        w in msg for w in ["paid", "mpesa", "transferred", "sent money", "payment", "transaction"]
    )
    # Reset/Start over request
    if msg in _RESET_EXACT_KEYWORDS or any(msg.startswith(kw) for kw in _RESET_EXACT_KEYWORDS if len(kw) > 4):
        return {
            "intent": "RESET_CONVERSATION",
            "sentiment": "neutral",
            "language": lang,
            "entities": {"products": [], "amounts": [], "dates": [], "other": []},
            "conversation_state": "new",
            "confidence": 1.0,
            "needs_escalation": False,
            "escalation_reason": None,
            "keywords": ["reset"],
            "contact_signal": {"type": "customer", "confidence": 0.8, "reason": "reset keyword detected"},
        }

    return None


async def analyze_intent(
    message: str,
    history: list,
    business_knowledge: str,
    conversation_state: dict,
    customer_name: str,
    is_personal: bool,
    business_type: str = "",
) -> Dict[str, Any]:
    """
    Single AI call that returns full intent classification.
    Uses threaded-context: focuses on the immediate thread + relationship signal
    so the AI knows whether this is a follow-up or a new conversation.
    """
    # Fast deterministic override before calling LLM
    _override = _deterministic_intent_override(message)
    if _override:
        return _override

    # Affirmation gate: if the agent asked "want to see our services/catalog?"
    # and the customer replies with a simple yes/ok/sure → treat as catalog/booking intent
    # This prevents "yes" from looping back to ChatAgent and losing the thread.
    _AFFIRMATIONS = {"yes", "yeah", "yep", "yah", "sure", "ok", "okay", "ok!", "yes!", "sure!",
                     "yep!", "yes please", "sure thing", "go ahead", "show me", "proceed",
                     "ndio", "sawa", "karibu", "ndiyo",  # Swahili
                     "oui", "bien sûr", "d'accord",      # French
                     "نعم", "أجل",                       # Arabic
    }
    _msg_stripped = message.strip().lower().rstrip("!?.,'")
    if _msg_stripped in _AFFIRMATIONS and conversation_state.get("waiting_for_service_request"):
        _target_intent = "BOOKING_REQUEST" if any(k in (business_type or "").lower() for k in (
            "salon", "spa", "clinic", "barber", "beauty", "fitness", "gym", "service",
            "rental", "airbnb", "restaurant", "hotel", "saloon",
        )) else "CATALOG_REQUEST"
        lang = _detect_language(message) if _msg_stripped not in {"yes", "yeah", "yep", "sure", "ok", "okay"} else conversation_state.get("preferred_language", "English") or "English"
        return {
            "intent": _target_intent,
            "sentiment": "neutral",
            "language": lang,
            "entities": {"products": [], "amounts": [], "dates": [], "other": []},
            "conversation_state": "ongoing",
            "confidence": 0.95,
            "needs_escalation": False,
            "escalation_reason": None,
            "keywords": ["affirmation"],
            "contact_signal": {"type": "customer", "confidence": 0.9, "reason": "affirmation after service offer"},
            "_relationship": "follow_up",
            "_hours_since_last": None,
        }

    try:
        from ai_service import get_drafter
        ai = get_drafter()

        # Build threaded context
        threaded = build_threaded_context(history)
        history_text = format_threaded_history(threaded)
        relationship = threaded.get("relationship", "new_conversation")

        # Build conversation state hint — but RESET if new conversation
        state_hint = ""
        if conversation_state and relationship != "new_conversation":
            cs = conversation_state.get("state", "new")
            lp = conversation_state.get("last_discussed_product")
            lpo = conversation_state.get("last_price_offered")
            if cs != "new":
                state_hint = f"\nConversation is currently in state: {cs}."
                if lp:
                    state_hint += f" Last discussed product: {lp}."
                if lpo:
                    state_hint += f" Last price offered: {lpo}."

        bk_snippet = ""
        if business_knowledge:
            bk_snippet = f"\nBusiness context:\n{business_knowledge[:1200]}"

        personal_note = "\nThis is a personal contact (friend/family), not a business customer." if is_personal else ""

        # Business-type context: inform AI what this business sells
        SERVICE_BUSINESS_TYPES = {"salon", "saloon", "barbershop", "spa", "clinic", "healthcare", "fitness", "gym", "services", "restaurant", "hotel", "beauty", "rental"}
        _btype = (business_type or "").lower().strip()
        booking_bias = ""
        if _btype == "creator":
            booking_bias = (
                f"\n🎨 BUSINESS TYPE: 'creator' — This is a content creator / influencer business."
                f"\n   • Incoming messages are from brands wanting collabs, fans, or personal contacts."
                f"\n   • When someone asks about collabs, sponsorships, rates, what's included → CATALOG_REQUEST or BOOKING_REQUEST"
                f"\n   • When someone asks about deadlines, budgets, deliverables → BOOKING_REQUEST"
                f"\n   • When someone is a fan sending praise or casual messages → GENERAL_CHAT"
                f"\n   • NEVER classify a fan DM as a booking request unless they explicitly mention a collab."
            )
        elif _btype == "fitness" or any(k in _btype for k in ("gym", "yoga", "pilates", "crossfit", "zumba")):
            booking_bias = (
                f"\n🏋️ BUSINESS TYPE: 'fitness' — This is a gym / fitness studio."
                f"\n   • When customer asks about classes, schedule, timetable → AVAILABILITY_CHECK"
                f"\n   • When customer asks about membership, pricing, packages → CATALOG_REQUEST"
                f"\n   • When customer wants to join a class, sign up, book a session → BOOKING_REQUEST"
                f"\n   • When customer asks about a trainer → CATALOG_REQUEST or BOOKING_REQUEST"
                f"\n   • NEVER treat class schedule questions as ORDER_INQUIRY — they are AVAILABILITY_CHECK."
            )
        elif _btype == "healthcare" or any(k in _btype for k in ("clinic", "hospital", "doctor", "dental", "pharmacy", "medical", "health")):
            booking_bias = (
                f"\n🏥 BUSINESS TYPE: 'healthcare' — This is a medical/health practice."
                f"\n   • When patient asks about doctors, specialists, services offered → CATALOG_REQUEST"
                f"\n   • When patient asks about availability, slots, appointment times → AVAILABILITY_CHECK"
                f"\n   • When patient says 'I need to see a doctor', 'book appointment', 'schedule a visit' → BOOKING_REQUEST"
                f"\n   • When patient asks about insurance, NHIF, cost → PRODUCT_INQUIRY"
                f"\n   • NEVER classify appointment booking as ORDER_INQUIRY."
            )
        elif _btype == "restaurant" or any(k in _btype for k in ("cafe", "eatery", "bistro", "hotel", "canteen")):
            booking_bias = (
                f"\n🍽️ BUSINESS TYPE: 'restaurant' — This is a food/dining establishment."
                f"\n   • When customer asks about the menu, what's available, food options → CATALOG_REQUEST"
                f"\n   • When customer wants to make a reservation, book a table → BOOKING_REQUEST"
                f"\n   • When customer asks about dietary options, halal, vegan → PRODUCT_INQUIRY"
                f"\n   • When customer asks about availability / table for a specific time → AVAILABILITY_CHECK"
                f"\n   • NEVER classify a table reservation as an ORDER_INQUIRY."
            )
        elif _btype == "salon" or any(k in _btype for k in ("saloon", "barbershop", "beauty", "spa", "barber", "nail", "lash")):
            booking_bias = (
                f"\n💇 BUSINESS TYPE: 'salon' — This is a hair/beauty salon or spa."
                f"\n   • When customer asks about services, prices, what's available → CATALOG_REQUEST"
                f"\n   • When customer asks about a specific stylist → CATALOG_REQUEST"
                f"\n   • When customer wants to book, make appointment → BOOKING_REQUEST"
                f"\n   • When customer asks about availability, free slots, when is [stylist] free → AVAILABILITY_CHECK"
                f"\n   • NEVER treat a service inquiry as ORDER_INQUIRY."
            )
        elif _btype == "tech" or any(k in _btype for k in ("saas", "fintech", "software", "app", "platform", "agency", "startup", "digital")):
            booking_bias = (
                f"\n💻 BUSINESS TYPE: 'tech' — This is a software/SaaS/fintech/digital product company."
                f"\n   • When prospect asks about features, what the product does → PRODUCT_INQUIRY or CATALOG_REQUEST"
                f"\n   • When prospect asks about pricing, plans, cost → PRODUCT_INQUIRY"
                f"\n   • When prospect wants a demo, trial, walkthrough, onboarding call → BOOKING_REQUEST"
                f"\n   • When prospect asks about integrations, API, security → PRODUCT_INQUIRY"
                f"\n   • When existing customer asks about support, billing, account issues → COMPLAINT or GENERAL_CHAT"
                f"\n   • NEVER classify a demo request as AVAILABILITY_CHECK — it is BOOKING_REQUEST."
            )
        elif _btype in SERVICE_BUSINESS_TYPES or any(k in _btype for k in ("service", "rental", "airbnb")):
            booking_bias = (
                f"\n📅 BUSINESS TYPE: '{business_type}' — This business offers SERVICES/APPOINTMENTS/RENTALS."
                f"\n   • When customer asks 'what do you offer', 'show me services', 'what do you have' → CATALOG_REQUEST or BOOKING_REQUEST"
                f"\n   • When customer asks about availability, times, dates → AVAILABILITY_CHECK"
                f"\n   • When customer says 'I want to book', 'make appointment' → BOOKING_REQUEST"
                f"\n   • Routing to correct agent happens automatically based on business type, so classify intent naturally."
            )
        else:
            booking_bias = (
                f"\n📋 BUSINESS TYPE: '{business_type}' — This business sells PHYSICAL PRODUCTS."
                f"\n   • When customer asks 'what do you have', 'show catalog' → CATALOG_REQUEST"
                f"\n   • When customer asks about specific products → PRODUCT_INQUIRY"
                f"\n   • Routing to correct agent happens automatically based on business type."
            )

        prompt = f"""You are an AI intent classifier for a WhatsApp business assistant.

══ BUSINESS CONTEXT ══{bk_snippet}{booking_bias}

══ CUSTOMER ══
Name: {customer_name}{personal_note}{state_hint}

══ CONVERSATION HISTORY ══
{history_text}

══ CURRENT MESSAGE — classify THIS ══
"{message}"

══ INTENT EXAMPLES (multilingual) ══
PRICE_INQUIRY: "bei gani", "how much", "ngapi", "price ya", "combien ça coûte", "क्या दाम है", "quanto custa", "what's the price", "cost?", "جاوب بالسعر"
CATALOG_REQUEST: "show me what you have", "niambie mnayo", "send catalog", "what are you selling", "I want to order something", "nataka buy kitu", "nataka kununua", "i want to buy", "let me see your products", "je veux voir vos produits", "kuna nini", "ما عندكم"
PRODUCT_INQUIRY: "do you have red dresses?", "tell me about the iPhone", "nina haja ya", "je cherche", "¿tienen zapatos?", "क्या आपके पास है"
ORDER_STATUS: "order yangu iko wapi", "when delivery", "nimewait sana", "où est ma commande", "dónde está mi pedido", "where is my order", "has it shipped", "طلبي فين"
PAYMENT_METHOD: "nipe namba ya mpesa", "send payment method", "how do I pay", "comment payer", "account number please", "¿cómo pago?", "payment details please"
PAYMENT_CONFIRM: "mpesa haikufika", "nililipa lakini", "payment failed", "le paiement a échoué", "i've paid", "sent the money", "check your mpesa", "nimesend"
GREETING: "sasa", "niaje", "mambo", "hi", "habari", "bonjour", "hola", "नमस्ते", "salut", "wagwan", "sup", "ahlan"
COMPLAINT: "bidhaa mbaya", "siko happy", "not what I ordered", "je ne suis pas satisfait", "I'm not happy", "poor quality", "this is wrong", "مشكلة"
BOOKING_REQUEST: "I want to book", "naweza kuja lini", "je veux réserver", "quiero una cita", "book me in", "can I make an appointment", "احجز لي"
AVAILABILITY_CHECK: "when are you available", "are you open Saturday", "do you have slots", "quand êtes-vous disponible", "متى تكونون متاحين"
BOOKING_STATUS: "status ya booking", "my appointment", "is my booking confirmed", "ma réservation est-elle confirmée", "mis citas", "show my bookings", "booking yangu", "طلبي للموعد", "where is my booking"
NEGOTIATION: "can you do better", "too expensive", "bei ni kubwa sana", "c'est trop cher", "any discount", "best price", "kuna offer"
RESET_CONVERSATION: "start over", "restart", "clear everything", "wrong booking", "actually let's do something else", "begin again", "tuanze upya", "anza tena"
GO_BACK: "ignore that last message", "wait go back", "previous step", "actually not that", "go back", "rudisha nyuma"

══ GLOBAL LANGUAGE RULES ══
- Classify in ANY language — no language is default or assumed
- Handle transliterated text (Arabic/Hindi/Swahili written in Latin script)
- Handle code-switching (two languages in one message e.g. "haha crazy... btw order yangu iko wapi")
- Detect language and store it — do not normalize to English
- "Sheng", "Pidgin", "Hinglish", "Arabizi" are valid language values
- Never correct the customer's language choice

══ ENTITY RULES ══
- Preserve original currency format (R500, ₦2000, $50, ¥3000, KES 500, NGN 2000) — do NOT normalize
- Do NOT normalize dates — "5/6" means different things globally, store as-is
- Store phone numbers with country code context if present
- Pass raw entity strings — do not transform or convert

══ TRANSITION RULE ══
- If message contains BOTH small talk AND a business question, classify as the BUSINESS intent
- Example: "haha crazy weather... btw when is my order?" → ORDER_STATUS

══ CLASSIFICATION RULES ══
1. Understand INTENT not exact words — "I want to order something else" = CATALOG_REQUEST
2. Short follow-ups ("ok", "yes", "sure") inherit business intent ONLY if the business explicitly offered a product/action. If the business just asked a casual question, classify as GENERAL_CHAT.
3. When unsure between two intents, pick the one that requires ACTION
4. For personal contacts, prefer PERSONAL_CHAT unless clearly business
5. Confidence < 0.65 on business messages → needs_escalation=true
6. Confidence < 0.50 on business messages → intent should be "UNKNOWN"
7. LEGAL_THREAT, FRAUD_CLAIM always → needs_escalation=true
8. List up to 2 alternative_intents if confidence < 0.85 and there are other plausible intents
9. SYSTEMIC DISAMBIGUATION: 'Wanting to buy/order something new' is CATALOG_REQUEST. 'Checking on a payment or delivery for an already placed order' is ORDER_STATUS. Do not confuse the action of placing a new order with checking an old one!

══ CONTACT SIGNAL RULES ══
For contact_signal.type:
- "customer": ANY product/price/order/delivery/booking/payment question, "how much", "do you have", "I want", "bei gani", "catalog", "stock", "available"
- "personal": casual greeting with no business follow-up, mentions owner by name, "it's me", "tuongee", "call me", emotional/social context only, emojis with no business intent
- "unclear": cannot determine from this message alone
For contact_signal.confidence: how certain you are (0.0-1.0)
For contact_signal.reason: brief explanation in 5 words or fewer

Return ONLY valid JSON with these exact keys:
{{
  "intent": "<INTENT>",
  "alternative_intents": [],
  "sentiment": "<happy|neutral|frustrated|angry|urgent>",
  "language": "<language name or code, e.g. English, Swahili, Sheng, Arabic, Hinglish>",
  "entities": {{
    "products": [],
    "amounts": [],
    "dates": [],
    "other": []
  }},
  "conversation_state": "<new|ongoing|negotiating|closing|resolved>",
  "confidence": <0.0-1.0>,
  "needs_escalation": <true|false>,
  "escalation_reason": "<reason or null>",
  "keywords": [],
  "contact_signal": {{
    "type": "<customer|personal|unclear>",
    "confidence": <0.0-1.0>,
    "reason": "<brief reason>"
  }}
}}

JSON only, no markdown:"""

        raw = await ai._call_llm(prompt, model_pref="standard")

        # Strip markdown if present
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            raise ValueError(f"No JSON in response: {raw[:200]}")

        result = json.loads(json_match.group())

        # Store relationship signal for downstream agents
        result["_relationship"] = relationship
        result["_hours_since_last"] = threaded.get("hours_since_last")

        # Ensure alternative_intents field exists (1.2)
        if "alternative_intents" not in result:
            result["alternative_intents"] = []

        # 16.1: Ensure contact_signal field exists
        if "contact_signal" not in result:
            result["contact_signal"] = {"type": "unclear", "confidence": 0.0, "reason": "not classified"}
        # If intent is clearly business → upgrade contact_signal to customer if not already
        _biz_intents = {
            "PRODUCT_INQUIRY", "CATALOG_REQUEST", "PRICE_NEGOTIATION",
            "ORDER_STATUS", "ORDER_CANCEL", "ORDER_UPDATE",
            "PAYMENT_CONFIRM", "PAYMENT_METHOD_QUESTION", "PAYMENT_ISSUE",
            "COMPLAINT", "REFUND_REQUEST", "DAMAGED_ITEM", "WRONG_ITEM",
            "BOOKING_REQUEST", "BOOKING_CANCEL", "BOOKING_RESCHEDULE",
        }
        if result.get("intent") in _biz_intents and result["contact_signal"]["type"] != "customer":
            result["contact_signal"] = {"type": "customer", "confidence": 0.95, "reason": "business intent detected"}

        # Enforce escalation on always-escalate intents
        intent = result.get("intent", "UNKNOWN")
        if intent in ALWAYS_ESCALATE_INTENTS:
            result["needs_escalation"] = True
            if not result.get("escalation_reason"):
                result["escalation_reason"] = f"Intent '{intent}' always requires human review"

        # 1.1: Low confidence → UNKNOWN intent threshold
        confidence = float(result.get("confidence", 0.5))
        if confidence < UNKNOWN_THRESHOLD and intent not in CHAT_INTENTS and intent != "UNKNOWN":
            result["intent"] = "UNKNOWN"
            intent = "UNKNOWN"
            logger.info(f"[IntentAnalyzer] Low confidence ({confidence:.2f}) → reclassified to UNKNOWN")

        # 1.1: Raise escalation threshold to 0.65
        if confidence < ESCALATE_THRESHOLD and intent not in CHAT_INTENTS:
            result["needs_escalation"] = True
            if not result.get("escalation_reason"):
                result["escalation_reason"] = f"Low confidence ({confidence:.2f}) — human review needed"

        # UNKNOWN intent on short messages = conversational follow-up, not escalation
        if intent == "UNKNOWN" and len(message.split()) <= 8:
            result["intent"] = "GENERAL_CHAT"
            result["needs_escalation"] = False
            result["escalation_reason"] = None
            result["confidence"] = 0.7
            logger.info(f"[IntentAnalyzer] Short UNKNOWN message reclassified as GENERAL_CHAT: '{message}'")

        logger.info(
            f"[IntentAnalyzer] intent={result.get('intent')} alt={result.get('alternative_intents')} "
            f"sentiment={result.get('sentiment')} confidence={result.get('confidence')} "
            f"escalate={result.get('needs_escalation')} relationship={relationship}"
        )
        return result

    except Exception as e:
        logger.error(f"[IntentAnalyzer] error: {e}")
        return {
            "intent": "UNKNOWN",
            "sentiment": "neutral",
            "language": "English",
            "entities": {"products": [], "amounts": [], "dates": [], "other": []},
            "conversation_state": "new",
            "confidence": 0.0,
            "alternative_intents": [],
            "needs_escalation": True,
            "escalation_reason": f"Intent analysis failed: {e}",
            "keywords": [],
            "contact_signal": {"type": "unclear", "confidence": 0.0, "reason": "analysis failed"},
            "_relationship": "new_conversation",
            "_hours_since_last": None,
        }


def route_intent_to_agent(intent: str, business_type: str = "", contact_type: str = "UNKNOWN") -> str:
    """
    Route to agent based on BUSINESS TYPE first, then intent.
    Business type determines the workflow - customer's words don't matter.
    """
    _btype = (business_type or "").lower().strip()
    
    # Service/Rental/Restaurant businesses → ALWAYS use BookingAgent (except complaints/orders/payments)
    SERVICE_BUSINESS_TYPES = {
        "salon", "saloon", "barbershop", "spa", "clinic", "healthcare",
        "fitness", "gym", "services", "restaurant", "hotel", "beauty",
        "rental", "airbnb", "creator", "tech"
    }
    
    is_service_business = (
        _btype in SERVICE_BUSINESS_TYPES or 
        any(k in _btype for k in ("salon", "spa", "clinic", "barber", "beauty", "fitness", "gym", "service", "rental", "airbnb", "restaurant", "hotel"))
    )
    
    # Complaints/Orders/Payments always go to their respective agents regardless of business type
    if intent in COMPLAINT_INTENTS:
        return "complaint"
    if intent in ORDER_INTENTS:
        return "order"
    if intent in PAYMENT_INTENTS:
        return "payment"
    
    # Service businesses → BookingAgent for ALL catalog/sales/booking intents
    if is_service_business:
        if intent in (SALES_INTENTS | BOOKING_INTENTS):
            return "booking"

    # Retail/Shop businesses → SalesAgent for ALL catalog/sales/booking intents
    else:
        if intent in (SALES_INTENTS | BOOKING_INTENTS):
            return "sales"

    # Chat intents (GREETING, GENERAL_CHAT, SMALL_TALK, PERSONAL_CHAT, OFF_TOPIC)
    # always go to ChatAgent — for ALL contact types.
    # ChatAgent replies naturally and has guardrails that return handled=False
    # when a real booking/order request is detected, which then falls through
    # to the correct agent. Never push products at someone who just said hi.
    return "chat"
