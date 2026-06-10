"""
Utility functions for country detection and payment method defaults
"""

# Country code to payment methods mapping
COUNTRY_PAYMENT_METHODS = {
    # East Africa
    # East Africa — M-Pesa dominates KE/TZ, mobile money leads all
    "KE": {"currency": "KES", "methods": ["M-Pesa", "Airtel Money", "Cash"]},
    "TZ": {"currency": "TZS", "methods": ["M-Pesa", "Tigo Pesa", "Cash"]},
    "UG": {"currency": "UGX", "methods": ["MTN Mobile Money", "Airtel Money", "Cash"]},
    "RW": {"currency": "RWF", "methods": ["MTN Mobile Money", "Airtel Money", "Cash"]},
    "ET": {"currency": "ETB", "methods": ["CBE Birr", "Cash", "Bank Transfer"]},

    # West Africa
    "NG": {"currency": "NGN", "methods": ["Bank Transfer", "Opay", "Cash"]},
    "GH": {"currency": "GHS", "methods": ["MTN Mobile Money", "Vodafone Cash", "Cash"]},
    "SN": {"currency": "XOF", "methods": ["Wave", "Orange Money", "Cash"]},
    "CI": {"currency": "XOF", "methods": ["Orange Money", "Wave", "Cash"]},
    "CM": {"currency": "XAF", "methods": ["MTN Mobile Money", "Orange Money", "Cash"]},

    # Southern Africa
    "ZA": {"currency": "ZAR", "methods": ["Cash", "EFT", "SnapScan"]},
    "ZW": {"currency": "USD", "methods": ["EcoCash", "Cash", "Bank Transfer"]},
    "ZM": {"currency": "ZMW", "methods": ["MTN Mobile Money", "Airtel Money", "Cash"]},

    # North Africa / Middle East
    "EG": {"currency": "EGP", "methods": ["Vodafone Cash", "Cash", "Bank Transfer"]},
    "SA": {"currency": "SAR", "methods": ["STC Pay", "Cash", "Bank Transfer"]},
    "AE": {"currency": "AED", "methods": ["Cash", "Card", "Bank Transfer"]},
    "MA": {"currency": "MAD", "methods": ["Cash", "Bank Transfer", "Card"]},

    # South Asia
    "IN": {"currency": "INR", "methods": ["UPI", "PhonePe", "Cash"]},
    "PK": {"currency": "PKR", "methods": ["JazzCash", "Easypaisa", "Cash"]},
    "BD": {"currency": "BDT", "methods": ["bKash", "Nagad", "Cash"]},

    # Southeast Asia
    "ID": {"currency": "IDR", "methods": ["GoPay", "OVO", "Cash"]},
    "PH": {"currency": "PHP", "methods": ["GCash", "Cash", "Bank Transfer"]},
    "MY": {"currency": "MYR", "methods": ["Touch 'n Go", "GrabPay", "Cash"]},
    "TH": {"currency": "THB", "methods": ["PromptPay", "TrueMoney", "Cash"]},
    "VN": {"currency": "VND", "methods": ["MoMo", "ZaloPay", "Cash"]},

    # Latin America
    "BR": {"currency": "BRL", "methods": ["PIX", "Cash", "Credit Card"]},
    "MX": {"currency": "MXN", "methods": ["Cash", "SPEI", "Mercado Pago"]},
    "AR": {"currency": "ARS", "methods": ["Mercado Pago", "Cash", "Bank Transfer"]},
    "CO": {"currency": "COP", "methods": ["Nequi", "Daviplata", "Cash"]},
    "CL": {"currency": "CLP", "methods": ["Mercado Pago", "Bank Transfer", "Cash"]},
    "PE": {"currency": "PEN", "methods": ["Yape", "Plin", "Cash"]},

    # Europe / North America
    "US": {"currency": "USD", "methods": ["Zelle", "Cash App", "Card"]},
    "GB": {"currency": "GBP", "methods": ["Bank Transfer", "Card", "Cash"]},
    "EU": {"currency": "EUR", "methods": ["Bank Transfer", "Card", "Cash"]},
    "CA": {"currency": "CAD", "methods": ["Interac e-Transfer", "Card", "Cash"]},
    "FI": {"currency": "EUR", "methods": ["Bank Transfer", "MobilePay", "Card"]},

    # Default fallback
    "DEFAULT": {"currency": "USD", "methods": ["Cash", "Bank Transfer", "Card"]}
}

# ISO 3166-1 alpha-2 → E.164 country calling code (no +)
ISO_DIAL_CODES = {
    "KE": "254", "TZ": "255", "UG": "256", "RW": "250", "ET": "251", "ZM": "260", "ZW": "263",
    "NG": "234", "GH": "233", "SN": "221", "CI": "225", "CM": "237",
    "ZA": "27", "EG": "20", "MA": "212", "SA": "966", "AE": "971",
    "IN": "91", "PK": "92", "BD": "880",
    "ID": "62", "PH": "63", "MY": "60", "TH": "66", "VN": "84",
    "BR": "55", "MX": "52", "AR": "54", "CO": "57", "CL": "56", "PE": "51",
    "US": "1", "CA": "1", "GB": "44", "FI": "358", "SE": "46", "NO": "47", "DK": "45",
    "DE": "49", "FR": "33", "NL": "31", "BE": "32", "ES": "34", "IT": "39", "PT": "351",
    "IE": "353", "AT": "43", "CH": "41", "PL": "48", "AU": "61", "NZ": "64",
    "JP": "81", "KR": "82", "SG": "65", "HK": "852", "TW": "886",
}


def get_dial_code(country_code: str) -> str:
    """Return E.164 calling code digits for an ISO country code, or empty string."""
    return ISO_DIAL_CODES.get((country_code or "").strip().upper(), "")


def detect_country_from_phone(phone_number: str) -> str:
    """
    Detect country code from phone number.
    Returns 2-letter country code or 'DEFAULT'
    """
    # Remove any non-digit characters
    phone = ''.join(filter(str.isdigit, phone_number))
    
    # Country code mappings (common WhatsApp countries)
    country_codes = {
        # East Africa
        "254": "KE",   # Kenya
        "255": "TZ",   # Tanzania
        "256": "UG",   # Uganda
        "250": "RW",   # Rwanda
        "251": "ET",   # Ethiopia
        "260": "ZM",   # Zambia
        "263": "ZW",   # Zimbabwe
        # West Africa
        "234": "NG",   # Nigeria
        "233": "GH",   # Ghana
        "221": "SN",   # Senegal
        "225": "CI",   # Ivory Coast
        "237": "CM",   # Cameroon
        # South / North Africa
        "27": "ZA",    # South Africa
        "20": "EG",    # Egypt
        "212": "MA",   # Morocco
        # Middle East
        "966": "SA",   # Saudi Arabia
        "971": "AE",   # UAE
        # South Asia
        "91": "IN",    # India
        "92": "PK",    # Pakistan
        "880": "BD",   # Bangladesh
        # Southeast Asia
        "62": "ID",    # Indonesia
        "63": "PH",    # Philippines
        "60": "MY",    # Malaysia
        "66": "TH",    # Thailand
        "84": "VN",    # Vietnam
        # Latin America
        "55": "BR",    # Brazil
        "52": "MX",    # Mexico
        "54": "AR",    # Argentina
        "57": "CO",    # Colombia
        "56": "CL",    # Chile
        "51": "PE",    # Peru
        # Europe / North America
        "1": "US",     # USA/Canada (broad — refined below)
        "44": "GB",    # UK
        "358": "FI",   # Finland
    }
    
    # Try to match country code
    for code, country in country_codes.items():
        if phone.startswith(code):
            return country
    
    return "DEFAULT"

def get_payment_methods_for_country(country_code: str) -> dict:
    """
    Get payment methods and currency for a country.
    Returns dict with 'currency' and 'methods' keys
    """
    return COUNTRY_PAYMENT_METHODS.get(country_code, COUNTRY_PAYMENT_METHODS["DEFAULT"])
