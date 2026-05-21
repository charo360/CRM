"""
Unified email sending client.
Supports: platform (Resend), SendGrid, Brevo, Mailgun, SMTP.
"""
from __future__ import annotations

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)

# ── helpers ───────────────────────────────────────────────────────────────────

def _from_name(settings: Dict[str, Any]) -> str:
    return settings.get("from_name") or os.getenv("PLATFORM_FROM_NAME", "Zilo")

def _from_email(settings: Dict[str, Any]) -> str:
    return settings.get("from_email") or os.getenv("PLATFORM_FROM_EMAIL", "noreply@getzilo.com")

def _creds(settings: Dict[str, Any]) -> Dict[str, Any]:
    return settings.get("credentials") or {}

# ── per-provider senders ──────────────────────────────────────────────────────

async def _send_resend(settings: Dict[str, Any], to: List[str], subject: str,
                        html: str, text: str) -> None:
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY not configured")
    payload = {
        "from": f"{_from_name(settings)} <{_from_email(settings)}>",
        "to": to,
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Resend error {r.status_code}: {r.text}")


async def _send_sendgrid(settings: Dict[str, Any], to: List[str], subject: str,
                          html: str, text: str) -> None:
    api_key = _creds(settings).get("api_key", "")
    if not api_key:
        raise RuntimeError("SendGrid api_key not configured")
    payload = {
        "personalizations": [{"to": [{"email": e} for e in to]}],
        "from": {"email": _from_email(settings), "name": _from_name(settings)},
        "subject": subject,
        "content": [{"type": "text/html", "value": html}],
    }
    if text:
        payload["content"].insert(0, {"type": "text/plain", "value": text})
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"SendGrid error {r.status_code}: {r.text}")


async def _send_brevo(settings: Dict[str, Any], to: List[str], subject: str,
                       html: str, text: str) -> None:
    api_key = _creds(settings).get("api_key", "")
    if not api_key:
        raise RuntimeError("Brevo api_key not configured")
    payload = {
        "sender": {"name": _from_name(settings), "email": _from_email(settings)},
        "to": [{"email": e} for e in to],
        "subject": subject,
        "htmlContent": html,
    }
    if text:
        payload["textContent"] = text
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Brevo error {r.status_code}: {r.text}")


async def _send_mailgun(settings: Dict[str, Any], to: List[str], subject: str,
                         html: str, text: str) -> None:
    creds = _creds(settings)
    api_key = creds.get("api_key", "")
    domain  = creds.get("domain", "")
    if not api_key or not domain:
        raise RuntimeError("Mailgun api_key and domain required")
    data = {
        "from":    f"{_from_name(settings)} <mailgun@{domain}>",
        "to":      ",".join(to),
        "subject": subject,
        "html":    html,
    }
    if text:
        data["text"] = text
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"https://api.mailgun.net/v3/{domain}/messages",
            auth=("api", api_key),
            data=data,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Mailgun error {r.status_code}: {r.text}")


def _send_smtp_sync(settings: Dict[str, Any], to: List[str], subject: str,
                     html: str, text: str) -> None:
    creds = _creds(settings)
    host     = creds.get("host", "")
    port     = int(creds.get("port", 587))
    username = creds.get("username", "")
    password = creds.get("password", "")
    use_tls  = creds.get("use_tls", True)
    if not host:
        raise RuntimeError("SMTP host not configured")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{_from_name(settings)} <{_from_email(settings)}>"
    msg["To"]      = ", ".join(to)
    if text:
        msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    server: smtplib.SMTP
    if use_tls and port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        if use_tls:
            server.starttls()
    if username:
        server.login(username, password)
    server.sendmail(msg["From"], to, msg.as_string())
    server.quit()


# ── public API ────────────────────────────────────────────────────────────────

async def send_email(settings: Dict[str, Any], to: List[str], subject: str,
                      html: str, text: str = "") -> None:
    """Send a single email via the configured provider."""
    provider = (settings.get("provider") or "platform").lower()
    if provider == "platform":
        await _send_resend(settings, to, subject, html, text)
    elif provider == "sendgrid":
        await _send_sendgrid(settings, to, subject, html, text)
    elif provider == "brevo":
        await _send_brevo(settings, to, subject, html, text)
    elif provider == "mailgun":
        await _send_mailgun(settings, to, subject, html, text)
    elif provider == "smtp":
        import asyncio
        await asyncio.get_event_loop().run_in_executor(
            None, _send_smtp_sync, settings, to, subject, html, text
        )
    else:
        raise RuntimeError(f"Unknown provider: {provider}")


async def send_bulk(settings: Dict[str, Any], recipients: List[str],
                     subject: str, html: str, text: str = "",
                     batch_size: int = 50) -> Dict[str, int]:
    """Send to many recipients in batches. Returns {sent, failed}."""
    sent = failed = 0
    for i in range(0, len(recipients), batch_size):
        batch = recipients[i: i + batch_size]
        try:
            await send_email(settings, batch, subject, html, text)
            sent += len(batch)
        except Exception as exc:
            log.error("Batch send failed (%s): %s", batch, exc)
            failed += len(batch)
    return {"sent": sent, "failed": failed}
