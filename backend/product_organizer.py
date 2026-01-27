"""
AI Product Organizer
Uses Gemini Vision API to analyze product images and suggest names/categories
"""
import google.generativeai as genai
import os
from typing import Dict, List
import logging
from PIL import Image
import io

logger = logging.getLogger(__name__)


class ProductOrganizer:
    """AI-powered product organization using Gemini Vision"""
    
    def __init__(self, api_key: str = None):
        """Initialize with Gemini API key"""
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        
        if self.api_key and self.api_key != 'your_gemini_api_key_here':
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            self.vision_available = True
        else:
            self.vision_available = False
            logger.warning("Gemini API key not configured - using fallback mode")
    
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
            # Load image
            img = Image.open(image_path)
            
            # Create prompt for Gemini
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

            # Generate response
            response = self.model.generate_content([prompt, img])
            
            # Parse response
            result = self._parse_gemini_response(response.text)
            
            logger.info(f"AI analysis complete: {result.get('name', 'Unknown')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing image with AI: {e}")
            return self._fallback_analysis(image_path)
    
    def _parse_gemini_response(self, response_text: str) -> Dict[str, any]:
        """Parse Gemini's structured response"""
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
            logger.error(f"Error parsing Gemini response: {e}")
        
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
