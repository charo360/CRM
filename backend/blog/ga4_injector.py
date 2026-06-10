"""
GA4 Tracking Injection for WordPress Multisite
Injects Google Analytics 4 tracking code into client WordPress subsites
"""
import logging
import httpx
import base64
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _wp_admin_auth() -> str:
    """Returns Basic auth header for WordPress admin."""
    user = os.getenv("WP_ADMIN_USER", "")
    password = os.getenv("WP_ADMIN_APP_PASSWORD", "")
    return base64.b64encode(f"{user}:{password}".encode()).decode()


async def inject_ga4_tracking(site_url: str, measurement_id: str) -> dict:
    """
    Injects GA4 tracking code into a WordPress subsite's header.
    Uses the Insert Headers and Footers plugin or custom code injection.
    
    Args:
        site_url: Full URL of the WordPress subsite (e.g., https://paya.zilo.pro)
        measurement_id: GA4 Measurement ID (e.g., G-XXXXXXXXXX)
    
    Returns:
        dict with status and message
    """
    if not measurement_id or not measurement_id.startswith("G-"):
        return {"success": False, "message": "Invalid GA4 Measurement ID"}
    
    # GA4 tracking script
    ga4_script = f"""
<!-- Google Analytics 4 -->
<script async src="https://www.googletagmanager.com/gtag/js?id={measurement_id}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{measurement_id}');
</script>
<!-- End Google Analytics 4 -->
"""
    
    try:
        headers = {
            "Authorization": f"Basic {_wp_admin_auth()}",
            "Content-Type": "application/json",
        }
        
        # Method 1: Try to use Insert Headers and Footers plugin settings
        # This plugin stores header code in wp_options as 'insert_headers_and_footers'
        async with httpx.AsyncClient(timeout=30) as client:
            # First, check if the option exists
            option_name = "ihaf_insert_header"  # Insert Headers and Footers plugin option
            
            # Update the header injection option via WP REST API (if plugin is active)
            # Note: This requires the plugin to be installed and activated
            # Alternative: Use wp-cli to update the option directly
            
            # For now, we'll use a custom approach: inject into theme's header.php
            # or use wp_head action hook via a custom plugin
            
            # Method 2: Create a custom mu-plugin (must-use plugin) for GA4
            # This is more reliable and doesn't depend on third-party plugins
            return await _inject_via_mu_plugin(site_url, measurement_id, ga4_script)
            
    except Exception as e:
        logger.error(f"[GA4] Failed to inject tracking for {site_url}: {e}")
        return {"success": False, "message": str(e)}


async def _inject_via_mu_plugin(site_url: str, measurement_id: str, ga4_script: str) -> dict:
    """
    Injects GA4 by creating a must-use plugin via WP-CLI.
    Must-use plugins are auto-loaded and can't be deactivated by users.
    """
    from blog.blog_service import _wp_cli
    
    # Extract slug from site_url (e.g., paya.zilo.pro → paya)
    slug = site_url.replace("https://", "").replace("http://", "").split(".")[0]
    
    # PHP code for the mu-plugin
    mu_plugin_code = f"""<?php
/**
 * Plugin Name: Zilo GA4 Tracking
 * Description: Google Analytics 4 tracking for {slug}
 * Version: 1.0
 * Author: Zilo
 */

add_action('wp_head', 'zilo_ga4_tracking', 1);
function zilo_ga4_tracking() {{
    if (is_admin()) return; // Don't track admin pages
    echo '{ga4_script.replace("'", "\\'")}';
}}
"""
    
    # Create the mu-plugin file via WP-CLI
    # mu-plugins are located at wp-content/mu-plugins/
    plugin_filename = f"zilo-ga4-{slug}.php"
    
    try:
        # Use wp-cli to create the file
        # Note: This requires write access to wp-content/mu-plugins/
        result = await _wp_cli(
            "eval",
            f"file_put_contents(WPMU_PLUGIN_DIR . '/{plugin_filename}', {repr(mu_plugin_code)});",
            url=site_url
        )
        
        if result.returncode == 0:
            logger.info(f"[GA4] Successfully injected tracking for {site_url} (ID: {measurement_id})")
            return {
                "success": True,
                "message": f"GA4 tracking activated for {slug}",
                "measurement_id": measurement_id,
                "method": "mu-plugin"
            }
        else:
            logger.warning(f"[GA4] WP-CLI injection failed: {result.stderr}")
            return {"success": False, "message": result.stderr}
            
    except Exception as e:
        logger.error(f"[GA4] mu-plugin creation failed: {e}")
        return {"success": False, "message": str(e)}


async def remove_ga4_tracking(site_url: str) -> dict:
    """
    Removes GA4 tracking from a WordPress subsite.
    
    Args:
        site_url: Full URL of the WordPress subsite
    
    Returns:
        dict with status and message
    """
    from blog.blog_service import _wp_cli
    
    slug = site_url.replace("https://", "").replace("http://", "").split(".")[0]
    plugin_filename = f"zilo-ga4-{slug}.php"
    
    try:
        result = await _wp_cli(
            "eval",
            f"@unlink(WPMU_PLUGIN_DIR . '/{plugin_filename}');",
            url=site_url
        )
        
        if result.returncode == 0:
            logger.info(f"[GA4] Removed tracking for {site_url}")
            return {"success": True, "message": f"GA4 tracking removed for {slug}"}
        else:
            return {"success": False, "message": result.stderr}
            
    except Exception as e:
        logger.error(f"[GA4] Failed to remove tracking: {e}")
        return {"success": False, "message": str(e)}


async def update_ga4_tracking(site_url: str, new_measurement_id: str) -> dict:
    """
    Updates GA4 tracking ID for a WordPress subsite.
    
    Args:
        site_url: Full URL of the WordPress subsite
        new_measurement_id: New GA4 Measurement ID
    
    Returns:
        dict with status and message
    """
    # Remove old tracking and inject new one
    await remove_ga4_tracking(site_url)
    return await inject_ga4_tracking(site_url, new_measurement_id)
