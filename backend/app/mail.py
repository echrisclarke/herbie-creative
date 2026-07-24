"""Transactional email via Resend (optional). Used for password reset links."""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("api")


def resend_configured() -> bool:
    return bool((os.getenv("RESEND_API_KEY") or "").strip())


def public_app_url() -> str:
    raw = (os.getenv("PUBLIC_APP_URL") or "https://pipeline.herbiecreative.com").strip()
    return raw.rstrip("/") or "https://pipeline.herbiecreative.com"


def reset_from_address() -> str:
    return (
        (os.getenv("RESEND_FROM") or "").strip()
        or "Campaign Pipeline <onboarding@resend.dev>"
    )


def send_password_reset_email(*, to_email: str, reset_url: str) -> bool:
    """Send reset link. Returns True if accepted by the provider."""
    api_key = (os.getenv("RESEND_API_KEY") or "").strip()
    if not api_key:
        logger.warning(
            "Password reset requested but RESEND_API_KEY is unset. Reset URL (ops only): %s",
            reset_url,
        )
        return False

    payload = {
        "from": reset_from_address(),
        "to": [to_email],
        "subject": "Reset your Campaign Pipeline password",
        "text": (
            "Reset your Campaign Pipeline password with this link "
            "(expires in 1 hour):\n\n"
            f"{reset_url}\n\n"
            "If you did not ask for this, you can ignore the email."
        ),
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
