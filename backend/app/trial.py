"""Pre-signup guest trial on the host API key, with hard generate/still caps.

Signed-in users do not share the host key. They must add their own OpenAI key.
Token metering is approximated by still counts (image gens), which is the main cost.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import hosted_mode
from app.tenant import current_user_id


def trial_runs_limit() -> int:
    raw = (os.getenv("TRIAL_RUNS_LIMIT") or "3").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 3


def trial_max_stills_per_run() -> int:
    raw = (os.getenv("TRIAL_MAX_STILLS_PER_RUN") or "6").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 6


def trial_max_total_stills() -> int:
    raw = (os.getenv("TRIAL_MAX_TOTAL_STILLS") or "18").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 18


def trial_force_quality() -> str:
    value = (os.getenv("TRIAL_FORCE_QUALITY") or "low").strip().lower()
    if value not in {"low", "medium", "high"}:
        return "low"
    return value


def trial_allow_motion() -> bool:
    return (os.getenv("TRIAL_ALLOW_MOTION") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def trial_global_daily_runs() -> int:
    raw = (os.getenv("TRIAL_GLOBAL_DAILY_RUNS") or "100").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 100


def host_openai_key() -> str | None:
    value = (os.getenv("OPENAI_API_KEY") or "").strip()
    return value or None


def host_xai_key() -> str | None:
    value = (os.getenv("XAI_API_KEY") or "").strip()
    return value or None


def is_guest_id(user_id: str | None) -> bool:
    return bool(user_id and str(user_id).startswith("guest_"))


def guest_folder_id(guest_id: str) -> str:
    return f"guest_{guest_id}"


def trial_status(user_id: str | None = None) -> dict[str, Any]:
    """Status for the current guest trial or signed-in account."""
    from app.auth_store import (
        get_guest_trial,
        get_trial_runs_used,
        load_user_keys,
        today_global_trial_runs,
    )

    uid = user_id or current_user_id()
    limit = trial_runs_limit()
    host_openai = bool(host_openai_key())
    host_xai = bool(host_xai_key())
    global_used = today_global_trial_runs()
    global_limit = trial_global_daily_runs()
    global_ok = global_limit <= 0 or global_used < global_limit

    if is_guest_id(uid):
        guest = get_guest_trial(uid.removeprefix("guest_"))
        used = int(guest["runs_used"]) if guest else 0
        stills_used = int(guest["stills_used"]) if guest else 0
        remaining_runs = max(0, limit - used)
        remaining_stills = max(0, trial_max_total_stills() - stills_used)
        can_host = (
            hosted_mode()
            and host_openai
            and remaining_runs > 0
            and remaining_stills > 0
            and global_ok
        )
        return {
            "enabled": hosted_mode() and limit > 0 and host_openai,
            "mode": "guest",
            "requires_signup": not can_host,
            "limit": limit,
            "used": used,
            "remaining": remaining_runs,
            "stills_used": stills_used,
            "stills_remaining": remaining_stills,
            "max_stills_per_run": trial_max_stills_per_run(),
            "max_total_stills": trial_max_total_stills(),
            "force_quality": trial_force_quality(),
            "allow_motion": False,
            "has_own_openai": False,
            "has_own_xai": False,
            "can_use_host_openai": can_host,
            "can_use_host_xai": False,
            "openai_ready": can_host,
            "global_daily_used": global_used,
            "global_daily_limit": global_limit,
        }

    # Signed-in: host key is not shared. Own keys only.
    keys = load_user_keys(uid) if uid else {}
    has_own_openai = bool((keys.get("openai_api_key") or "").strip())
    has_own_xai = bool((keys.get("xai_api_key") or "").strip())
    return {
        "enabled": False,
        "mode": "account",
        "requires_signup": False,
        "limit": 0,
        "used": get_trial_runs_used(uid) if uid else 0,
        "remaining": 0,
        "stills_used": 0,
        "stills_remaining": 0,
        "max_stills_per_run": trial_max_stills_per_run(),
        "max_total_stills": trial_max_total_stills(),
        "force_quality": trial_force_quality(),
        "allow_motion": True,
        "has_own_openai": has_own_openai,
        "has_own_xai": has_own_xai,
        "can_use_host_openai": False,
        "can_use_host_xai": False,
        "openai_ready": has_own_openai,
        "global_daily_used": global_used,
        "global_daily_limit": global_limit,
    }


def ensure_guest_session(session: dict) -> str:
    """Return guest folder id (guest_<uuid>), creating the guest row if needed."""
    from app.auth_store import create_guest_trial, get_guest_trial

    raw = str(session.get("guest_id") or "").strip()
    if raw and get_guest_trial(raw):
        return guest_folder_id(raw)
    guest_id = uuid.uuid4().hex
    create_guest_trial(guest_id)
    session["guest_id"] = guest_id
    return guest_folder_id(guest_id)


def estimate_stills(
    *,
    product_count: int,
    outputs: list[str] | None,
    framing: str | None,
) -> int:
    ratios = outputs or ["1:1", "9:16", "16:9"]
    framing_mult = 2 if (framing or "both") == "both" else 1
    products = max(1, product_count)
    return max(1, products * len(ratios) * framing_mult)


def apply_trial_generate_guards(
    body: Any,
    *,
    product_count: int = 1,
) -> tuple[Any, int]:
    """Mutate generate request for guest trial; return (body, estimated_stills)."""
    status = trial_status()
    if status.get("mode") != "guest" or not status.get("can_use_host_openai"):
        est = estimate_stills(
            product_count=product_count,
            outputs=getattr(body, "outputs", None),
            framing=getattr(body, "framing", None),
        )
        return body, est

    body.image_quality = trial_force_quality()  # type: ignore[attr-defined]
    # "both" framing doubles image count; force a single framing on trial.
    if getattr(body, "framing", None) == "both":
        body.framing = "close-up"  # type: ignore[attr-defined]

    outputs = list(body.outputs or ["1:1", "9:16", "16:9"])
    per_run = trial_max_stills_per_run()
    stills_left = int(status.get("stills_remaining") or per_run)
    budget = min(per_run, stills_left)
    products = max(1, product_count)

    # Shrink ratios until estimate fits budget.
    while outputs and estimate_stills(
        product_count=products, outputs=outputs, framing=body.framing
    ) > budget:
        outputs.pop()
    if not outputs:
        outputs = ["1:1"]
    body.outputs = outputs  # type: ignore[attr-defined]
    body.creatives_only = True  # type: ignore[attr-defined]

    est = estimate_stills(
        product_count=products, outputs=body.outputs, framing=body.framing
    )
    return body, est


def consume_trial_run_if_needed(*, estimated_stills: int = 0) -> bool:
    from app.auth_store import (
        increment_guest_trial,
        increment_global_trial_run,
    )

    if not hosted_mode():
        return False
    uid = current_user_id()
    if not is_guest_id(uid):
        return False
    status = trial_status(uid)
    if not status.get("can_use_host_openai"):
        return False
    guest_id = uid.removeprefix("guest_")
    increment_guest_trial(guest_id, stills=max(0, estimated_stills))
    increment_global_trial_run()
    return True


def require_generate_access() -> None:
    status = trial_status()
    if status.get("has_own_openai"):
        return
    if status.get("can_use_host_openai"):
        return
    if status.get("mode") == "guest":
        raise ValueError(
            "Free trial finished. Sign up and add your own OpenAI API key to keep generating."
        )
    if hosted_mode():
        raise ValueError(
            "Add your own OpenAI API key in Settings to generate. "
            "The free trial is only available before you create an account."
        )
    raise ValueError("OpenAI API key required. Add your key in Settings.")


def require_motion_access() -> None:
    status = trial_status()
    if status.get("mode") == "guest" and not trial_allow_motion():
        raise ValueError(
            "Motion is not included in the free trial. Sign up and add your own keys."
        )
    if status.get("mode") == "account" and not status.get("has_own_xai"):
        raise ValueError("Add your own Grok / xAI key in Settings for motion.")
