"""Hosted free-trial: limited runs on the server owner's API keys."""
from __future__ import annotations

import os
from typing import Any

from app.config import hosted_mode
from app.tenant import current_user_id


def trial_runs_limit() -> int:
    raw = (os.getenv("TRIAL_RUNS_LIMIT") or "3").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 3


def host_openai_key() -> str | None:
    value = (os.getenv("OPENAI_API_KEY") or "").strip()
    return value or None


def host_xai_key() -> str | None:
    value = (os.getenv("XAI_API_KEY") or "").strip()
    return value or None


def trial_status(user_id: str | None = None) -> dict[str, Any]:
    from app.auth_store import get_trial_runs_used, load_user_keys

    uid = user_id or current_user_id()
    limit = trial_runs_limit()
    used = get_trial_runs_used(uid) if uid else 0
    remaining = max(0, limit - used)
    keys = load_user_keys(uid) if uid else {}
    has_own_openai = bool((keys.get("openai_api_key") or "").strip())
    has_own_xai = bool((keys.get("xai_api_key") or "").strip())
    host_openai = bool(host_openai_key())
    host_xai = bool(host_xai_key())
    return {
        "enabled": hosted_mode() and limit > 0 and host_openai,
        "limit": limit,
        "used": used,
        "remaining": remaining,
        "has_own_openai": has_own_openai,
        "has_own_xai": has_own_xai,
        "can_use_host_openai": (
            hosted_mode()
            and not has_own_openai
            and remaining > 0
            and host_openai
        ),
        "can_use_host_xai": (
            hosted_mode() and not has_own_xai and remaining > 0 and host_xai
        ),
        "openai_ready": has_own_openai
        or (remaining > 0 and host_openai and hosted_mode()),
    }


def consume_trial_run_if_needed(user_id: str | None = None) -> bool:
    """Count one hosted trial run when the user has no OpenAI key of their own."""
    from app.auth_store import increment_trial_runs_used, load_user_keys

    if not hosted_mode():
        return False
    uid = user_id or current_user_id()
    if not uid:
        return False
    keys = load_user_keys(uid)
    if (keys.get("openai_api_key") or "").strip():
        return False
    if trial_status(uid)["remaining"] <= 0:
        return False
    if not host_openai_key():
        return False
    increment_trial_runs_used(uid)
    return True


def require_generate_access() -> None:
    """Raise ValueError if the user cannot start a generate job."""
    status = trial_status()
    if status["has_own_openai"]:
        return
    if status["can_use_host_openai"]:
        return
    if hosted_mode() and status["remaining"] <= 0:
        raise ValueError(
            "Free trial used up (3 generate runs). Add your own OpenAI API key in Settings to continue."
        )
    raise ValueError("OpenAI API key required. Add your key in Settings.")
