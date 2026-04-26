import logging
import os
import httpx
from typing import Dict, Any
from bson import ObjectId

logger = logging.getLogger(__name__)

ZERNIO_BASE = "https://zernio.com/api/v1"

async def push_to_zernio(db, user_id: str, product_id: str) -> Dict[str, Any]:
    """
    Pushes a Zilo product to the Zernio Unified Catalog (Meta/Google/TikTok).
    """
    key = os.getenv("ZERNIO_API_KEY", "")
    if not key:
        raise ValueError("ZERNIO_API_KEY not configured")

    try:
        product = await db.products.find_one({"_id": ObjectId(product_id), "user_id": user_id})
        if not product:
            raise ValueError("Product not found")

        # Get Zernio Profile ID for this user
        user_doc = await db.users.find_one({"_id": user_id}, {"zernio_profile_id": 1})
        profile_id = user_doc.get("zernio_profile_id")
        if not profile_id:
            raise ValueError("User has no Zernio profile connected.")

        images = product.get("images", [])
        if not images and product.get("image_url"):
            images = [product["image_url"]]

        payload = {
            "profileId": profile_id,
            "product": {
                "id": str(product["_id"]),
                "title": product.get("name", "Unnamed Product"),
                "description": product.get("description", ""),
                "price": product.get("price", 0),
                "currency": product.get("currency", "USD"),
                "availability": "in stock" if product.get("in_stock") else "out of stock",
                "condition": "new",
                "images": images,
                "category": product.get("category", "Retail")
            }
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{ZERNIO_BASE}/catalog/products",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload
            )
            
            if resp.status_code >= 400:
                logger.error(f"[ZernioPush] API Error {resp.status_code}: {resp.text}")
                raise RuntimeError(f"Zernio API error {resp.status_code}: {resp.text}")

        data = resp.json()
        zernio_product_id = data.get("id") or data.get("product", {}).get("id", str(product["_id"]))

        await db.products.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": {"zernio_product_id": zernio_product_id}}
        )

        logger.info(f"[ZernioPush] Successfully pushed {product_id} to Zernio Catalog.")
        return {"status": "success", "zernio_id": zernio_product_id}

    except Exception as e:
        logger.error(f"[ZernioPush] Failed to push product {product_id}: {e}")
        raise RuntimeError(f"Failed to push product to Zernio Catalog: {e}")
