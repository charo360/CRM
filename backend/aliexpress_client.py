"""
AliExpress Dropshipping Open API Client
Handles automated dropship order placement and address translation
for mapped AliExpress listings.
"""

import hashlib
import hmac
import logging
import os
import time
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


def calculate_signature(secret: str, params: Dict[str, Any]) -> str:
    """
    Calculate the signature for AliExpress Open API request (HMAC-SHA256 / MD5).
    Sorts keys, concatenates, and hashes with the API secret.
    """
    # Sort parameters alphabetically by key
    sorted_keys = sorted(params.keys())
    
    # Concatenate param name and value
    query_str = ""
    for k in sorted_keys:
        val = params[k]
        if val is not None:
            query_str += f"{k}{val}"
            
    # Prepend secret and append secret for standard MD5 signature
    sign_src = f"{secret}{query_str}{secret}"
    
    # Compute MD5
    m = hashlib.md5()
    m.update(sign_src.encode("utf-8"))
    return m.hexdigest().upper()


async def get_aliexpress_credentials(db, user_id: str) -> Dict[str, str]:
    """
    Retrieve AliExpress API credentials. Prioritizes merchant's custom linked 
    AliExpress account, falling back to Zilo platform-level keys.
    """
    user = await db.users.find_one({"_id": user_id}, {"settings.aliexpress": 1})
    ali_settings = (user or {}).get("settings", {}).get("aliexpress", {})
    
    api_key = ali_settings.get("api_key") or os.environ.get("ALIEXPRESS_API_KEY")
    api_secret = ali_settings.get("api_secret") or os.environ.get("ALIEXPRESS_API_SECRET")
    access_token = ali_settings.get("access_token") or os.environ.get("ALIEXPRESS_ACCESS_TOKEN")
    
    return {
        "api_key": (api_key or "").strip(),
        "api_secret": (api_secret or "").strip(),
        "access_token": (access_token or "").strip()
    }


async def create_aliexpress_dropship_order(
    db,
    user_id: str,
    aliexpress_product_id: str,
    sku_id: str,
    quantity: int,
    shipping_address: dict
) -> Optional[str]:
    """
    Place an automated dropshipping order on AliExpress using the 
    aliexpress.ds.trade.buy (AliExpress Dropshipping Buy) API.
    
    Args:
        db: MongoDB database connection
        user_id: User/Business ID placing the order
        aliexpress_product_id: The target AliExpress item ID
        sku_id: The specific variant SKU ID mapped in Zilo
        quantity: Item quantity
        shipping_address: Customer's Shopify/Zilo shipping address dictionary
    
    Returns:
        The AliExpress Order ID string if successful, else None.
    """
    creds = await get_aliexpress_credentials(db, user_id)
    
    # Sandbox/Test Mode: If no production API keys are configured, 
    # we return a simulated AliExpress Order ID to allow end-to-end sandbox execution.
    if not creds["api_key"] or not creds["api_secret"]:
        simulated_id = f"ALI_SIM_{int(time.time())}"
        logger.info(f"[AliExpressClient] Sandbox Mode: Simulating AliExpress order placement. ID={simulated_id}")
        return simulated_id

    # AliExpress API Gateway URL
    url = "https://gw.api.alibaba.com/openapi/param2/1/aliexpress.open/aliexpress.ds.trade.buy"
    
    # Map shipping fields to AliExpress Dropshipping specifications
    first_name = shipping_address.get("first_name", "")
    last_name = shipping_address.get("last_name", "")
    contact_person = f"{first_name} {last_name}".strip() or "Valued Customer"
    
    # Address translation and normalisation
    phone = shipping_address.get("phone") or "0000000000"
    country_code = shipping_address.get("country_code", "US").upper()
    province = shipping_address.get("province") or shipping_address.get("city", "")
    city = shipping_address.get("city", "")
    address_line = shipping_address.get("address1", "")
    if shipping_address.get("address2"):
        address_line += f", {shipping_address['address2']}"
    zip_code = shipping_address.get("zip") or "0000"

    # Dropshipping order parameters payload
    # Doc: https://open.aliexpress.com/doc/api.htm?apiName=aliexpress.ds.trade.buy
    order_items = [{
        "product_id": int(aliexpress_product_id),
        "sku_id": sku_id,
        "quantity": quantity,
        "logistics_service_name": "AliExpress Standard Shipping"
    }]
    
    address_payload = {
        "contact_person": contact_person,
        "phone_number": phone,
        "country_code": country_code,
        "province": province,
        "city": city,
        "address": address_line,
        "zip": zip_code
    }
    
    # Prepare API Request Parameters
    params = {
        "app_key": creds["api_key"],
        "session": creds["access_token"],
        "timestamp": str(int(time.time() * 1000)),
        "format": "json",
        "v": "2.0",
        "sign_method": "md5",
        "items": __import__("json").dumps(order_items),
        "address": __import__("json").dumps(address_payload)
    }
    
    # Compute signature
    params["sign"] = calculate_signature(creds["api_secret"], params)
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, data=params)
            
        if response.status_code != 200:
            logger.error(f"[AliExpressClient] Error placing order, HTTP {response.status_code}: {response.text}")
            return None
            
        data = response.json()
        
        # Parse official response
        # Structure format: {"aliexpress_ds_trade_buy_response": {"result": {"order_list": [1234567]}}}
        result_wrapper = data.get("aliexpress_ds_trade_buy_response", {})
        result = result_wrapper.get("result", {})
        
        if result.get("is_success", False):
            order_list = result.get("order_list", [])
            if order_list:
                ali_order_id = str(order_list[0])
                logger.info(f"[AliExpressClient] Order placed successfully on AliExpress! ID={ali_order_id}")
                return ali_order_id
                
        error_msg = result.get("error_message") or data.get("error_response", {}).get("msg") or "Unknown API error"
        logger.error(f"[AliExpressClient] AliExpress API purchase failed: {error_msg}")
        return None
        
    except Exception as exc:
        logger.error(f"[AliExpressClient] Exception while placing AliExpress order: {exc}", exc_info=True)
        return None
