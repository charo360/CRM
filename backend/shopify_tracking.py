"""
Shopify Tracking Code Injector
Automatically injects GA4 and Zilo Behavior Tracker into Shopify stores
"""
import logging
from typing import Dict, Any, Optional
from assistant.composio_helper import composio_proxy as nango_proxy

logger = logging.getLogger(__name__)


async def inject_tracking_codes(
    db,
    user_id: str,
    ga4_measurement_id: str,
    business_id: str,
    api_url: str = "https://crm.zilo.pro/api"
) -> Dict[str, Any]:
    """
    Inject GA4 and Zilo Behavior Tracker into Shopify store via Script Tags API
    
    Args:
        db: Database connection
        user_id: User ID
        ga4_measurement_id: GA4 Measurement ID (G-XXXXXXXXXX)
        business_id: Business ID for behavior tracker
        api_url: API URL for behavior tracker
    
    Returns:
        Dict with status and script tag IDs
    """
    try:
        # Check if scripts already exist
        existing_scripts = await get_existing_script_tags(db, user_id)
        
        # Remove old scripts if they exist
        if existing_scripts:
            await remove_tracking_codes(db, user_id)
        
        # Create GA4 tracking script
        ga4_script = f"""
(function() {{
  var script1 = document.createElement('script');
  script1.async = true;
  script1.src = 'https://www.googletagmanager.com/gtag/js?id={ga4_measurement_id}';
  document.head.appendChild(script1);
  
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{ga4_measurement_id}');
}})();
"""
        
        # Create Zilo Behavior Tracker script
        behavior_script = f"""
(function() {{
  var script2 = document.createElement('script');
  script2.src = '{api_url.replace('/api', '')}/tracking/zilo-behavior-tracker.js';
  script2.onload = function() {{
    if (window.ZiloBehaviorTracker) {{
      ZiloBehaviorTracker.init({{
        businessId: '{business_id}',
        apiUrl: '{api_url}'
      }});
    }}
  }};
  document.head.appendChild(script2);
}})();
"""
        
        # Inject GA4 script tag
        ga4_response = await nango_proxy(
            business_id=user_id,
            integration_key="shopify",
            method="POST",
            path="/admin/api/2024-01/script_tags.json",
            json={
                "script_tag": {
                    "event": "onload",
                    "src": f"data:text/javascript;base64,{_encode_base64(ga4_script)}",
                    "display_scope": "all"
                }
            }
        )
        
        # Inject Zilo Behavior Tracker script tag
        behavior_response = await nango_proxy(
            business_id=user_id,
            integration_key="shopify",
            method="POST",
            path="/admin/api/2024-01/script_tags.json",
            json={
                "script_tag": {
                    "event": "onload",
                    "src": f"data:text/javascript;base64,{_encode_base64(behavior_script)}",
                    "display_scope": "all"
                }
            }
        )
        
        ga4_script_id = ga4_response.get("script_tag", {}).get("id")
        behavior_script_id = behavior_response.get("script_tag", {}).get("id")
        
        # Store script tag IDs in database for future removal/updates
        await db.users.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "settings.shopify_ga4_script_id": ga4_script_id,
                    "settings.shopify_behavior_script_id": behavior_script_id,
                    "settings.shopify_tracking_active": True
                }
            }
        )
        
        logger.info(f"[ShopifyTracking] Successfully injected tracking codes for user {user_id}")
        return {
            "status": "success",
            "ga4_script_id": ga4_script_id,
            "behavior_script_id": behavior_script_id,
            "message": "Tracking codes successfully injected into Shopify store"
        }
        
    except Exception as e:
        logger.error(f"[ShopifyTracking] Failed to inject tracking codes for {user_id}: {e}")
        return {
            "status": "error",
            "message": f"Failed to inject tracking codes: {str(e)}"
        }


async def remove_tracking_codes(db, user_id: str) -> Dict[str, Any]:
    """
    Remove GA4 and Zilo Behavior Tracker from Shopify store
    
    Args:
        db: Database connection
        user_id: User ID
    
    Returns:
        Dict with status
    """
    try:
        user = await db.users.find_one({"_id": user_id})
        if not user:
            return {"status": "error", "message": "User not found"}
        
        settings = user.get("settings", {})
        ga4_script_id = settings.get("shopify_ga4_script_id")
        behavior_script_id = settings.get("shopify_behavior_script_id")
        
        # Remove GA4 script
        if ga4_script_id:
            try:
                await nango_proxy(
                    business_id=user_id,
                    integration_key="shopify",
                    method="DELETE",
                    path=f"/admin/api/2024-01/script_tags/{ga4_script_id}.json"
                )
            except Exception as e:
                logger.warning(f"[ShopifyTracking] Failed to remove GA4 script {ga4_script_id}: {e}")
        
        # Remove Behavior Tracker script
        if behavior_script_id:
            try:
                await nango_proxy(
                    business_id=user_id,
                    integration_key="shopify",
                    method="DELETE",
                    path=f"/admin/api/2024-01/script_tags/{behavior_script_id}.json"
                )
            except Exception as e:
                logger.warning(f"[ShopifyTracking] Failed to remove behavior script {behavior_script_id}: {e}")
        
        # Clear script IDs from database
        await db.users.update_one(
            {"_id": user_id},
            {
                "$unset": {
                    "settings.shopify_ga4_script_id": "",
                    "settings.shopify_behavior_script_id": ""
                },
                "$set": {
                    "settings.shopify_tracking_active": False
                }
            }
        )
        
        logger.info(f"[ShopifyTracking] Successfully removed tracking codes for user {user_id}")
        return {
            "status": "success",
            "message": "Tracking codes successfully removed from Shopify store"
        }
        
    except Exception as e:
        logger.error(f"[ShopifyTracking] Failed to remove tracking codes for {user_id}: {e}")
        return {
            "status": "error",
            "message": f"Failed to remove tracking codes: {str(e)}"
        }


async def get_existing_script_tags(db, user_id: str) -> list:
    """
    Get existing Zilo script tags from Shopify store
    
    Args:
        db: Database connection
        user_id: User ID
    
    Returns:
        List of script tag IDs
    """
    try:
        response = await nango_proxy(
            business_id=user_id,
            integration_key="shopify",
            method="GET",
            path="/admin/api/2024-01/script_tags.json"
        )
        
        script_tags = response.get("script_tags", [])
        
        # Filter for Zilo-related scripts
        zilo_scripts = []
        for tag in script_tags:
            src = tag.get("src", "")
            if "zilo" in src.lower() or "gtag" in src.lower():
                zilo_scripts.append(tag.get("id"))
        
        return zilo_scripts
        
    except Exception as e:
        logger.error(f"[ShopifyTracking] Failed to get script tags for {user_id}: {e}")
        return []


async def update_tracking_codes(
    db,
    user_id: str,
    ga4_measurement_id: str,
    business_id: str,
    api_url: str = "https://crm.zilo.pro/api"
) -> Dict[str, Any]:
    """
    Update existing tracking codes or inject new ones
    
    Args:
        db: Database connection
        user_id: User ID
        ga4_measurement_id: GA4 Measurement ID
        business_id: Business ID for behavior tracker
        api_url: API URL for behavior tracker
    
    Returns:
        Dict with status
    """
    # Remove old scripts
    await remove_tracking_codes(db, user_id)
    
    # Inject new scripts
    return await inject_tracking_codes(db, user_id, ga4_measurement_id, business_id, api_url)


def _encode_base64(script: str) -> str:
    """Encode script to base64 for data URI"""
    import base64
    return base64.b64encode(script.encode()).decode()


async def check_shopify_connection(db, user_id: str) -> bool:
    """
    Check if user has active Shopify connection
    
    Args:
        db: Database connection
        user_id: User ID
    
    Returns:
        True if connected, False otherwise
    """
    try:
        # Try to make a simple API call to check connection
        await nango_proxy(
            business_id=user_id,
            integration_key="shopify",
            method="GET",
            path="/admin/api/2024-01/shop.json"
        )
        return True
    except Exception as e:
        logger.debug(f"[ShopifyTracking] User {user_id} not connected to Shopify: {e}")
        return False
