import re
from typing import Dict, Any, List

class BusinessContextDetector:
    """
    Classifies the intent of a message and extracts relevant business entities.
    Intents:
    - personal: Casual chat, greetings, non-business interaction
    - business_b2c: Standard customer inquiries (price, stock, delivery, ordering)
    - business_b2b: Wholesale, bulk orders, partnership, supply
    
    Entities:
    - products: potential product names
    - quantity: number of items requested
    """

    def __init__(self):
        self.b2b_keywords = [
            r'\b(bulk|wholesale|supply|supplier|distributor|partnership|collab|resell|stockist|catalogue|quote|invoice)\b',
            r'\b(qty|quantity|units|pieces|pcs)\s*>\s*10', # Implicit bulk
            r'\b(moq|minimum order)\b'
        ]

        self.b2c_keywords = [
            r'\b(price|cost|how much|buy|order|need|want|get|have|stock|available|deliver|shipping|location|pay|mpesa)\b',
            r'\b(sending|sent|receipt|payment)\b'
        ]
        
        # Product detection helper (can be refined with actual catalog)
        self.product_indicator = r'\b(shirt|pant|shoe|dress|top|jeans|jacket|suit|kikoy|leso|laptop|phone|computer|screen)\b'

    def detect(self, message: str) -> Dict[str, Any]:
        if not message:
            return {'intent': 'personal', 'entities': {}}
            
        text = message.lower()
        
        # 1. Detect Intent
        intent = 'personal'
        confidence = 0.5
        
        # Check B2B first (more specific)
        b2b_score = sum(len(re.findall(p, text)) for p in self.b2b_keywords)
        if b2b_score > 0:
            intent = 'business_b2b'
            confidence = 0.8
        else:
            # Check B2C
            b2c_score = sum(len(re.findall(p, text)) for p in self.b2c_keywords)
            if b2c_score > 0:
                intent = 'business_b2c'
                confidence = 0.7
            
            # If message is very short and has no business keywords, assume personal
            if len(text.split()) < 4 and b2c_score == 0:
                intent = 'personal'
                confidence = 0.9

        # 2. Extract Entities
        entities = self._extract_entities(text)

        return {
            'intent': intent,
            'confidence': confidence,
            'entities': entities
        }

    def _extract_entities(self, text: str) -> Dict[str, Any]:
        """
        Extracts potential products and quantities.
        """
        entities = {
            'products': [],
            'quantity': None
        }
        
        # Simple quantity extraction (e.g., "5 pieces", "2 shirts")
        qty_match = re.search(r'\b(\d+)\s*(pcs|pieces|units|pairs)?\b', text)
        if qty_match:
            entities['quantity'] = int(qty_match.group(1))
            
        # Potentially matching product keywords from a known list
        # In a real scenario, this would check against the CentralizedKnowledgeBase
        product_matches = re.findall(self.product_indicator, text)
        if product_matches:
            entities['products'] = list(set(product_matches))
            
        return entities
