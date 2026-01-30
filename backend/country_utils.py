"""
Utility functions for country detection and payment method defaults
"""

# Country code to payment methods mapping
COUNTRY_PAYMENT_METHODS = {
    # East Africa
    "KE": {
        "currency": "KES",
        "methods": ["M-Pesa", "Airtel Money", "Cash", "Bank Transfer"]
    },
    "TZ": {
        "currency": "TZS",
        "methods": ["M-Pesa", "Tigo Pesa", "Airtel Money", "Cash"]
    },
    "UG": {
        "currency": "UGX",
        "methods": ["MTN Mobile Money", "Airtel Money", "Cash", "Bank Transfer"]
    },
    "RW": {
        "currency": "RWF",
        "methods": ["MTN Mobile Money", "Airtel Money", "Cash"]
    },
    
    # West Africa
    "NG": {
        "currency": "NGN",
        "methods": ["Cash", "Bank Transfer", "Opay", "PalmPay"]
    },
    "GH": {
        "currency": "GHS",
        "methods": ["MTN Mobile Money", "Vodafone Cash", "Cash", "Bank Transfer"]
    },
    
    # South Africa
    "ZA": {
        "currency": "ZAR",
        "methods": ["Cash", "EFT", "SnapScan", "Zapper"]
    },
    
    # India
    "IN": {
        "currency": "INR",
        "methods": ["UPI", "Paytm", "PhonePe", "Google Pay", "Cash"]
    },
    
    # Southeast Asia
    "ID": {
        "currency": "IDR",
        "methods": ["GoPay", "OVO", "DANA", "Cash", "Bank Transfer"]
    },
    "PH": {
        "currency": "PHP",
        "methods": ["GCash", "PayMaya", "Cash", "Bank Transfer"]
    },
    "MY": {
        "currency": "MYR",
        "methods": ["Touch 'n Go", "Boost", "GrabPay", "Cash"]
    },
    
    # Latin America
    "BR": {
        "currency": "BRL",
        "methods": ["PIX", "Cash", "Credit Card", "Boleto"]
    },
    "MX": {
        "currency": "MXN",
        "methods": ["Cash", "OXXO", "SPEI", "Mercado Pago"]
    },
    "AR": {
        "currency": "ARS",
        "methods": ["Cash", "Mercado Pago", "Bank Transfer"]
    },
    "CO": {
        "currency": "COP",
        "methods": ["Cash", "Nequi", "Daviplata", "Bank Transfer"]
    },
    
    # Middle East
    "EG": {
        "currency": "EGP",
        "methods": ["Cash", "Vodafone Cash", "Bank Transfer"]
    },
    "SA": {
        "currency": "SAR",
        "methods": ["Cash", "STC Pay", "Bank Transfer"]
    },
    
    # Default fallback
    "DEFAULT": {
        "currency": "USD",
        "methods": ["Cash", "Mobile Money", "Bank Transfer", "Card"]
    }
}

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
        "254": "KE",  # Kenya
        "255": "TZ",  # Tanzania
        "256": "UG",  # Uganda
        "250": "RW",  # Rwanda
        
        # West Africa
        "234": "NG",  # Nigeria
        "233": "GH",  # Ghana
        
        # South Africa
        "27": "ZA",
        
        # India
        "91": "IN",
        
        # Southeast Asia
        "62": "ID",   # Indonesia
        "63": "PH",   # Philippines
        "60": "MY",   # Malaysia
        
        # Latin America
        "55": "BR",   # Brazil
        "52": "MX",   # Mexico
        "54": "AR",   # Argentina
        "57": "CO",   # Colombia
        
        # Middle East
        "20": "EG",   # Egypt
        "966": "SA",  # Saudi Arabia
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
