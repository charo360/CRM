"""
Multilingual UI strings for menu headers, list labels, and instruction text.
Used by all agents to ensure the customer always sees text in their language.

Usage:
    from .ui_strings import t
    header = t("services_header", language)
"""

# Keys → language → translated string
# "English" is always the fallback
_STRINGS: dict = {

    # ── Service/booking list ──────────────────────────────────────────────────
    "services_header": {
        "English":    "📋 *Our Services*",
        "Swahili":    "📋 *Huduma Zetu*",
        "Sheng":      "📋 *Vitu Tunafanya*",
        "French":     "📋 *Nos Services*",
        "Spanish":    "📋 *Nuestros Servicios*",
        "Portuguese": "📋 *Nossos Serviços*",
        "Arabic":     "📋 *خدماتنا*",
        "Hausa":      "📋 *Ayyukanmu*",
        "Yoruba":     "📋 *Awọn Iṣẹ Wa*",
        "Igbo":       "📋 *Ọrụ Anyị*",
        "Somali":     "📋 *Adeegyadeena*",
        "Luganda":    "📋 *Omulimu Gwaffe*",
        "Pidgin":     "📋 *Our Services*",
        "Hinglish":   "📋 *Hamari Services*",
        "Amharic":    "📋 *አገልግሎቶቻችን*",
        "Hindi":      "📋 *हमारी सेवाएँ*",
    },

    # ── Product/catalog list ──────────────────────────────────────────────────
    "products_header": {
        "English":    "🛍️ *Our Products*",
        "Swahili":    "🛍️ *Bidhaa Zetu*",
        "Sheng":      "🛍️ *Vitu Vyetu*",
        "French":     "🛍️ *Nos Produits*",
        "Spanish":    "🛍️ *Nuestros Productos*",
        "Portuguese": "🛍️ *Nossos Produtos*",
        "Arabic":     "🛍️ *منتجاتنا*",
        "Hausa":      "🛍️ *Kayayyakinmu*",
        "Yoruba":     "🛍️ *Awọn Ọja Wa*",
        "Igbo":       "🛍️ *Ngwongwo Anyị*",
        "Somali":     "🛍️ *Badeecadaheena*",
        "Luganda":    "🛍️ *Ebintu Byaffe*",
        "Pidgin":     "🛍️ *Our Tings*",
        "Hinglish":   "🛍️ *Hamare Products*",
        "Amharic":    "🛍️ *ምርቶቻችን*",
        "Hindi":      "🛍️ *हमारे उत्पाद*",
    },

    # ── Rental/property list ──────────────────────────────────────────────────
    "listings_header": {
        "English":    "🏠 *Our Listings*",
        "Swahili":    "🏠 *Nyumba/Vyumba Vyetu*",
        "Sheng":      "🏠 *Pads Zetu*",
        "French":     "🏠 *Nos Annonces*",
        "Spanish":    "🏠 *Nuestros Alojamientos*",
        "Portuguese": "🏠 *Nossas Listagens*",
        "Arabic":     "🏠 *قوائمنا*",
        "Hausa":      "🏠 *Gidajenmu*",
        "Yoruba":     "🏠 *Awọn Ile Wa*",
        "Igbo":       "🏠 *Ụlọ Anyị*",
        "Somali":     "🏠 *Guryaheena*",
        "Luganda":    "🏠 *Enyumba Zaffe*",
        "Pidgin":     "🏠 *Our Places*",
        "Hinglish":   "🏠 *Hamari Properties*",
        "Amharic":    "🏠 *ቤቶቻችን*",
        "Hindi":      "🏠 *हमारे स्थान*",
    },

    # ── "Reply with a number to select" instruction ───────────────────────────
    "select_number_instruction": {
        "English":    "_Reply with a number to select_",
        "Swahili":    "_Jibu na namba kuchagua_",
        "Sheng":      "_Reply na namba kuchagua_",
        "French":     "_Répondez avec un numéro pour choisir_",
        "Spanish":    "_Responde con un número para elegir_",
        "Portuguese": "_Responda com um número para escolher_",
        "Arabic":     "_أرسل رقماً للاختيار_",
        "Hausa":      "_Amsa da lamba don zaɓi_",
        "Yoruba":     "_Dahun pẹlu nọmba kan lati yan_",
        "Igbo":       "_Zaa ọnọdụ nọmba iji họrọ_",
        "Somali":     "_Ku jawaab nambar si aad u doorato_",
        "Luganda":    "_Ddamu n'ennamba okuŋŋamba_",
        "Pidgin":     "_Reply with number to pick_",
        "Hinglish":   "_Number se reply karo chunne ke liye_",
        "Amharic":    "_ለመምረጥ ቁጥር ይላኩ_",
        "Hindi":      "_चुनने के लिए नंबर से जवाब दें_",
    },

    # ── "Reply with a number to book" instruction ────────────────────────────
    "book_number_instruction": {
        "English":    "_Reply with the number to book_",
        "Swahili":    "_Jibu na namba kuhifadhi nafasi_",
        "Sheng":      "_Reply na namba ku-book_",
        "French":     "_Répondez avec le numéro pour réserver_",
        "Spanish":    "_Responde con el número para reservar_",
        "Portuguese": "_Responda com o número para reservar_",
        "Arabic":     "_أرسل الرقم للحجز_",
        "Hausa":      "_Amsa da lamba don ɗauki wurin_",
        "Yoruba":     "_Dahun pẹlu nọmba lati ṣe àyẹwò_",
        "Igbo":       "_Zaa nọmba iji dee akwụkwọ_",
        "Somali":     "_Ku jawaab nambar si aad u buukiso_",
        "Luganda":    "_Ddamu n'ennamba okuteeka_",
        "Pidgin":     "_Reply with number to book_",
        "Hinglish":   "_Number se reply karo booking ke liye_",
        "Amharic":    "_ቦታ ለማስጠበቅ ቁጥር ይላኩ_",
        "Hindi":      "_बुकिंग के लिए नंबर से जवाब दें_",
    },

    # ── "See more" label ─────────────────────────────────────────────────────
    "see_more": {
        "English":    "9️⃣  ➡️ *See more*",
        "Swahili":    "9️⃣  ➡️ *Ona zaidi*",
        "Sheng":      "9️⃣  ➡️ *Ona zaidi*",
        "French":     "9️⃣  ➡️ *Voir plus*",
        "Spanish":    "9️⃣  ➡️ *Ver más*",
        "Portuguese": "9️⃣  ➡️ *Ver mais*",
        "Arabic":     "9️⃣  ➡️ *عرض المزيد*",
        "Hausa":      "9️⃣  ➡️ *Duba ƙari*",
        "Yoruba":     "9️⃣  ➡️ *Wo diẹ sii*",
        "Igbo":       "9️⃣  ➡️ *Hụ ọzọ*",
        "Somali":     "9️⃣  ➡️ *Arag intii kale*",
        "Luganda":    "9️⃣  ➡️ *Laba ebisingawo*",
        "Pidgin":     "9️⃣  ➡️ *See more tings*",
        "Hinglish":   "9️⃣  ➡️ *Aur dekho*",
        "Amharic":    "9️⃣  ➡️ *ተጨማሪ ይመልከቱ*",
        "Hindi":      "9️⃣  ➡️ *और देखें*",
    },

    # ── "View gallery / View all images" label ────────────────────────────────
    "view_gallery": {
        "English":    "0️⃣  🖼️ *View Gallery*",
        "Swahili":    "0️⃣  🖼️ *Tazama Picha*",
        "Sheng":      "0️⃣  🖼️ *Angalia Picha*",
        "French":     "0️⃣  🖼️ *Voir les Photos*",
        "Spanish":    "0️⃣  🖼️ *Ver Galería*",
        "Portuguese": "0️⃣  🖼️ *Ver Galeria*",
        "Arabic":     "0️⃣  🖼️ *عرض الصور*",
        "Hausa":      "0️⃣  🖼️ *Duba Hotuna*",
        "Yoruba":     "0️⃣  🖼️ *Wo Awọn Aworan*",
        "Igbo":       "0️⃣  🖼️ *Hụ Foto*",
        "Somali":     "0️⃣  🖼️ *Arag Sawirrada*",
        "Luganda":    "0️⃣  🖼️ *Laba Ebifaananyi*",
        "Pidgin":     "0️⃣  🖼️ *See Photos*",
        "Hinglish":   "0️⃣  🖼️ *Photos Dekho*",
        "Amharic":    "0️⃣  🖼️ *ፎቶዎች ይመልከቱ*",
        "Hindi":      "0️⃣  🖼️ *फ़ोटो देखें*",
    },

    # ── Rental select instruction ─────────────────────────────────────────────
    "rental_select_instruction": {
        "English":    "_Reply with the number of the listing you'd like to book_",
        "Swahili":    "_Jibu na namba ya chumba/nyumba unayotaka kuhifadhi_",
        "Sheng":      "_Reply na namba ya pad unayotaka ku-book_",
        "French":     "_Répondez avec le numéro de l'annonce à réserver_",
        "Spanish":    "_Responde con el número del alojamiento que deseas reservar_",
        "Portuguese": "_Responda com o número da listagem que deseja reservar_",
        "Arabic":     "_أرسل رقم القائمة التي تريد حجزها_",
        "Hausa":      "_Amsa da lamba don ɗauki gidan_",
        "Yoruba":     "_Dahun pẹlu nọmba ti o fẹ ṣe àyẹwò_",
        "Igbo":       "_Zaa nọmba ụlọ ị chọrọ_",
        "Somali":     "_Ku jawaab nambarka guriga aad rabto_",
        "Luganda":    "_Ddamu n'ennamba y'enyumba gy'ofuna_",
        "Pidgin":     "_Reply with the number of the place you want_",
        "Hinglish":   "_Jo property chahiye uska number bhejo_",
        "Amharic":    "_የሚፈልጉትን ቦታ ቁጥር ይላኩ_",
        "Hindi":      "_जो संपत्ति चाहिए उसका नंबर भेजें_",
    },
}

_FALLBACK = "English"


def t(key: str, language: str) -> str:
    """
    Return UI string for the given key in the given language.
    Falls back to English if the language or key is not found.
    """
    lang_map = _STRINGS.get(key, {})
    return lang_map.get(language) or lang_map.get(_FALLBACK, key)
