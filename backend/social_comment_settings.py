"""Comment auto-reply settings (Composio social inbox)."""

from __future__ import annotations

from typing import Any, Dict

SETTINGS_KEY = "social_comment_autoreply"
LEGACY_SETTINGS_KEY = "zernio_comment_autoreply"


def read_comment_autoreply_settings(user_settings: Dict[str, Any] | None) -> Dict[str, Any]:
    settings = user_settings if isinstance(user_settings, dict) else {}
    saved = settings.get(SETTINGS_KEY) or settings.get(LEGACY_SETTINGS_KEY) or {}
    return saved if isinstance(saved, dict) else {}


def comment_autoreply_mongo_set(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Mongo $set fragment for persisting comment auto-reply settings."""
    return {f"settings.{SETTINGS_KEY}": settings}
