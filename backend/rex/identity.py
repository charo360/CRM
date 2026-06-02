"""
Product identity — the Chief of Staff is Zilo.

Zilo Chat already routes specialist agents (Scout, Document Writer, Meta Ads, …).
This package gives Zilo the Rex-layer capabilities: trust ranks, morning briefing,
ledger, notebook, overnight loop, and team promotions.

Internal module paths stay `rex.*`; HTTP routes stay `/api/rex/*`.
"""

CHIEF_OF_STAFF_NAME = "Zilo"
CHIEF_OF_STAFF_DISPLAY = "Zilo"

# Back-compat alias for code that still says REX in enum/type names.
REX_ACTOR_NAME = CHIEF_OF_STAFF_NAME
