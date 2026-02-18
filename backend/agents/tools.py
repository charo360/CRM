from typing import List, Dict, Any, Optional
import difflib
import os

# Reusing the robust normalization helper
def normalize_url(u: str) -> Optional[str]:
    """Normalize media URLs for Docker/local access."""
    if not u:
        return u
    if u.startswith('/'):
        base = os.environ.get('PUBLIC_BASE_URL') or os.environ.get('WEBHOOK_BASE_URL') or 'http://host.docker.internal:8000'
        return f"{base.rstrip('/')}{u}"
    if u.startswith('http://localhost:'):
        return u.replace('http://localhost:', 'http://host.docker.internal:')
    if u.startswith('http://127.0.0.1:'):
        return u.replace('http://127.0.0.1:', 'http://host.docker.internal:')
    return u

def find_product_matches(query: str, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Find products matching the user's query using exact, plural, and fuzzy logic.
    Returns a list of matching product objects.
    """
    body_lower = query.lower()
    matched_products = []
    
    # 1. EXACT / SUBSTRING MATCH (Product Name contains Query or Query contains Product Name)
    # A. Product name in query? (e.g. user says "I want Red Dress")
    for p in products:
        if p.get("name", "").lower() in body_lower:
            matched_products.append(p)
            
    # B. Query in product name? (e.g. user says "dresses" -> matches "Red Dress")
    # Only if we haven't found exact matches yet? Or maybe allow both?
    # Let's collect candidates based on keywords.
    
    if not matched_products and len(body_lower) > 2:
        keywords = body_lower.split()
        stop_words = {"want", "need", "price", "how", "much", "is", "the", "a", "an", "send", "pic", "picture", "image", "photo", "show", "me", "all", "to", "in", "of", "for", "with", "at", "on", "and", "or"}
        keywords = [k for k in keywords if k not in stop_words and len(k) > 2]
        
        candidates = []
        if keywords:
            for p in products:
                p_name_lower = p.get("name", "").lower()
                match_count = 0
                
                for k in keywords:
                    # 1. Exact keyword match
                    if k in p_name_lower:
                        match_count += 1
                        continue
                    
                    # 2. Plural/Suffix checks
                    base_forms = []
                    if k.endswith('ies'): base_forms.append(k[:-3] + 'y')
                    if k.endswith('es'): base_forms.append(k[:-2])
                    if k.endswith('s'): base_forms.append(k[:-1])
                    if k == 'dresses': base_forms.append('dress') # redundancy safety
                    
                    found_variant = False
                    for base in base_forms:
                        if len(base) > 2 and base in p_name_lower:
                            match_count += 1
                            found_variant = True
                            break
                
                if match_count > 0:
                    candidates.append((match_count, p))
                    
            # Sort by match count (descending)
            candidates.sort(key=lambda x: x[0], reverse=True)
            matched_products = [c[1] for c in candidates]

    # Deduplicate by _id while preserving order
    unique_products = []
    seen_ids = set()
    for p in matched_products:
        pid = str(p["_id"])
        if pid not in seen_ids:
            unique_products.append(p)
            seen_ids.add(pid)
            
    return unique_products

def format_product_catalog(products: List[Dict[str, Any]], currency: str = "USD") -> str:
    """Attributes to string catalog."""
    lines = []
    for p in products:
        price = f"{currency} {p.get('price', 0):,.0f}" if p.get('price') is not None else "N/A"
        stock = "IN STOCK" if p.get("in_stock", True) else "OUT OF STOCK"
        lines.append(f"• {p['name']} - {price} [{stock}]")
    return "\n".join(lines)
