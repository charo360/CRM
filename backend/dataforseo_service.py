"""
DataForSEO API integration for keyword research and search volume data.
Provides accurate search volume, competition, and keyword difficulty metrics.
"""
import os
import logging
import httpx
import base64
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def _get_auth_header() -> str:
    """Get DataForSEO API auth header from environment (uses existing DATAFORSEO_TOKEN)."""
    token = os.getenv("DATAFORSEO_TOKEN", "").strip()
    if not token:
        raise ValueError("DATAFORSEO_TOKEN must be set")
    return f"Basic {token}"


async def get_keyword_data(
    keywords: List[str],
    location_code: Optional[int] = None,
    language_code: str = "en",
) -> Dict[str, Any]:
    """
    Get search volume and metrics for a list of keywords.

    Args:
        keywords: List of keywords to research (max 1000 per request)
        location_code: DataForSEO location code. None = global/worldwide data.
        language_code: Language code (en, es, fr, etc.)

    Returns:
        {
            "keywords": [
                {
                    "keyword": str,
                    "search_volume": int,
                    "competition": float (0-1),
                    "cpc": float (USD),
                    "trend": List[int] (12 months),
                }
            ],
            "location": str,
            "language": str,
        }
    """
    if not keywords:
        return {"keywords": [], "location": "", "language": language_code}

    # Limit to 1000 keywords per request (API limit)
    keywords = keywords[:1000]

    url = "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live"

    task: Dict[str, Any] = {
        "keywords": keywords,
        "language_code": language_code,
    }
    if location_code is not None:
        task["location_code"] = location_code
    payload = [task]
    
    headers = {
        "Authorization": _get_auth_header(),
        "Content-Type": "application/json",
    }
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        if data.get("status_code") != 20000:
            error_msg = data.get("status_message", "Unknown error")
            logger.error("[dataforseo] API error: %s", error_msg)
            raise RuntimeError(f"DataForSEO API error: {error_msg}")
        
        # Parse results
        results = []
        tasks = data.get("tasks", [])
        if tasks and tasks[0].get("result"):
            for item in tasks[0]["result"]:
                results.append({
                    "keyword": item.get("keyword", ""),
                    "search_volume": item.get("search_volume", 0),
                    "competition": item.get("competition", 0),
                    "cpc": item.get("cpc", 0),
                    "trend": item.get("monthly_searches", []),
                })
        
        logger.info(
            "[dataforseo] Retrieved data for %d keywords (location=%s)",
            len(results),
            location_code,
        )

        return {
            "keywords": results,
            "location": _get_location_name(location_code),
            "language": language_code,
        }
        
    except httpx.HTTPError as e:
        logger.error("[dataforseo] HTTP error: %s", str(e))
        raise RuntimeError(f"Failed to fetch keyword data: {str(e)}")
    except Exception as e:
        logger.error("[dataforseo] Unexpected error: %s", str(e))
        raise


async def get_keyword_suggestions(
    seed_keyword: str,
    location_code: Optional[int] = None,
    language_code: str = "en",
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Get keyword suggestions and related keywords for a seed keyword.

    Args:
        seed_keyword: Base keyword to get suggestions for
        location_code: DataForSEO location code. None = global/worldwide data.
        language_code: Language code
        limit: Max number of suggestions to return

    Returns:
        {
            "seed_keyword": str,
            "suggestions": [
                {
                    "keyword": str,
                    "search_volume": int,
                    "competition": float,
                    "cpc": float,
                }
            ]
        }
    """
    url = "https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live"

    task: Dict[str, Any] = {
        "keywords": [seed_keyword],
        "language_code": language_code,
        "include_seed_keyword": True,
        "include_serp_info": False,
        "limit": limit,
    }
    if location_code is not None:
        task["location_code"] = location_code
    payload = [task]
    
    headers = {
        "Authorization": _get_auth_header(),
        "Content-Type": "application/json",
    }
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        if data.get("status_code") != 20000:
            error_msg = data.get("status_message", "Unknown error")
            raise RuntimeError(f"DataForSEO API error: {error_msg}")
        
        # Parse results
        suggestions = []
        tasks = data.get("tasks", [])
        if tasks and tasks[0].get("result"):
            for item in tasks[0]["result"]:
                suggestions.append({
                    "keyword": item.get("keyword", ""),
                    "search_volume": item.get("search_volume", 0),
                    "competition": item.get("competition", 0),
                    "cpc": item.get("cpc", 0),
                })
        
        logger.info(
            "[dataforseo] Retrieved %d suggestions for '%s'",
            len(suggestions),
            seed_keyword,
        )
        
        return {
            "seed_keyword": seed_keyword,
            "suggestions": suggestions,
        }
        
    except Exception as e:
        logger.error("[dataforseo] Failed to get suggestions: %s", str(e))
        raise


def _get_location_name(location_code: Optional[int]) -> str:
    """Map location code to human-readable name."""
    if location_code is None:
        return "Global"
    locations = {
        # Africa
        2404: "Kenya", 2566: "Nigeria", 2710: "South Africa", 2834: "Tanzania",
        2800: "Uganda", 2288: "Ghana", 2818: "Egypt", 2504: "Morocco",
        2012: "Algeria", 2788: "Tunisia", 2706: "Senegal", 2508: "Mozambique",
        2716: "Zimbabwe", 2024: "Angola", 2454: "Malawi", 2646: "Rwanda",
        2887: "Yemen", 2760: "Sudan", 2686: "Somalia",
        # Americas
        2840: "United States", 2124: "Canada", 2484: "Mexico", 2076: "Brazil",
        2032: "Argentina", 2152: "Chile", 2170: "Colombia", 2604: "Peru",
        2858: "Uruguay", 2862: "Venezuela", 2218: "Ecuador", 2068: "Bolivia",
        2600: "Paraguay", 2630: "Puerto Rico",
        # Europe
        2826: "United Kingdom", 2276: "Germany", 2250: "France", 2380: "Italy",
        2724: "Spain", 2528: "Netherlands", 2056: "Belgium", 2756: "Switzerland",
        2040: "Austria", 2752: "Sweden", 2578: "Norway", 2208: "Denmark",
        2246: "Finland", 2616: "Poland", 2203: "Czech Republic", 2348: "Hungary",
        2642: "Romania", 2100: "Bulgaria", 2300: "Greece", 2620: "Portugal",
        2191: "Croatia", 2703: "Slovakia", 2705: "Slovenia", 2372: "Ireland",
        2233: "Estonia", 2428: "Latvia", 2440: "Lithuania",
        # Asia-Pacific
        2036: "Australia", 2554: "New Zealand", 2356: "India", 2586: "Pakistan",
        2050: "Bangladesh", 2144: "Sri Lanka", 2524: "Nepal",
        2458: "Malaysia", 2764: "Thailand", 2608: "Philippines", 2360: "Indonesia",
        2704: "Vietnam", 2116: "Cambodia", 2104: "Myanmar", 2418: "Laos",
        2702: "Singapore", 2158: "Taiwan", 2410: "South Korea", 2392: "Japan",
        2344: "Hong Kong", 2446: "Macao",
        # Middle East
        2784: "United Arab Emirates", 2682: "Saudi Arabia", 2634: "Qatar",
        2414: "Kuwait", 2048: "Bahrain", 2512: "Oman", 2376: "Israel",
        2400: "Jordan", 2422: "Lebanon", 2368: "Iraq", 2364: "Iran",
    }
    return locations.get(location_code, f"Location {location_code}")


# Location codes for common countries/regions — used by get_location_code()
LOCATION_CODES: Dict[str, int] = {
    # Africa
    "kenya": 2404, "nigeria": 2566, "south africa": 2710, "tanzania": 2834,
    "uganda": 2800, "ghana": 2288, "egypt": 2818, "morocco": 2504,
    "algeria": 2012, "tunisia": 2788, "senegal": 2706, "mozambique": 2508,
    "zimbabwe": 2716, "angola": 2024, "malawi": 2454, "rwanda": 2646,
    "ethiopia": 2887, "sudan": 2760,
    # Americas
    "usa": 2840, "us": 2840, "united states": 2840,
    "canada": 2124,
    "mexico": 2484,
    "brazil": 2076,
    "argentina": 2032, "chile": 2152, "colombia": 2170, "peru": 2604,
    "uruguay": 2858, "venezuela": 2862, "ecuador": 2218, "bolivia": 2068,
    "paraguay": 2600, "puerto rico": 2630,
    # Europe
    "uk": 2826, "united kingdom": 2826, "britain": 2826, "england": 2826,
    "germany": 2276, "france": 2250, "italy": 2380, "spain": 2724,
    "netherlands": 2528, "holland": 2528, "belgium": 2056,
    "switzerland": 2756, "austria": 2040, "sweden": 2752, "norway": 2578,
    "denmark": 2208, "finland": 2246, "poland": 2616, "czech republic": 2203,
    "czechia": 2203, "hungary": 2348, "romania": 2642, "bulgaria": 2100,
    "greece": 2300, "portugal": 2620, "croatia": 2191, "slovakia": 2703,
    "slovenia": 2705, "ireland": 2372, "estonia": 2233, "latvia": 2428,
    "lithuania": 2440,
    # Asia-Pacific
    "australia": 2036, "new zealand": 2554,
    "india": 2356, "pakistan": 2586, "bangladesh": 2050, "sri lanka": 2144,
    "nepal": 2524,
    "malaysia": 2458, "thailand": 2764, "philippines": 2608, "indonesia": 2360,
    "vietnam": 2704, "cambodia": 2116, "myanmar": 2104, "laos": 2418,
    "singapore": 2702, "taiwan": 2158, "south korea": 2410, "korea": 2410,
    "japan": 2392, "hong kong": 2344,
    # Middle East
    "uae": 2784, "united arab emirates": 2784, "dubai": 2784,
    "saudi arabia": 2682, "ksa": 2682,
    "qatar": 2634, "kuwait": 2414, "bahrain": 2048, "oman": 2512,
    "israel": 2376, "jordan": 2400, "lebanon": 2422, "iraq": 2368,
}


def get_location_code(location: str) -> Optional[int]:
    """
    Convert a location name/city/country to a DataForSEO location code.
    Returns None (global data) for unrecognised locations rather than defaulting to any country.
    """
    if not location:
        return None
    location_lower = location.lower().strip()
    # Direct match
    if location_lower in LOCATION_CODES:
        return LOCATION_CODES[location_lower]
    # Substring match — e.g. "Nairobi, Kenya" → Kenya
    for key, code in LOCATION_CODES.items():
        if key in location_lower:
            return code
    return None  # Unknown location → global data
