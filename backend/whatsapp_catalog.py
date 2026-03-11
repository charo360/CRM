"""
WhatsApp Catalog Service - Interactive product displays with buttons and lists
Handles rich product presentations via Evolution API
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class WhatsAppCatalog:
    """Service for sending interactive product messages via WhatsApp"""
    
    def __init__(self, evolution_url: str, instance: str):
        self.evolution_url = evolution_url
        self.instance = instance
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def send_product_with_buttons(
        self,
        phone: str,
        product: Dict[str, Any],
        include_share: bool = True
    ) -> Dict[str, Any]:
        """
        Send a single product with interactive buttons
        
        Args:
            phone: Customer phone number
            product: Product dict with name, price, description, stock, etc.
            include_share: Whether to include a share button
        
        Returns:
            Response from Evolution API
        """
        try:
            # Format price
            price = product.get('price', 0)
            currency = product.get('currency', 'KES')
            price_str = f"{currency} {price:,.0f}" if price else "Price on request"
            
            # Build description
            description_parts = [f"💰 {price_str}"]
            
            if product.get('description'):
                description_parts.append(f"\n{product['description'][:200]}")
            
            stock = product.get('stock')
            if stock is not None:
                in_stock = product.get('in_stock', True)
                if in_stock and stock > 0:
                    description_parts.append(f"\n📦 Stock: {stock} available")
                elif not in_stock or stock == 0:
                    description_parts.append("\n⚠️ Out of stock")
            
            # Build buttons
            buttons = []
            product_id = str(product.get('_id', product.get('id', '')))
            
            # Only add order button if in stock
            if product.get('in_stock', True) and (stock is None or stock > 0):
                buttons.append({
                    "type": "reply",
                    "displayText": "🛒 Order Now",
                    "id": f"order_{product_id}"
                })
            
            buttons.append({
                "type": "reply",
                "displayText": "📋 More Info",
                "id": f"details_{product_id}"
            })
            
            if include_share:
                buttons.append({
                    "type": "reply",
                    "displayText": "📱 Share",
                    "id": f"share_{product_id}"
                })
            
            payload = {
                "number": phone,
                "options": {
                    "delay": 1200,
                    "presence": "composing"
                },
                "buttonMessage": {
                    "title": f"✨ {product['name']}",
                    "description": "".join(description_parts),
                    "footerText": "Tap a button below",
                    "buttons": buttons[:3]  # WhatsApp max 3 buttons
                }
            }
            
            response = await self.http_client.post(
                f"{self.evolution_url}/message/sendButtons/{self.instance}",
                json=payload
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Error sending product buttons: {e}")
            raise
    
    async def send_product_list(
        self,
        phone: str,
        title: str,
        products: List[Dict[str, Any]],
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send multiple products as an interactive list
        
        Args:
            phone: Customer phone number
            title: List title (e.g., "Our Products")
            products: List of product dicts
            category: Optional category name for section title
        
        Returns:
            Response from Evolution API
        """
        try:
            # Build product rows
            rows = []
            for product in products[:10]:  # WhatsApp max 10 items per section
                product_id = str(product.get('_id', product.get('id', '')))
                price = product.get('price', 0)
                currency = product.get('currency', 'KES')
                price_str = f"{currency} {price:,.0f}" if price else "POA"
                
                description = product.get('description', '')[:72]  # WhatsApp limit
                in_stock = product.get('in_stock', True)
                stock_emoji = "✅" if in_stock else "❌"
                
                rows.append({
                    "title": product['name'][:24],  # WhatsApp limit
                    "description": f"{stock_emoji} {price_str} - {description}",
                    "rowId": f"select_{product_id}"
                })
            
            payload = {
                "number": phone,
                "options": {
                    "delay": 1200
                },
                "listMessage": {
                    "title": f"🛍️ {title}",
                    "description": f"Browse {len(rows)} product{'s' if len(rows) > 1 else ''}. Tap to view details:",
                    "buttonText": "View Products",
                    "footerText": "Swipe up to see all items",
                    "sections": [
                        {
                            "title": category or "Products",
                            "rows": rows
                        }
                    ]
                }
            }
            
            response = await self.http_client.post(
                f"{self.evolution_url}/message/sendList/{self.instance}",
                json=payload
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Error sending product list: {e}")
            raise
    
    async def send_product_showcase(
        self,
        phone: str,
        product: Dict[str, Any],
        send_buttons: bool = True
    ) -> Dict[str, Any]:
        """
        Send product with image and rich caption, optionally followed by buttons
        
        Args:
            phone: Customer phone number
            product: Product dict with image_url, name, price, etc.
            send_buttons: Whether to send follow-up buttons
        
        Returns:
            Response from Evolution API
        """
        try:
            # Get product image
            images = product.get('images', [])
            image_url = product.get('image_url')
            
            # Use first image from array or fallback to image_url
            if images and len(images) > 0:
                media_url = images[0]
            elif image_url:
                media_url = image_url
            else:
                media_url = None
            
            # Format caption
            price = product.get('price', 0)
            currency = product.get('currency', 'KES')
            price_str = f"{currency} {price:,.0f}" if price else "Price on request"
            
            stock = product.get('stock')
            in_stock = product.get('in_stock', True)
            
            caption_parts = [
                f"🌟 *{product['name']}*\n",
                f"💰 Price: {price_str}"
            ]
            
            if stock is not None and in_stock:
                caption_parts.append(f"📦 Stock: {stock} available")
            elif not in_stock or stock == 0:
                caption_parts.append("⚠️ Currently out of stock")
            
            if product.get('description'):
                caption_parts.append(f"\n{product['description']}")
            
            caption = "\n".join(caption_parts)
            
            # Send media message if image available
            if media_url:
                media_payload = {
                    "number": phone,
                    "options": {
                        "delay": 1200,
                        "presence": "composing"
                    },
                    "mediaMessage": {
                        "mediatype": "image",
                        "media": media_url,
                        "caption": caption
                    }
                }
                
                response = await self.http_client.post(
                    f"{self.evolution_url}/message/sendMedia/{self.instance}",
                    json=media_payload
                )
                response.raise_for_status()
            else:
                # No image, send as text
                text_payload = {
                    "number": phone,
                    "options": {
                        "delay": 1200
                    },
                    "textMessage": {
                        "text": caption
                    }
                }
                
                response = await self.http_client.post(
                    f"{self.evolution_url}/message/sendText/{self.instance}",
                    json=text_payload
                )
                response.raise_for_status()
            
            # Send follow-up buttons if requested
            if send_buttons and in_stock and (stock is None or stock > 0):
                await asyncio.sleep(1)
                
                product_id = str(product.get('_id', product.get('id', '')))
                button_payload = {
                    "number": phone,
                    "options": {
                        "delay": 500
                    },
                    "buttonMessage": {
                        "title": "What would you like to do?",
                        "buttons": [
                            {
                                "type": "reply",
                                "displayText": "🛒 Order Now",
                                "id": f"order_{product_id}"
                            },
                            {
                                "type": "reply",
                                "displayText": "💬 Ask Question",
                                "id": f"ask_{product_id}"
                            },
                            {
                                "type": "reply",
                                "displayText": "📱 Share",
                                "id": f"share_{product_id}"
                            }
                        ]
                    }
                }
                
                await self.http_client.post(
                    f"{self.evolution_url}/message/sendButtons/{self.instance}",
                    json=button_payload
                )
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error sending product showcase: {e}")
            raise
    
    async def send_product_carousel(
        self,
        phone: str,
        products: List[Dict[str, Any]],
        max_items: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Send multiple product images in sequence (carousel effect)
        
        Args:
            phone: Customer phone number
            products: List of product dicts with images
            max_items: Maximum number of products to show (default 3)
        
        Returns:
            List of responses from Evolution API
        """
        try:
            responses = []
            products_to_send = products[:max_items]
            
            for i, product in enumerate(products_to_send):
                images = product.get('images', [])
                image_url = product.get('image_url')
                
                media_url = None
                if images and len(images) > 0:
                    media_url = images[0]
                elif image_url:
                    media_url = image_url
                
                if not media_url:
                    continue
                
                price = product.get('price', 0)
                currency = product.get('currency', 'KES')
                price_str = f"{currency} {price:,.0f}" if price else "POA"
                
                caption = f"{i+1}. {product['name']} - {price_str}"
                
                payload = {
                    "number": phone,
                    "options": {
                        "delay": 2000 * i,
                        "presence": "composing"
                    },
                    "mediaMessage": {
                        "mediatype": "image",
                        "media": media_url,
                        "caption": caption
                    }
                }
                
                response = await self.http_client.post(
                    f"{self.evolution_url}/message/sendMedia/{self.instance}",
                    json=payload
                )
                response.raise_for_status()
                responses.append(response.json())
            
            # Send selection buttons after all images
            if len(products_to_send) > 1:
                await asyncio.sleep(len(products_to_send) * 2)
                
                buttons = []
                for i, product in enumerate(products_to_send):
                    product_id = str(product.get('_id', product.get('id', '')))
                    buttons.append({
                        "type": "reply",
                        "displayText": f"Buy #{i+1}",
                        "id": f"buy_{product_id}"
                    })
                
                button_payload = {
                    "number": phone,
                    "buttonMessage": {
                        "title": "Select your choice:",
                        "buttons": buttons[:3]
                    }
                }
                
                await self.http_client.post(
                    f"{self.evolution_url}/message/sendButtons/{self.instance}",
                    json=button_payload
                )
            
            return responses
            
        except Exception as e:
            logger.error(f"Error sending product carousel: {e}")
            raise
    
    def format_product_message(self, product: Dict[str, Any], currency: str = 'USD') -> str:
        """
        Format a product into a rich text message with emojis
        
        Args:
            product: Product dict
        
        Returns:
            Formatted message string
        """
        # Category emojis
        category_emojis = {
            'electronics': '📱',
            'clothing': '👕',
            'shoes': '👟',
            'accessories': '👜',
            'jewelry': '💎',
            'food': '🍔',
            'beauty': '💄',
            'home': '🏠',
            'sports': '⚽',
            'books': '📚',
            'toys': '🧸',
            'automotive': '🚗'
        }
        
        category = product.get('category', '').lower()
        emoji = category_emojis.get(category, '🛍️')
        
        price = product.get('price', 0)
        price_str = f"{currency} {price:,.0f}" if price else "Price on request"
        
        parts = [
            f"{emoji} *{product['name'].upper()}*",
            "─" * 30,
            "",
            f"💰 *Price:* {price_str}"
        ]
        
        # Discount
        if product.get('discount'):
            parts.append(f"🔥 *Sale:* {product['discount']}% OFF")
        
        # Stock
        stock = product.get('stock')
        in_stock = product.get('in_stock', True)
        if stock is not None and in_stock:
            parts.append(f"📦 *Stock:* {stock} available")
        elif not in_stock or stock == 0:
            parts.append("⚠️ *Out of Stock*")
        
        # Description
        if product.get('description'):
            parts.extend(["", "📝 *Description:*", product['description']])
        
        # Additional details
        if product.get('colors'):
            parts.append(f"🎨 *Colors:* {', '.join(product['colors'])}")
        
        if product.get('sizes'):
            parts.append(f"📏 *Sizes:* {', '.join(product['sizes'])}")
        
        # Rating
        rating = product.get('rating')
        if rating:
            stars = '★' * int(float(rating))
            parts.append(f"⭐ *Rating:* {rating} {stars}")
        
        review_count = product.get('review_count')
        if review_count:
            parts.append(f"💬 *Reviews:* {review_count} customers")
        
        parts.extend(["", "🚚 Free shipping on orders over KES 5,000!"])
        
        return "\n".join(parts)
    
    async def close(self):
        """Close the HTTP client"""
        await self.http_client.aclose()
