"""
Stripe API client (Connect platform + Checkout destination charges).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import stripe

from stripe_credentials import platform_secret_key, stripe_api_version

logger = logging.getLogger(__name__)


STRIPE_PLATFORM_PROFILE_URL = (
    "https://dashboard.stripe.com/settings/connect/platform-profile"
)


class StripeApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        action_url: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.action_url = action_url


def _configure() -> None:
    key = platform_secret_key()
    if not key:
        raise StripeApiError("Stripe platform secret key is not configured")
    stripe.api_key = key
    stripe.api_version = stripe_api_version()


def _stripe_error_message(exc: Exception) -> str:
    if isinstance(exc, stripe.StripeError):
        msg = getattr(exc, "user_message", None) or str(exc)
        return msg.strip() or "Stripe request failed"
    return str(exc)


def stripe_api_error_from_exception(exc: Exception) -> StripeApiError:
    msg = _stripe_error_message(exc)
    lower = msg.lower()
    if "cannot request the `card_payments` capability" in lower or (
        "card_payments" in lower and "accounts in" in lower
    ):
        return StripeApiError(
            "This country is not supported for Stripe card checkout on connected accounts. "
            "Choose a supported country in Integrations, or use Paystack / PayHero for Kenya and "
            "other local payment methods. See https://stripe.com/global",
            code="stripe_connect_country_unsupported",
            action_url="https://stripe.com/global",
        )
    if "platform-profile" in lower or "managing losses" in lower:
        return StripeApiError(
            "Stripe Connect platform profile is incomplete. Complete loss liability and "
            "platform settings in the Stripe Dashboard (same account as STRIPE_PLATFORM_SECRET_KEY), "
            "then try Connect again.",
            code="stripe_platform_profile_incomplete",
            action_url=STRIPE_PLATFORM_PROFILE_URL,
        )
    return StripeApiError(msg)


class StripeClient:
    async def create_connect_account(
        self,
        *,
        email: str,
        country: str,
        business_name: str,
        default_currency: str = "USD",
    ) -> Dict[str, Any]:
        cur = (default_currency or "USD").upper()
        cc = country.upper()

        def _run_v2():
            _configure()
            return stripe.Account.create(
                country=cc,
                email=email,
                default_currency=cur.lower(),
                business_profile={"name": business_name[:200]},
                controller={
                    "fees": {"payer": "application"},
                    "losses": {"payments": "application"},
                    "stripe_dashboard": {"type": "express"},
                },
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
            )

        def _run_express_legacy():
            _configure()
            return stripe.Account.create(
                type="express",
                country=cc,
                email=email,
                default_currency=cur.lower(),
                business_profile={"name": business_name[:200]},
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
            )

        try:
            acct = await asyncio.to_thread(_run_v2)
            return dict(acct)
        except Exception as e:
            logger.warning("[Stripe] create_connect_account (v2): %s — trying type=express", e)
            try:
                acct = await asyncio.to_thread(_run_express_legacy)
                return dict(acct)
            except Exception as e2:
                logger.warning("[Stripe] create_connect_account (express): %s", e2)
                raise stripe_api_error_from_exception(e2) from e2

    async def retrieve_account(self, account_id: str) -> Dict[str, Any]:
        def _run():
            _configure()
            return stripe.Account.retrieve(account_id)

        try:
            acct = await asyncio.to_thread(_run)
            return dict(acct)
        except Exception as e:
            raise stripe_api_error_from_exception(e) from e

    async def create_account_link(
        self,
        *,
        account_id: str,
        return_url: str,
        refresh_url: str,
    ) -> Dict[str, Any]:
        def _run():
            _configure()
            return stripe.AccountLink.create(
                account=account_id,
                return_url=return_url,
                refresh_url=refresh_url,
                type="account_onboarding",
            )

        try:
            link = await asyncio.to_thread(_run)
            return dict(link)
        except Exception as e:
            raise stripe_api_error_from_exception(e) from e

    async def create_checkout_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        def _run():
            _configure()
            return stripe.checkout.Session.create(**payload)

        try:
            session = await asyncio.to_thread(_run)
            return dict(session)
        except Exception as e:
            logger.warning("[Stripe] create_checkout_session: %s", e)
            raise stripe_api_error_from_exception(e) from e

    async def retrieve_checkout_session(self, session_id: str) -> Dict[str, Any]:
        def _run():
            _configure()
            return stripe.checkout.Session.retrieve(
                session_id,
                expand=["payment_intent"],
            )

        try:
            session = await asyncio.to_thread(_run)
            return dict(session)
        except Exception as e:
            raise stripe_api_error_from_exception(e) from e

    async def retrieve_payment_intent(self, payment_intent_id: str) -> Dict[str, Any]:
        def _run():
            _configure()
            return stripe.PaymentIntent.retrieve(payment_intent_id)

        try:
            pi = await asyncio.to_thread(_run)
            return dict(pi)
        except Exception as e:
            raise stripe_api_error_from_exception(e) from e

    async def create_refund(
        self,
        *,
        payment_intent_id: str,
        amount_minor: Optional[int] = None,
        reverse_transfer: bool = True,
        refund_application_fee: bool = True,
    ) -> Dict[str, Any]:
        def _run():
            _configure()
            params: Dict[str, Any] = {
                "payment_intent": payment_intent_id,
                "reverse_transfer": reverse_transfer,
                "refund_application_fee": refund_application_fee,
            }
            if amount_minor is not None:
                params["amount"] = int(amount_minor)
            return stripe.Refund.create(**params)

        try:
            refund = await asyncio.to_thread(_run)
            return dict(refund)
        except Exception as e:
            raise stripe_api_error_from_exception(e) from e
