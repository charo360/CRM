"""
email_marketing/client.py
Unified email sender — abstracts platform Resend + user-configured providers.

Supported providers:
  platform  — Resend (RESEND_API_KEY env var) — default for all users
  smtp      — user's own SMTP server
  sendgrid  — user's own SendGrid API key
  brevo     — user's own Brevo (ex-Sendinblue) API key
  mailgun   — user's own Mailgun API key + domain
  mailchimp — Mailchimp Transactional (Mandrill) API key
  klaviyo   — Klaviyo SMTP relay (public key + private key)
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Platform sender (Resend) ──────────────────────────────────────────────────

RESEND_API = "https://api.resend.com/emails"
PLATFORM_FROM = os.environ.get("PLATFORM_FROM_EMAIL", "noreply@mail.zilocrm.com")
PLATFORM_FROM_NAME = os.environ.get("PLATFORM_FROM_NAME", "Zilo")


async def _send_via_resend(
    api_key: str,
    from_email: str,
    from_name: str,
    to: List[str],
    subject: str,
    html: str,
    text: str = "",
    reply_to: str = "",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "from": f"{from_name} <{from_email}>",
        "to": to,
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text
    if reply_to:
        payload["reply_to"] = reply_to
    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.post(
            RESEND_API,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
    data = r.json()
    if not r.is_success:
        raise RuntimeError(f"Resend error {r.status_code}: {data.get('message', r.text[:200])}")
    return {"provider": "resend", "id": data.get("id"), "status": "sent"}


# ── SendGrid ──────────────────────────────────────────────────────────────────

async def _send_via_sendgrid(
    api_key: str,
    from_email: str,
    from_name: str,
    to: List[str],
    subject: str,
    html: str,
    text: str = "",
) -> Dict[str, Any]:
    payload = {
        "personalizations": [{"to": [{"email": e} for e in to]}],
        "from": {"email": from_email, "name": from_name},
        "subject": subject,
        "content": [
            {"type": "text/html", "value": html},
        ],
    }
    if text:
        payload["content"].insert(0, {"type": "text/plain", "value": text})
    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
    if not r.is_success:
        raise RuntimeError(f"SendGrid error {r.status_code}: {r.text[:200]}")
    return {"provider": "sendgrid", "status": "sent"}


# ── Brevo ─────────────────────────────────────────────────────────────────────

async def _send_via_brevo(
    api_key: str,
    from_email: str,
    from_name: str,
    to: List[str],
    subject: str,
    html: str,
    text: str = "",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": e} for e in to],
        "subject": subject,
        "htmlContent": html,
    }
    if text:
        payload["textContent"] = text
    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers={"api-key": api_key, "Content-Type": "application/json"},
        )
    data = r.json()
    if not r.is_success:
        raise RuntimeError(f"Brevo error {r.status_code}: {data.get('message', r.text[:200])}")
    return {"provider": "brevo", "id": data.get("messageId"), "status": "sent"}


# ── Mailgun ───────────────────────────────────────────────────────────────────

async def _send_via_mailgun(
    api_key: str,
    domain: str,
    from_email: str,
    from_name: str,
    to: List[str],
    subject: str,
    html: str,
    text: str = "",
) -> Dict[str, Any]:
    data = {
        "from": f"{from_name} <{from_email}>",
        "to": ",".join(to),
        "subject": subject,
        "html": html,
    }
    if text:
        data["text"] = text
    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.post(
            f"https://api.mailgun.net/v3/{domain}/messages",
            data=data,
            auth=("api", api_key),
        )
    resp = r.json()
    if not r.is_success:
        raise RuntimeError(f"Mailgun error {r.status_code}: {resp.get('message', r.text[:200])}")
    return {"provider": "mailgun", "id": resp.get("id"), "status": "sent"}


# ── Mailchimp Transactional (Mandrill) ───────────────────────────────────────

async def _send_via_mailchimp(
    api_key: str,
    from_email: str,
    from_name: str,
    to: List[str],
    subject: str,
    html: str,
    text: str = "",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "key": api_key,
        "message": {
            "html": html,
            "subject": subject,
            "from_email": from_email,
            "from_name": from_name,
            "to": [{"email": e, "type": "to"} for e in to],
        },
    }
    if text:
        payload["message"]["text"] = text
    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.post("https://mandrillapp.com/api/1.0/messages/send", json=payload)
    if not r.is_success:
        raise RuntimeError(f"Mailchimp/Mandrill error {r.status_code}: {r.text[:200]}")
    results = r.json()
    rejected = [x for x in results if x.get("status") in ("rejected", "invalid")]
    if rejected and len(rejected) == len(to):
        raise RuntimeError(
            f"Mailchimp rejected all recipients: {rejected[0].get('reject_reason', 'unknown')}"
        )
    return {"provider": "mailchimp", "status": "sent", "id": results[0].get("_id") if results else None}


# ── Klaviyo (SMTP relay) ──────────────────────────────────────────────────────

async def _send_via_klaviyo(
    public_key: str,
    private_key: str,
    from_email: str,
    from_name: str,
    to: List[str],
    subject: str,
    html: str,
    text: str = "",
) -> Dict[str, Any]:
    """Send via Klaviyo's SMTP relay (smtp.klaviyo.com:587).
    Username = Public API Key, Password = Private API Key.
    """
    import asyncio
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: _send_via_smtp_sync(
            "smtp.klaviyo.com", 587,
            public_key, private_key,
            True,
            from_email, from_name, to, subject, html, text,
        ),
    )
    return {**result, "provider": "klaviyo"}


# ── SMTP ──────────────────────────────────────────────────────────────────────

def _send_via_smtp_sync(
    host: str,
    port: int,
    username: str,
    password: str,
    use_tls: bool,
    from_email: str,
    from_name: str,
    to: List[str],
    subject: str,
    html: str,
    text: str = "",
) -> Dict[str, Any]:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{from_name} <{from_email}>"
    msg["To"]      = ", ".join(to)
    if text:
        msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    context = ssl.create_default_context()
    if use_tls and port == 465:
        with smtplib.SMTP_SSL(host, port, context=context) as server:
            server.login(username, password)
            server.sendmail(from_email, to, msg.as_string())
    else:
        with smtplib.SMTP(host, port) as server:
            if use_tls:
                server.starttls(context=context)
            if username and password:
                server.login(username, password)
            server.sendmail(from_email, to, msg.as_string())
    return {"provider": "smtp", "status": "sent"}


# ── Unified send ──────────────────────────────────────────────────────────────

async def send_email(
    settings: Dict[str, Any],
    to: List[str],
    subject: str,
    html: str,
    text: str = "",
    reply_to: str = "",
) -> Dict[str, Any]:
    """
    settings keys:
      provider   : platform | resend | smtp | sendgrid | brevo | mailgun
      from_name  : display name
      from_email : sender address
      credentials: provider-specific dict
    """
    provider   = (settings.get("provider") or "platform").lower()
    from_name  = settings.get("from_name") or PLATFORM_FROM_NAME
    from_email = settings.get("from_email") or PLATFORM_FROM
    creds      = settings.get("credentials") or {}

    if provider in ("platform", "resend"):
        api_key = creds.get("api_key") or os.environ.get("RESEND_API_KEY", "")
        if not api_key:
            raise RuntimeError("RESEND_API_KEY not configured — set env var or use a custom provider.")
        return await _send_via_resend(api_key, from_email, from_name, to, subject, html, text, reply_to)

    if provider == "sendgrid":
        return await _send_via_sendgrid(creds["api_key"], from_email, from_name, to, subject, html, text)

    if provider == "brevo":
        return await _send_via_brevo(creds["api_key"], from_email, from_name, to, subject, html, text)

    if provider == "mailgun":
        return await _send_via_mailgun(
            creds["api_key"], creds["domain"], from_email, from_name, to, subject, html, text
        )

    if provider == "mailchimp":
        return await _send_via_mailchimp(creds["api_key"], from_email, from_name, to, subject, html, text)

    if provider == "klaviyo":
        return await _send_via_klaviyo(
            creds["public_key"], creds["private_key"], from_email, from_name, to, subject, html, text
        )

    if provider == "smtp":
        import asyncio
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _send_via_smtp_sync(
                creds["host"], int(creds.get("port", 587)),
                creds.get("username", ""), creds.get("password", ""),
                bool(creds.get("use_tls", True)),
                from_email, from_name, to, subject, html, text,
            ),
        )
        return result

    raise RuntimeError(f"Unknown email provider: {provider}")


async def send_bulk(
    settings: Dict[str, Any],
    recipients: List[str],
    subject: str,
    html: str,
    text: str = "",
    batch_size: int = 50,
) -> Dict[str, Any]:
    """Send to a large list in batches (avoids rate limits)."""
    import asyncio
    sent = failed = 0
    errors: List[str] = []
    for i in range(0, len(recipients), batch_size):
        batch = recipients[i : i + batch_size]
        try:
            await send_email(settings, batch, subject, html, text)
            sent += len(batch)
        except Exception as e:
            failed += len(batch)
            errors.append(str(e))
        await asyncio.sleep(0.2)
    return {"sent": sent, "failed": failed, "errors": errors[:5]}
