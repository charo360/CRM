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

async def find_product_matches_ai(query: str, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    AI-powered semantic product matching. Understands that 'shoes' matches 'sneakers',
    'phone' matches 'iPhone', etc. without hardcoded lists. Works for ANY product category.
    """
    if not products:
        return []
    
    try:
        from ai_service import get_drafter
        ai = get_drafter()
        
        # Build compact product list for AI
        product_list = []
        for i, p in enumerate(products[:50]):  # Limit to 50 to save tokens
            product_list.append(f"{i}. {p.get('name', '')} - {p.get('category', '')} - {(p.get('description', '') or '')[:60]}")
        
        prompt = f"""Customer query: "{query}"

Products available:
{chr(10).join(product_list)}

Return ONLY the numbers (comma-separated) of products that match the customer's query.
Use semantic understanding: "shoes" matches sneakers/heels/boots, "phone" matches iPhone/Samsung, etc.
If NO products match, return "NONE".
Examples:
- Query "shoes" → "0,5,12" (if those are footwear)
- Query "laptop" → "3" (if that's a computer)
- Query "red dress" → "NONE" (if no red dresses exist)

Numbers only:"""
        
        response = await ai._call_llm(prompt, model_pref="standard")
        response = response.strip().upper()
        
        if response == "NONE" or not response:
            return []
        
        # Parse AI response
        matched_indices = []
        for part in response.replace(" ", "").split(","):
            try:
                idx = int(part)
                if 0 <= idx < len(products[:50]):
                    matched_indices.append(idx)
            except ValueError:
                continue
        
        return [products[i] for i in matched_indices]
    
    except Exception as e:
        import logging
        logging.error(f"[AI Product Match] Error: {e}, falling back to keyword search")
        # Fallback to keyword search if AI fails
        return find_product_matches(query, products)


def find_product_matches(query: str, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fallback keyword-based product matching. Used when AI matching fails or for simple exact matches.
    """
    body_lower = query.lower()
    matched_products = []
    
    # 1. EXACT / SUBSTRING MATCH on name
    for p in products:
        if p.get("name", "").lower() in body_lower:
            matched_products.append(p)
    
    # 2. Keyword search across name + description + category
    if not matched_products and len(body_lower) > 2:
        keywords = body_lower.split()
        stop_words = {
            "want", "need", "price", "how", "much", "is", "the", "a", "an",
            "send", "pic", "picture", "image", "photo", "show", "me", "all",
            "to", "in", "of", "for", "with", "at", "on", "and", "or", "do",
            "you", "have", "any", "can", "i", "get", "please", "this", "that",
            "what", "your", "some", "like", "about", "got",
        }
        keywords = [k for k in keywords if k not in stop_words and len(k) > 2]
        
        candidates = []
        if keywords:
            for p in products:
                # Build searchable text from name + description + category
                p_name_lower = p.get("name", "").lower()
                p_desc_lower = (p.get("description", "") or "").lower()
                p_cat_lower = (p.get("category", "") or "").lower()
                searchable = f"{p_name_lower} {p_desc_lower} {p_cat_lower}"
                
                match_score = 0
                
                for k in keywords:
                    # Exact keyword match (in name = 3 points, desc/cat = 1 point)
                    if k in p_name_lower:
                        match_score += 3
                        continue
                    if k in searchable:
                        match_score += 1
                        continue
                    
                    # Plural/Suffix checks
                    base_forms = []
                    if k.endswith('ies'): base_forms.append(k[:-3] + 'y')
                    if k.endswith('es'): base_forms.append(k[:-2])
                    if k.endswith('s'): base_forms.append(k[:-1])
                    
                    for base in base_forms:
                        if len(base) > 2 and base in searchable:
                            match_score += 2 if base in p_name_lower else 1
                            break
                    
                    # Fuzzy match — use difflib for close matches on product name words
                    if match_score == 0:
                        p_words = p_name_lower.split()
                        close = difflib.get_close_matches(k, p_words, n=1, cutoff=0.75)
                        if close:
                            match_score += 1
                
                if match_score > 0:
                    candidates.append((match_score, p))
                    
            # Sort by match score (descending)
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
