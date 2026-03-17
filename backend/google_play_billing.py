"""
Google Play Billing Integration
Handles subscription verification and management
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

class GooglePlayBilling:
    """Google Play Billing service for subscription verification"""
    
    SCOPES = ['https://www.googleapis.com/auth/androidpublisher']
    SERVICE_ACCOUNT_FILE = 'google-service-account.json'
    PACKAGE_NAME = 'com.charo360.whatsappcrm'
    
    def __init__(self):
        """Initialize Google Play API client"""
        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.SERVICE_ACCOUNT_FILE,
                scopes=self.SCOPES
            )
            self.service = build('androidpublisher', 'v3', credentials=credentials)
            logger.info("Google Play Billing service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Google Play Billing: {e}")
            self.service = None
    
    async def verify_purchase(self, product_id: str, purchase_token: str) -> Optional[Dict[str, Any]]:
        """
        Verify a subscription purchase with Google Play
        
        Args:
            product_id: The subscription product ID (e.g., 'crm_pro_monthly')
            purchase_token: The purchase token from the app
            
        Returns:
            Purchase details if valid, None otherwise
        """
        if not self.service:
            logger.error("Google Play service not initialized")
            return None
        
        try:
            # Get subscription details from Google Play
            result = self.service.purchases().subscriptions().get(
                packageName=self.PACKAGE_NAME,
                subscriptionId=product_id,
                token=purchase_token
            ).execute()
            
            logger.info(f"Purchase verified: {product_id} for token {purchase_token[:20]}...")
            return result
            
        except HttpError as e:
            logger.error(f"Failed to verify purchase: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error verifying purchase: {e}")
            return None
    
    async def get_subscription_status(self, product_id: str, purchase_token: str) -> Dict[str, Any]:
        """
        Get current subscription status
        
        Returns:
            Dict with status, expiry_date, auto_renewing, etc.
        """
        purchase_data = await self.verify_purchase(product_id, purchase_token)
        
        if not purchase_data:
            return {
                'valid': False,
                'status': 'invalid',
                'message': 'Could not verify subscription'
            }
        
        # Parse Google Play response
        expiry_time_millis = int(purchase_data.get('expiryTimeMillis', 0))
        expiry_date = datetime.fromtimestamp(expiry_time_millis / 1000)
        auto_renewing = purchase_data.get('autoRenewing', False)
        payment_state = purchase_data.get('paymentState', 0)
        
        # Determine status
        now = datetime.utcnow()
        is_active = expiry_date > now and payment_state == 1
        
        # Check for grace period
        grace_period_end = purchase_data.get('gracePeriodExpiryTimeMillis')
        in_grace_period = False
        if grace_period_end:
            grace_end = datetime.fromtimestamp(int(grace_period_end) / 1000)
            in_grace_period = now < grace_end
        
        # Determine final status
        if is_active:
            status = 'active'
        elif in_grace_period:
            status = 'grace_period'
        elif expiry_date < now:
            status = 'expired'
        else:
            status = 'pending'
        
        return {
            'valid': True,
            'status': status,
            'product_id': product_id,
            'expiry_date': expiry_date.isoformat(),
            'auto_renewing': auto_renewing,
            'payment_state': payment_state,
            'in_grace_period': in_grace_period,
            'purchase_token': purchase_token
        }
    
    async def cancel_subscription(self, product_id: str, purchase_token: str) -> bool:
        """
        Cancel a subscription (user-initiated)
        Note: This doesn't actually cancel on Google's side, just marks it in our system
        Users must cancel through Play Store
        """
        try:
            logger.info(f"Subscription cancellation requested: {product_id}")
            return True
        except Exception as e:
            logger.error(f"Error processing cancellation: {e}")
            return False
    
    def get_subscription_tier(self, product_id: str) -> str:
        """
        Get subscription tier from product ID
        
        Args:
            product_id: e.g., 'crm_pro_monthly'
            
        Returns:
            Tier name: 'basic', 'pro', or 'enterprise'
        """
        if 'basic' in product_id.lower():
            return 'basic'
        elif 'pro' in product_id.lower():
            return 'pro'
        elif 'enterprise' in product_id.lower():
            return 'enterprise'
        return 'free'
    
    def get_billing_period(self, product_id: str) -> str:
        """
        Get billing period from product ID
        
        Args:
            product_id: e.g., 'crm_pro_monthly'
            
        Returns:
            'monthly' or 'yearly'
        """
        if 'yearly' in product_id.lower() or 'annual' in product_id.lower():
            return 'yearly'
        return 'monthly'


# Subscription tier limits
SUBSCRIPTION_LIMITS = {
    'free': {
        'max_customers': 50,
        'max_products': 20,
        'max_team_members': 1,
        'ai_messages_per_month': 100,
        'features': ['basic_crm', 'whatsapp_integration']
    },
    'basic': {
        'max_customers': 500,
        'max_products': 100,
        'max_team_members': 3,
        'ai_messages_per_month': 1000,
        'features': ['basic_crm', 'whatsapp_integration', 'analytics', 'bookings']
    },
    'pro': {
        'max_customers': 5000,
        'max_products': 1000,
        'max_team_members': 10,
        'ai_messages_per_month': 10000,
        'features': ['basic_crm', 'whatsapp_integration', 'analytics', 'bookings', 
                    'advanced_analytics', 'custom_branding', 'api_access']
    },
    'enterprise': {
        'max_customers': -1,  # unlimited
        'max_products': -1,   # unlimited
        'max_team_members': -1,  # unlimited
        'ai_messages_per_month': -1,  # unlimited
        'features': ['basic_crm', 'whatsapp_integration', 'analytics', 'bookings',
                    'advanced_analytics', 'custom_branding', 'api_access',
                    'priority_support', 'custom_integrations', 'white_label']
    }
}


def check_feature_access(user_tier: str, feature: str) -> bool:
    """
    Check if a user's subscription tier has access to a feature
    
    Args:
        user_tier: User's subscription tier (free, basic, pro, enterprise)
        feature: Feature to check access for
        
    Returns:
        True if user has access, False otherwise
    """
    tier_data = SUBSCRIPTION_LIMITS.get(user_tier, SUBSCRIPTION_LIMITS['free'])
    return feature in tier_data.get('features', [])


def check_limit(user_tier: str, limit_type: str, current_count: int) -> bool:
    """
    Check if user is within their subscription limits
    
    Args:
        user_tier: User's subscription tier
        limit_type: Type of limit (max_customers, max_products, etc.)
        current_count: Current count of the resource
        
    Returns:
        True if within limits, False if exceeded
    """
    tier_data = SUBSCRIPTION_LIMITS.get(user_tier, SUBSCRIPTION_LIMITS['free'])
    max_limit = tier_data.get(limit_type, 0)
    
    # -1 means unlimited
    if max_limit == -1:
        return True
    
    return current_count < max_limit
