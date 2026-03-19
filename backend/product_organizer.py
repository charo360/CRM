"""
AI Product Organizer
Uses OpenAI Vision API to analyze product images and suggest names/categories
"""
from openai import OpenAI
import os
from typing import Dict, List
import logging
from PIL import Image
import io
import base64

logger = logging.getLogger(__name__)


class ProductOrganizer:
    """AI-powered product organization using OpenAI Vision"""
    
    def __init__(self, api_key: str = None):
        """Initialize with OpenAI API key — always uses OpenAI for Vision regardless of AI_PROVIDER"""
        # Try provided key, then env var, then load directly from .env file
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        
        if not self.api_key:
            # Load directly from .env since start_server.ps1 may clear the env var
            try:
                from dotenv import dotenv_values
                env_vals = dotenv_values(os.path.join(os.path.dirname(__file__), '.env'))
                self.api_key = env_vals.get('OPENAI_API_KEY', '')
            except Exception:
                pass
        
        if self.api_key and self.api_key not in ('your_openai_api_key_here', ''):
            try:
                self.client = OpenAI(api_key=self.api_key)
                self.model_name = 'gpt-4o-mini'
                self.vision_available = True
                logger.info(f"OpenAI Vision client initialized for product analysis (key ends: ...{self.api_key[-6:]})")
            except Exception as e:
                logger.error(f"Failed to configure OpenAI client: {e}")
                self.vision_available = False
        else:
            self.vision_available = False
            logger.warning("OpenAI API key not configured - product image analysis will use fallback mode")
    
    async def analyze_product_image(self, image_path: str, business_context: str = None) -> Dict[str, any]:
        """
        Analyze a product image and extract information
        
        Args:
            image_path: Path to product image
            business_context: Optional context about the business (e.g. "Fashion store", "Electronics shop")
            
        Returns:
            Dict with suggested name, category, description, price (if visible)
        """
        if not self.vision_available:
            return self._fallback_analysis(image_path)
        
        try:
            # Determine image source: URL or local file
            if image_path.startswith("http://") or image_path.startswith("https://"):
                image_content = {"type": "image_url", "image_url": {"url": image_path}}
            else:
                # Load local image and convert to base64
                img = Image.open(image_path)
                buffered = io.BytesIO()
                img.save(buffered, format="PNG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                image_content = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
            
            # Create prompt for OpenAI Vision
            context_snippet = f"\nBusiness Context: {business_context}\n" if business_context else ""
            prompt = f"""Analyze this product image and provide the following information in a structured format.{context_snippet}

CRITICAL INSTRUCTIONS:
- FOCUS ON THE PRODUCT ITEM(S) ONLY. 
- If a person or model is wearing the product, IGNORE the person. Do NOT describe the person's pose, appearance, or actions (e.g., "person taking a selfie", "man smiling").
- Instead, describe the garment or object (e.g., "White cotton T-shirt", "Sleek matte headphones").
- Use the Business Context above to guide your identification and terminology.

FIELDS TO EXTRACT:
1. Product Name: What is this product? Be specific (brand, model if visible)
2. Category: Choose ONE from: Electronics, Clothing, Food & Beverages, Beauty & Health, Home & Garden, Sports & Fitness, Books & Media, Toys & Games, Automotive, Other
3. Description: Brief 1-2 sentence description focusing ONLY on features/styling of the item.
4. Visible Price: If you can see a price tag or price in the image, extract it. Otherwise say "Not visible"
5. Confidence: How confident are you in this analysis? (High/Medium/Low)

Format your response EXACTLY like this:
NAME: [product name]
CATEGORY: [category]
DESCRIPTION: [description]
PRICE: [price or "Not visible"]
CONFIDENCE: [High/Medium/Low]"""

            # Generate response using OpenAI Vision API
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            image_content
                        ]
                    }
                ],
                max_tokens=500
            )
            
            # Parse response
            result = self._parse_openai_response(response.choices[0].message.content)
            
            logger.info(f"AI analysis complete: {result.get('name', 'Unknown')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing image with AI: {e}")
            return self._fallback_analysis(image_path)
    
    def _parse_openai_response(self, response_text: str) -> Dict[str, any]:
        """Parse OpenAI's structured response"""
        result = {
            "name": "Product",
            "category": "Other",
            "description": "",
            "suggested_price": None,
            "confidence": 0.5
        }
        
        try:
            lines = response_text.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                
                if line.startswith('NAME:'):
                    result['name'] = line.replace('NAME:', '').strip()
                
                elif line.startswith('CATEGORY:'):
                    result['category'] = line.replace('CATEGORY:', '').strip()
                
                elif line.startswith('DESCRIPTION:'):
                    result['description'] = line.replace('DESCRIPTION:', '').strip()
                
                elif line.startswith('PRICE:'):
                    price_str = line.replace('PRICE:', '').strip()
                    if price_str.lower() != 'not visible':
                        # Try to extract numeric price
                        import re
                        numbers = re.findall(r'\d+(?:,\d{3})*(?:\.\d{2})?', price_str)
                        if numbers:
                            result['suggested_price'] = float(numbers[0].replace(',', ''))
                
                elif line.startswith('CONFIDENCE:'):
                    conf_str = line.replace('CONFIDENCE:', '').strip().lower()
                    if conf_str == 'high':
                        result['confidence'] = 0.9
                    elif conf_str == 'medium':
                        result['confidence'] = 0.7
                    else:
                        result['confidence'] = 0.5
            
        except Exception as e:
            logger.error(f"Error parsing OpenAI response: {e}")
        
        return result
    
    def _fallback_analysis(self, image_path: str) -> Dict[str, any]:
        """Fallback when AI is not available"""
        from pathlib import Path
        filename = Path(image_path).stem
        
        return {
            "name": f"Product {filename[:8]}",
            "category": "Other",
            "description": "",
            "suggested_price": None,
            "confidence": 0.3
        }
    
    async def analyze_multiple_images(self, image_paths: List[str], business_context: str = None) -> List[Dict[str, any]]:
        """
        Analyze multiple product images
        
        Args:
            image_paths: List of image paths
            business_context: Optional context about the business
            
        Returns:
            List of analysis results
        """
        results = []
        
        for image_path in image_paths:
            try:
                result = await self.analyze_product_image(image_path, business_context)
                result['image_path'] = image_path
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to analyze {image_path}: {e}")
                results.append({
                    "error": str(e),
                    "image_path": image_path
                })
        
        return results


# Singleton instance
_organizer_instance = None

def get_organizer() -> ProductOrganizer:
    """Get singleton ProductOrganizer instance"""
    global _organizer_instance
    if _organizer_instance is None:
        _organizer_instance = ProductOrganizer()
    return _organizer_instance
