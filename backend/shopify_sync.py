import logging
import datetime
from typing import Dict, Any, List
from assistant.composio_helper import composio_proxy as nango_proxy

logger = logging.getLogger(__name__)

async def sync_shopify_products(db, user_id: str) -> Dict[str, Any]:
    """
    Pulls products from Shopify via Nango and syncs them to the local Zilo CRM products collection.
    """
    try:
        data = await nango_proxy(
            business_id=user_id,
            integration_key="shopify",
            method="GET",
            path="/admin/api/2024-01/products.json",
            params={"limit": 250}
        )
    except Exception as e:
        logger.error(f"[ShopifySync] Failed to fetch products for {user_id}: {e}")
        raise RuntimeError(f"Failed to fetch Shopify products: {e}")

    products = data.get("products", [])
    if not products:
        logger.info(f"[ShopifySync] No products found on Shopify for user {user_id}.")
        return {"status": "success", "synced": 0, "message": "No products found on Shopify."}

    synced_count = 0
    now = datetime.datetime.utcnow()

    for p in products:
        shopify_id = str(p.get("id"))
        title = p.get("title", "Unnamed Product")
        body_html = p.get("body_html", "")
        # Very basic HTML strip or keep as description
        description = body_html.replace("<p>", "").replace("</p>", "\n").replace("<br>", "\n") if body_html else ""
        
        # Determine price and stock from first variant
        variants = p.get("variants", [])
        price = 0.0
        in_stock = True
        stock_quantity = 0
        if variants:
            first_v = variants[0]
            try:
                price = float(first_v.get("price", 0))
            except:
                pass
            stock_quantity = first_v.get("inventory_quantity", 0)
            if first_v.get("inventory_management") == "shopify" and stock_quantity <= 0:
                in_stock = False

        # Get images
        images = p.get("images", [])
        image_url = images[0].get("src", "") if images else ""
        all_image_urls = [img.get("src", "") for img in images if img.get("src")]

        # Determine category from product_type or tags
        category = p.get("product_type") or "Retail"

        update_doc = {
            "name": title,
            "description": description[:1000],  # truncate if too long
            "price": price,
            "image_url": image_url,
            "images": all_image_urls,
            "category": category,
            "in_stock": in_stock,
            "stock_quantity": stock_quantity,
            "shopify_product_id": shopify_id,
            "updated_at": now
        }

        # Upsert
        await db.products.update_one(
            {"user_id": user_id, "shopify_product_id": shopify_id},
            {"$set": update_doc, "$setOnInsert": {"created_at": now}},
            upsert=True
        )
        synced_count += 1

    logger.info(f"[ShopifySync] Successfully synced {synced_count} products for user {user_id}.")
    return {"status": "success", "synced": synced_count}
