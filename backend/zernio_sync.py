import logging
import os
import datetime
import httpx
from typing import Dict, Any

logger = logging.getLogger(__name__)

ZERNIO_BASE = "https://zernio.com/api/v1"

async def sync_zernio_products(db, user_id: str) -> Dict[str, Any]:
    """
    Pulls products from the Zernio Unified Catalog (Meta/Google/TikTok) and syncs them to Zilo.
    """
    key = os.getenv("ZERNIO_API_KEY", "")
    if not key:
        raise ValueError("ZERNIO_API_KEY not configured")

    try:
        user_doc = await db.users.find_one({"_id": user_id}, {"zernio_profile_id": 1})
        profile_id = user_doc.get("zernio_profile_id")
        if not profile_id:
            logger.info(f"[ZernioSync] User {user_id} has no Zernio profile connected.")
            return {"status": "success", "synced": 0, "message": "No Zernio profile connected."}

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{ZERNIO_BASE}/catalog/products",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                params={"profileId": profile_id, "limit": 250}
            )
            
            if resp.status_code >= 400:
                # If the endpoint 404s, they just don't have catalog setup on Zernio yet.
                if resp.status_code == 404:
                    return {"status": "success", "synced": 0, "message": "No Zernio catalog exists."}
                logger.error(f"[ZernioSync] API Error {resp.status_code}: {resp.text}")
                raise RuntimeError(f"Zernio API error {resp.status_code}: {resp.text}")

        data = resp.json()
        products = data.get("products", [])
        if not products:
            logger.info(f"[ZernioSync] No products found on Zernio Catalog for user {user_id}.")
            return {"status": "success", "synced": 0, "message": "No products found on Zernio."}

        synced_count = 0
        now = datetime.datetime.utcnow()

        for p in products:
            zernio_id = str(p.get("id"))
            
            # Skip pushing if we have no valid ID
            if not zernio_id:
                continue

            title = p.get("title") or p.get("name") or "Unnamed Product"
            description = p.get("description", "")
            
            try:
                price = float(p.get("price", 0))
            except:
                price = 0.0

            availability = p.get("availability", "in stock")
            in_stock = availability.lower() in ("in stock", "available")
            
            # Handle images (either string array or single URL)
            raw_images = p.get("images", [])
            images = []
            if isinstance(raw_images, list):
                images = [img for img in raw_images if isinstance(img, str)]
            elif isinstance(raw_images, str):
                images = [raw_images]
                
            image_url = images[0] if images else ""

            update_doc = {
                "name": title,
                "description": description[:1000],
                "price": price,
                "image_url": image_url,
                "images": images,
                "category": p.get("category", "Retail"),
                "in_stock": in_stock,
                "zernio_product_id": zernio_id,
                "updated_at": now
            }

            # Upsert by zernio_product_id
            await db.products.update_one(
                {"user_id": user_id, "zernio_product_id": zernio_id},
                {"$set": update_doc, "$setOnInsert": {"created_at": now}},
                upsert=True
            )
            synced_count += 1

        logger.info(f"[ZernioSync] Successfully synced {synced_count} products for user {user_id}.")
        return {"status": "success", "synced": synced_count}

    except Exception as e:
        logger.error(f"[ZernioSync] Failed to fetch products for {user_id}: {e}")
        raise RuntimeError(f"Failed to fetch Zernio products: {e}")
