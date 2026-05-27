"""
Channel Renderers — transforms the single-source-of-truth Letter into
channel-specific formats.

Inviolable: A channel never changes Rex's voice or top-3 constraint;
it changes only the surface visual presentation (REX.md §4.7).
"""

from __future__ import annotations

from rex.briefing.letter import Letter
from rex.channels.primitives import Channel


def render_for_channel(letter: Letter, channel: Channel) -> str:
    """
    Format a semantic Letter specifically for a target delivery channel.
    """
    if channel is Channel.IN_APP:
        return letter.body

    if channel is Channel.WHATSAPP:
        return _render_whatsapp_or_telegram(letter, is_telegram=False)

    if channel is Channel.TELEGRAM:
        return _render_whatsapp_or_telegram(letter, is_telegram=True)

    if channel is Channel.SMS:
        return _render_sms(letter)

    if channel is Channel.EMAIL:
        return _render_email(letter)

    raise ValueError(f"Unknown channel: {channel}")


def _render_whatsapp_or_telegram(letter: Letter, *, is_telegram: bool) -> str:
    """
    WhatsApp/Telegram layout:
    Numbered list format with short instruction tokens (YES / REVIEW).
    """
    header = "Rex 🤝" if not is_telegram else "Rex 🤖"
    divider = "─────────────────────────────"

    if letter.quiet_night:
        return f"{header}\n{divider}\n{letter.opener}\n\nQuiet night. Nothing needs you. — Rex\n{divider}"

    lines = [
        f"{header}",
        divider,
        f"{letter.opener}\n",
    ]

    # Convert the letter actions into numbered off-app listings
    for idx, act in enumerate(letter.actions, 1):
        lines.append(f"{idx}/ {act.summary}")
        # Append short action tokens suited for simple text answers
        lines.append(f"   Draft ready. Reply {idx} YES to send, or {idx} REVIEW to check.\n")

    lines.append("Reply LEDGER for full overnight summary.")
    lines.append(divider)

    return "\n".join(lines)


def _render_sms(letter: Letter) -> str:
    """
    SMS layout:
    Ultra-dense, single-line alert emphasizing immediate action.
    """
    if letter.quiet_night:
        return "Rex: Quiet night overall. Nothing needs you."

    # If actions exist, surface the most urgent (first) one
    top_action = letter.actions[0]
    return f"URGENT from Rex: {top_action.summary} Confidence {top_action.confidence_pct}%. Reply YES to approve, or check your dashboard."


def _render_email(letter: Letter) -> str:
    """
    Email layout:
    A structured layout matching the canonical in-app Letter, but wrapping it nicely.
    """
    return (
        f"Subject: Daily Briefing - {letter.opener}\n\n"
        f"{letter.body}\n"
        "---"
        "\nThis is an automated operational briefing generated overnight by Rex."
    )
