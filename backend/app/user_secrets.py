"""API key storage: local file (dev) or per-user encrypted DB (hosted)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from app.config import PROJECT_ROOT, BACKEND_ROOT, hosted_mode

_SECRETS_PATH = PROJECT_ROOT / "private" / "api_keys.json"


def secrets_path() -> Path:
    return _SECRETS_PATH


def _read_file() -> dict[str, Any]:
    path = secrets_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_file(data: dict[str, Any]) -> None:
    path = secrets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _tenant_keys() -> dict[str, str] | None:
    if not hosted_mode():
        return None
    from app.tenant import current_api_keys, current_user_id

    keys = current_api_keys()
    if keys is not None:
        return keys
    uid = current_user_id()
    if not uid:
        return {}
    from app.auth_store import load_user_keys

    return load_user_keys(uid)


def get_stored_google_fonts_key() -> str | None:
    tenant = _tenant_keys()
    if tenant is not None:
        value = (tenant.get("google_fonts_api_key") or "").strip()
        return value or None
    value = (_read_file().get("google_fonts_api_key") or "").strip()
    return value or None


def resolve_google_fonts_key() -> str | None:
    return (
        get_stored_google_fonts_key()
        or (os.getenv("GOOGLE_FONTS_API_KEY") or "").strip()
        or None
    )


def get_stored_openai_key() -> str | None:
    tenant = _tenant_keys()
    if tenant is not None:
        value = (tenant.get("openai_api_key") or "").strip()
        return value or None
    value = (_read_file().get("openai_api_key") or "").strip()
    return value or None


def get_stored_xai_key() -> str | None:
    tenant = _tenant_keys()
    if tenant is not None:
        value = (tenant.get("xai_api_key") or "").strip()
        return value or None
    value = (_read_file().get("xai_api_key") or "").strip()
    return value or None


def resolve_openai_key() -> str | None:
    stored = get_stored_openai_key()
    if stored:
        return stored
    if hosted_mode():
        # Post-signup account trial may use the host key until the cap is hit.
        from app.trial import host_openai_key, is_guest_id, trial_status
        from app.tenant import current_user_id

        uid = current_user_id()
        if uid and not is_guest_id(uid) and trial_status().get("can_use_host_openai"):
            return host_openai_key()
        return None
    return (os.getenv("OPENAI_API_KEY") or None) or None


def resolve_xai_key() -> str | None:
    stored = get_stored_xai_key()
    if stored:
        return stored
    if hosted_mode():
        return None
    return (os.getenv("XAI_API_KEY") or None) or None


def _mask(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "••••••••"
    return f"{key[:4]}...{key[-4:]}"


def _dotenv_fallback(name: str) -> str | None:
    for candidate in (
        PROJECT_ROOT / ".env",
        BACKEND_ROOT / ".env",
        PROJECT_ROOT.parent / "private" / ".env",
    ):
        if not candidate.is_file():
            continue
        vals = dotenv_values(candidate)
        value = (vals.get(name) or "").strip()
        if value:
            return value
    return None


def settings_snapshot(*, reveal: bool = False) -> dict[str, Any]:
    """Return key status for the Settings UI."""
    openai = resolve_openai_key()
    xai = resolve_xai_key()
    google_fonts = resolve_google_fonts_key()
    trial: dict[str, Any] | None = None
    if hosted_mode():
        from app.trial import trial_status

        trial = trial_status()
        stored_rel = "account (encrypted)"
        has_stored = bool(
            get_stored_openai_key() or get_stored_xai_key() or get_stored_google_fonts_key()
        )
        if get_stored_openai_key():
            openai_source = "settings"
        elif trial and trial.get("can_use_host_openai"):
            openai_source = "trial"
        else:
            openai_source = None
        if get_stored_xai_key():
            xai_source = "settings"
        else:
            xai_source = None
        google_source = (
            "settings"
            if get_stored_google_fonts_key()
            else ("env" if (os.getenv("GOOGLE_FONTS_API_KEY") or "").strip() else None)
        )
    else:
        try:
            stored_rel = str(secrets_path().relative_to(PROJECT_ROOT))
        except ValueError:
            stored_rel = str(secrets_path())
        has_stored = secrets_path().is_file()
        openai_source = (
            "settings"
            if get_stored_openai_key()
            else ("env" if (os.getenv("OPENAI_API_KEY") or "").strip() else None)
        )
        xai_source = (
            "settings"
            if get_stored_xai_key()
            else ("env" if (os.getenv("XAI_API_KEY") or "").strip() else None)
        )
        google_source = (
            "settings"
            if get_stored_google_fonts_key()
            else (
                "env" if (os.getenv("GOOGLE_FONTS_API_KEY") or "").strip() else None
            )
        )
    # Never expose the host trial keys through Settings reveal.
    openai_reveal = get_stored_openai_key() if hosted_mode() else openai
    xai_reveal = get_stored_xai_key() if hosted_mode() else xai
    if openai_source == "trial" and trial:
        openai_hint = f"Free trial ({trial['remaining']} of {trial['limit']} left)"
    else:
        openai_hint = _mask(openai_reveal or openai)
    xai_hint = "Free trial" if xai_source == "trial" else _mask(xai_reveal or xai)

    return {
        "openai": {
            "configured": bool(openai),
            "source": openai_source,
            "hint": openai_hint,
            "value": openai_reveal if reveal else None,
            "label": "OpenAI API key",
            "help": (
                "Required for image generation, copy, and finalize. "
                "Hosted accounts get 3 free generate runs, then use your own key."
                if hosted_mode()
                else "Required for image generation, copy, and finalize."
            ),
            "env_name": "OPENAI_API_KEY",
        },
        "xai": {
            "configured": bool(xai),
            "source": xai_source,
            "hint": xai_hint,
            "value": xai_reveal if reveal else None,
            "label": "Grok / xAI API key",
            "help": "Optional. Enables Grok Imagine motion.",
            "env_name": "XAI_API_KEY",
        },
        "google_fonts": {
            "configured": bool(google_fonts),
            "source": google_source,
            "hint": _mask(google_fonts),
            "value": google_fonts if reveal else None,
            "label": "Google Fonts API key",
            "help": "Optional. Enables the full Web Fonts catalog in Review.",
            "env_name": "GOOGLE_FONTS_API_KEY",
        },
        "stored_file": stored_rel,
        "has_stored_file": has_stored,
        "hosted": hosted_mode(),
        "trial": trial,
    }


def update_keys(
    *,
    openai_api_key: str | None = None,
    xai_api_key: str | None = None,
    google_fonts_api_key: str | None = None,
    clear_openai: bool = False,
    clear_xai: bool = False,
    clear_google_fonts: bool = False,
) -> dict[str, Any]:
    """Upsert keys for the current user (hosted) or private/api_keys.json (local)."""
    if hosted_mode():
        from app.auth_store import update_user_keys
        from app.tenant import current_user_id, update_current_api_keys

        uid = current_user_id()
        if not uid:
            raise PermissionError("Not signed in")
        keys = update_user_keys(
            uid,
            openai_api_key=openai_api_key,
            xai_api_key=xai_api_key,
            google_fonts_api_key=google_fonts_api_key,
            clear_openai=clear_openai,
            clear_xai=clear_xai,
            clear_google_fonts=clear_google_fonts,
        )
        update_current_api_keys(keys)
        try:
            from app.fastapi_fonts import clear_google_fonts_cache

            clear_google_fonts_cache()
        except Exception:
            pass
        return settings_snapshot(reveal=False)

    data = _read_file()

    if clear_openai:
        data.pop("openai_api_key", None)
        fallback = _dotenv_fallback("OPENAI_API_KEY")
        if fallback:
            os.environ["OPENAI_API_KEY"] = fallback
        else:
            os.environ.pop("OPENAI_API_KEY", None)
    elif openai_api_key is not None:
        trimmed = openai_api_key.strip()
        if trimmed:
            data["openai_api_key"] = trimmed
            os.environ["OPENAI_API_KEY"] = trimmed

    if clear_xai:
        data.pop("xai_api_key", None)
        fallback = _dotenv_fallback("XAI_API_KEY")
        if fallback:
            os.environ["XAI_API_KEY"] = fallback
        else:
            os.environ.pop("XAI_API_KEY", None)
    elif xai_api_key is not None:
        trimmed = xai_api_key.strip()
        if trimmed:
            data["xai_api_key"] = trimmed
            os.environ["XAI_API_KEY"] = trimmed

    if clear_google_fonts:
        data.pop("google_fonts_api_key", None)
        fallback = _dotenv_fallback("GOOGLE_FONTS_API_KEY")
        if fallback:
            os.environ["GOOGLE_FONTS_API_KEY"] = fallback
        else:
            os.environ.pop("GOOGLE_FONTS_API_KEY", None)
    elif google_fonts_api_key is not None:
        trimmed = google_fonts_api_key.strip()
        if trimmed:
            data["google_fonts_api_key"] = trimmed
            os.environ["GOOGLE_FONTS_API_KEY"] = trimmed

    _write_file(data)
    try:
        from app.fastapi_fonts import clear_google_fonts_cache

        clear_google_fonts_cache()
    except Exception:
        pass
    return settings_snapshot(reveal=False)
