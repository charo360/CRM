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
import httpx

logger = logging.getLogger(__name__)


class ProductOrganizer:
    """AI-powered product organization using OpenAI Vision"""
    
    def __init__(self, api_key: str = None):
        """Initialize with OpenAI API key"""
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        
        if self.api_key and self.api_key != 'your_openai_api_key_here':
            try:
                self.client = OpenAI(api_key=self.api_key)
                self.model_name = 'gpt-4o-mini'
                self.vision_available = True
                logger.info("OpenAI client initialized for product organization")
            except Exception as e:
                logger.error(f"Failed to configure OpenAI client: {e}")
                self.vision_available = False
        else:
            self.vision_available = False
            logger.warning("OpenAI API key not configured - using fallback mode")
    
    async def analyze_product_image(self, image_path: str) -> Dict[str, any]:
        """
        Analyze a product image and extract information
        
        Args:
            image_path: Path to product image
            
        Returns:
            Dict with suggested name, category, description, price (if visible)
        """
        if not self.vision_available:
            return self._fallback_analysis(image_path)
        
        try:
            # A product image can be local during development or a public image
            # URL after it has been stored in cloud storage.
            if image_path.startswith(("https://", "http://")):
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                    image_response = await client.get(image_path)
                    image_response.raise_for_status()
                img = Image.open(io.BytesIO(image_response.content))
            else:
                img = Image.open(image_path)
            
            # Convert image to base64 for OpenAI Vision API
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            # Create prompt for OpenAI Vision
            prompt = """Analyze this product image and provide the following information in a structured format:

1. Product Name: What is this product? Be specific (brand, model if visible)
2. Category: Choose ONE from: Electronics, Clothing, Food & Beverages, Beauty & Health, Home & Garden, Sports & Fitness, Books & Media, Toys & Games, Automotive, Other
3. Description: Brief 1-2 sentence description
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
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{img_base64}"
                                }
                            }
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
            "description": "Add product description",
            "suggested_price": None,
            "confidence": 0.3
        }
    
    async def analyze_multiple_images(self, image_paths: List[str]) -> List[Dict[str, any]]:
        """
        Analyze multiple product images
        
        Args:
            image_paths: List of image paths
            
        Returns:
            List of analysis results
        """
        results = []
        
        for image_path in image_paths:
            try:
                result = await self.analyze_product_image(image_path)
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
