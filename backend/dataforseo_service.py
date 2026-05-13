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


def _get_credentials() -> tuple[str, str]:
    """Get DataForSEO API credentials from environment."""
    login = os.getenv("DATAFORSEO_LOGIN", "")
    password = os.getenv("DATAFORSEO_PASSWORD", "")
    if not login or not password:
        raise ValueError("DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD must be set")
    return login, password


def _get_auth_header() -> str:
    """Generate Basic Auth header for DataForSEO API."""
    login, password = _get_credentials()
    credentials = f"{login}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


async def get_keyword_data(
    keywords: List[str],
    location_code: int = 2404,  # Default: Kenya
    language_code: str = "en",
) -> Dict[str, Any]:
    """
    Get search volume and metrics for a list of keywords.
    
    Args:
        keywords: List of keywords to research (max 1000 per request)
        location_code: DataForSEO location code (2404=Kenya, 2840=USA, 2826=UK)
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
    
    payload = [{
        "keywords": keywords,
        "location_code": location_code,
        "language_code": language_code,
    }]
    
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
            "[dataforseo] Retrieved data for %d keywords (location=%d)",
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
    location_code: int = 2404,
    language_code: str = "en",
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Get keyword suggestions and related keywords for a seed keyword.
    
    Args:
        seed_keyword: Base keyword to get suggestions for
        location_code: DataForSEO location code
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
    
    payload = [{
        "keywords": [seed_keyword],
        "location_code": location_code,
        "language_code": language_code,
        "include_seed_keyword": True,
        "include_serp_info": False,
        "limit": limit,
    }]
    
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


def _get_location_name(location_code: int) -> str:
    """Map location code to human-readable name."""
    locations = {
        2404: "Kenya",
        2840: "United States",
        2826: "United Kingdom",
        2036: "Australia",
        2124: "Canada",
        2356: "India",
        2710: "South Africa",
        2566: "Nigeria",
        2834: "Tanzania",
        2800: "Uganda",
    }
    return locations.get(location_code, f"Location {location_code}")


# Location code reference for common countries
LOCATION_CODES = {
    "kenya": 2404,
    "usa": 2840,
    "us": 2840,
    "united states": 2840,
    "uk": 2826,
    "united kingdom": 2826,
    "australia": 2036,
    "canada": 2124,
    "india": 2356,
    "south africa": 2710,
    "nigeria": 2566,
    "tanzania": 2834,
    "uganda": 2800,
}


def get_location_code(location: str) -> int:
    """Convert location name to DataForSEO location code."""
    location_lower = location.lower().strip()
    return LOCATION_CODES.get(location_lower, 2404)  # Default to Kenya
