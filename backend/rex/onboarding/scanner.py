"""
Phase 11: Day 0 Onboarding — Data Scanner

Scans the founder's existing data (invoices, emails, deals, etc.)
while they're answering onboarding questions.

This is where Rex connects to the legacy CRM features
(Scout, Action Mode, etc.) to find real problems.
"""

import asyncio
import logging
import threading
from typing import Protocol, Optional

from .primitives import WebsiteInsights

logger = logging.getLogger(__name__)


class InvoiceStore(Protocol):
    """Protocol for accessing invoice data."""
    def count_overdue(self, days: int = 0) -> int:
        """Count invoices overdue by at least N days."""
        ...


class ConversationStore(Protocol):
    """Protocol for accessing conversation/message data."""
    def count_cold(self, days: int = 7) -> int:
        """Count conversations with no reply in N days."""
        ...


class DealStore(Protocol):
    """Protocol for accessing deal/pipeline data."""
    def count_stalled(self, days: int = 7) -> int:
        """Count deals with no movement in N days."""
        ...


class EmailStore(Protocol):
    """Protocol for accessing email data."""
    def count_unread(self) -> int:
        """Count unread emails."""
        ...


class ScoutStore(Protocol):
    """Protocol for accessing Scout lead data."""
    def count_recent_opportunities(self, days: int = 7) -> int:
        """Count opportunities found in last N days."""
        ...


def _run_async(coro, timeout: float = 20.0):
    """
    Run an async coroutine from a sync context.
    Works whether or not an event loop is already running on this thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict = {}

    def runner():
        result["value"] = asyncio.run(coro)

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout=timeout)
    return result.get("value")


class LiveDataScanner:
    """
    Scans the founder's actual business data during onboarding.

    This connects to the existing CRM backend (Scout, Action Mode, etc.)
    to find real problems Rex can immediately help with.
    """

    def __init__(
        self,
        invoices: InvoiceStore,
        conversations: ConversationStore,
        deals: DealStore,
        emails: EmailStore,
        scout: ScoutStore,
    ):
        self._invoices = invoices
        self._conversations = conversations
        self._deals = deals
        self._emails = emails
        self._scout = scout

    def scan_invoices(self) -> int:
        """Count overdue invoices (any amount overdue)."""
        return self._invoices.count_overdue(days=0)

    def scan_conversations(self) -> int:
        """Count conversations cold for 7+ days."""
        return self._conversations.count_cold(days=7)

    def scan_deals(self) -> int:
        """Count deals stalled for 7+ days."""
        return self._deals.count_stalled(days=7)

    def scan_emails(self) -> int:
        """Count unread emails."""
        return self._emails.count_unread()

    def scan_opportunities(self) -> int:
        """Count opportunities Scout found in last 7 days."""
        return self._scout.count_recent_opportunities(days=7)

    def scan_website(self, url: str) -> Optional[WebsiteInsights]:
        """
        Scrape the founder's website for business insights.

        Fetches the homepage and a few priority sub-pages (about, services,
        products, contact), then heuristically extracts company name, tech
        stack, social links, contact email, and blog presence.

        Returns None on any fetch/parse failure (onboarding stays graceful).
        """
        if not url:
            return None

        try:
            from utils.web_scraper import (
                scrape_site,
                infer_tech_stack,
                extract_social_links,
                extract_contact_email,
                has_blog,
            )
            scrape = _run_async(scrape_site(url, max_subpages=3))
        except Exception as e:
            logger.warning("[onboarding] Website scrape failed for %s: %s", url, e)
            return None

        if scrape is None:
            return None

        company_name = (scrape.og_name or scrape.title or "").strip()
        # Trim noisy site-name suffixes like "Acme | Home" → "Acme"
        if " | " in company_name:
            company_name = company_name.split(" | ")[0].strip()
        elif " - " in company_name and len(company_name.split(" - ")[0]) > 3:
            company_name = company_name.split(" - ")[0].strip()

        return WebsiteInsights(
            company_name=company_name,
            industry="",          # LLM enrichment can fill these later
            business_model="",
            target_market="",
            tech_stack=infer_tech_stack(scrape),
            has_blog=has_blog(scrape),
            social_links=extract_social_links(scrape),
            contact_email=extract_contact_email(scrape),
        )


class HonestDemoScanner:
    """
    Demo scanner used by the live onboarding flow before real CRM
    adapters are wired in. Returns zero for every CRM count (because
    nothing IS connected yet) and runs the real website scraper.

    Rule: never invent numbers. The "I see it" moment will lean on
    website findings + the founder's own pain-point answer.
    """

    def scan_invoices(self) -> int:
        return 0

    def scan_conversations(self) -> int:
        return 0

    def scan_deals(self) -> int:
        return 0

    def scan_emails(self) -> int:
        return 0

    def scan_opportunities(self) -> int:
        return 0

    def scan_website(self, url: str) -> Optional[WebsiteInsights]:
        # Reuse LiveDataScanner.scan_website by constructing a minimal one.
        # The CRM stores are never touched by scan_website, so passing None
        # for the protocols is safe — we only need the website path.
        live = LiveDataScanner.__new__(LiveDataScanner)
        return LiveDataScanner.scan_website(live, url)


class MockDataScanner:
    """
    Mock scanner for testing and demo environments.
    Returns realistic but fake data.
    """

    def __init__(
        self,
        overdue_invoices: int = 3,
        cold_conversations: int = 7,
        stalled_deals: int = 2,
        unread_emails: int = 47,
        opportunities: int = 5,
        website_insights: Optional[WebsiteInsights] = None,
    ):
        self._overdue_invoices = overdue_invoices
        self._cold_conversations = cold_conversations
        self._stalled_deals = stalled_deals
        self._unread_emails = unread_emails
        self._opportunities = opportunities
        self._website_insights = website_insights

    def scan_invoices(self) -> int:
        return self._overdue_invoices

    def scan_conversations(self) -> int:
        return self._cold_conversations

    def scan_deals(self) -> int:
        return self._stalled_deals

    def scan_emails(self) -> int:
        return self._unread_emails

    def scan_opportunities(self) -> int:
        return self._opportunities

    def scan_website(self, url: str) -> Optional[WebsiteInsights]:
        """Return mock website insights if configured."""
        if not url:
            return None
        return self._website_insights
