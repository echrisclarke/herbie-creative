"""Transactional email for password reset.

On Railway (Hobby), outbound SMTP is blocked, so prefer Brevo's HTTPS API
(same HerbieCreative Brevo account as Cycle / Sherbert). SMTP remains for
local or hosts that allow port 587. Resend is an optional third fallback.
"""
from __future__ import annotations

import logging
import os
import re
import smtplib
from email.message import EmailMessage

import httpx

logger = logging.getLogger("api")


def public_app_url() -> str:
    raw = (os.getenv("PUBLIC_APP_URL") or "https://pipeline.herbiecreative.com").strip()
    return raw.rstrip("/") or "https://pipeline.herbiecreative.com"


def brevo_api_configured() -> bool:
    return bool((os.getenv("BREVO_API_KEY") or "").strip())


def smtp_configured() -> bool:
    return bool(
        (os.getenv("SMTP_HOST") or "").strip()
        and (os.getenv("SMTP_USER") or "").strip()
        and (os.getenv("SMTP_PASS") or "").strip()
    )


def resend_configured() -> bool:
    return bool((os.getenv("RESEND_API_KEY") or "").strip())


def mail_configured() -> bool:
    return brevo_api_configured() or smtp_configured() or resend_configured()


def from_address() -> str:
    explicit = (
        os.getenv("SMTP_FROM")
        or os.getenv("MAIL_FROM")
        or os.getenv("BREVO_FROM")
        or os.getenv("RESEND_FROM")
        or ""
    ).strip()
    if explicit:
        return explicit
    return "Campaign Pipeline <noreply@herbiecreative.com>"


def _parse_from(raw: str) -> tuple[str, str]:
    """Return (name, email) from 'Name <email@x.com>' or bare email."""
    text = (raw or "").strip()
    match = re.match(r"^(.*?)\s*<([^>]+)>\s*$", text)
    if match:
        name = match.group(1).strip().strip('"') or "Campaign Pipeline"
        return name, match.group(2).strip()
    if "@" in text:
        return "Campaign Pipeline", text
    return "Campaign Pipeline", "noreply@herbiecreative.com"


def send_password_reset_email(*, to_email: str, reset_url: str) -> bool:
    """Send reset link. Returns True if the provider accepted it."""
    subject = "Reset your Campaign Pipeline password"
    body = (
        "Reset your Campaign Pipeline password with this link "
        "(expires in 1 hour):\n\n"
        f"{reset_url}\n\n"
        "If you did not ask for this, you can ignore the email."
    )
    # HTTPS first: Railway Hobby blocks outbound SMTP.
    if brevo_api_configured():
        return _send_via_brevo_api(to_email=to_email, subject=subject, body=body)
    if resend_configured():
        return _send_via_resend(to_email=to_email, subject=subject, body=body)
    if smtp_configured():
        return _send_via_smtp(to_email=to_email, subject=subject, body=body)
    logger.warning(
        "Password reset requested but no mail provider is configured. Reset URL (ops only): %s",
        reset_url,
    )
    return False


def _send_via_brevo_api(*, to_email: str, subject: str, body: str) -> bool:
    api_key = (os.getenv("BREVO_API_KEY") or "").strip()
    name, email = _parse_from(from_address())
    payload = {
        "sender": {"name": name, "email": email},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body,
    }
    try:
        res = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": api_key,
                "accept": "application/json",
                "content-type": "application/json",
            },
            json=payload,
            timeout=20.0,
        )
        if res.status_code >= 400:
            logger.error("Brevo API error %s: %s", res.status_code, res.text[:500])
            return False
        return True
    except httpx.HTTPError as exc:
        logger.error("Brevo API request failed: %s", exc)
        return False


def _send_via_smtp(*, to_email: str, subject: str, body: str) -> bool:
    host = (os.getenv("SMTP_HOST") or "").strip()
    user = (os.getenv("SMTP_USER") or "").strip()
    password = (os.getenv("SMTP_PASS") or "").strip()
    try:
        port = int((os.getenv("SMTP_PORT") or "587").strip() or "587")
    except ValueError:
        port = 587

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_address()
    msg["To"] = to_email
    msg.set_content(body)

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(user, password)
                smtp.send_message(msg)
        return True
    except Exception as exc:
        logger.error("SMTP send failed: %s", exc)
        return False


def _send_via_resend(*, to_email: str, subject: str, body: str) -> bool:
    api_key = (os.getenv("RESEND_API_KEY") or "").strip()
    payload = {
        "from": from_address(),
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    try:
        res = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20.0,
        )
        if res.status_code >= 400:
            logger.error("Resend error %s: %s", res.status_code, res.text[:500])
            return False
        return True
    except httpx.HTTPError as exc:
        logger.error("Resend request failed: %s", exc)
        return False
