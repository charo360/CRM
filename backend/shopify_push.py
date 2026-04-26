import logging
from typing import Dict, Any
from bson import ObjectId
from assistant.nango import nango_proxy

logger = logging.getLogger(__name__)

async def push_to_shopify(db, user_id: str, product_id: str) -> Dict[str, Any]:
    """
    Pushes a Zilo product to Shopify and updates the local record with the shopify_product_id.
    """
    try:
        product = await db.products.find_one({"_id": ObjectId(product_id), "user_id": user_id})
        if not product:
            raise ValueError("Product not found")

        payload = {
            "product": {
                "title": product.get("name", "Unnamed Product"),
                "body_html": product.get("description", ""),
                "product_type": product.get("category", "Retail"),
                "variants": [
                    {
                        "price": str(product.get("price", 0)),
                        "inventory_management": "shopify" if product.get("in_stock") else None,
                        "inventory_quantity": product.get("stock_quantity", 0)
                    }
                ]
            }
        }

        # If it has images
        images = product.get("images", [])
        if not images and product.get("image_url"):
            images = [product["image_url"]]
            
        if images:
            payload["product"]["images"] = [{"src": img} for img in images if img]

        # Use PUT if we already have a shopify ID, else POST
        method = "POST"
        path = "/admin/api/2024-01/products.json"
        
        if product.get("shopify_product_id"):
            method = "PUT"
            path = f"/admin/api/2024-01/products/{product['shopify_product_id']}.json"

        data = await nango_proxy(
            business_id=user_id,
            integration_key="shopify",
            method=method,
            path=path,
            json=payload
        )

        shopify_id = str(data.get("product", {}).get("id", ""))
        
        if shopify_id and not product.get("shopify_product_id"):
            await db.products.update_one(
                {"_id": ObjectId(product_id)},
                {"$set": {"shopify_product_id": shopify_id}}
            )

        logger.info(f"[ShopifyPush] Successfully pushed {product_id} to Shopify.")
        return {"status": "success", "shopify_id": shopify_id}

    except Exception as e:
        logger.error(f"[ShopifyPush] Failed to push product {product_id}: {e}")
        raise RuntimeError(f"Failed to push product to Shopify: {e}")
