"""Local API key storage for the UI Settings panel.

Keys live in private/api_keys.json (gitignored). Stored values override process
env so a public install can ship with blank .env and users enter keys in the app.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from app.config import PROJECT_ROOT, BACKEND_ROOT

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


def get_stored_google_fonts_key() -> str | None:
    value = (_read_file().get("google_fonts_api_key") or "").strip()
    return value or None


def resolve_google_fonts_key() -> str | None:
    return (
        get_stored_google_fonts_key()
        or (os.getenv("GOOGLE_FONTS_API_KEY") or "").strip()
        or None
    )


def get_stored_openai_key() -> str | None:
    value = (_read_file().get("openai_api_key") or "").strip()
    return value or None


def get_stored_xai_key() -> str | None:
    value = (_read_file().get("xai_api_key") or "").strip()
    return value or None


def resolve_openai_key() -> str | None:
    return get_stored_openai_key() or (os.getenv("OPENAI_API_KEY") or None) or None


def resolve_xai_key() -> str | None:
    return get_stored_xai_key() or (os.getenv("XAI_API_KEY") or None) or None


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
    try:
        stored_rel = str(secrets_path().relative_to(PROJECT_ROOT))
    except ValueError:
        stored_rel = str(secrets_path())
    return {
        "openai": {
            "configured": bool(openai),
            "source": (
                "settings"
                if get_stored_openai_key()
                else ("env" if (os.getenv("OPENAI_API_KEY") or "").strip() else None)
            ),
            "hint": _mask(openai),
            "value": openai if reveal else None,
            "label": "OpenAI API key",
            "help": "Required for image generation, copy, and finalize.",
            "env_name": "OPENAI_API_KEY",
        },
        "xai": {
            "configured": bool(xai),
            "source": (
                "settings"
                if get_stored_xai_key()
                else ("env" if (os.getenv("XAI_API_KEY") or "").strip() else None)
            ),
            "hint": _mask(xai),
            "value": xai if reveal else None,
            "label": "Grok / xAI API key",
            "help": "Optional. Enables Grok Imagine motion. Works via HTTP on PC, Mac, and Windows ARM.",
            "env_name": "XAI_API_KEY",
        },
        "google_fonts": {
            "configured": bool(google_fonts),
            "source": (
                "settings"
                if get_stored_google_fonts_key()
                else (
                    "env"
                    if (os.getenv("GOOGLE_FONTS_API_KEY") or "").strip()
                    else None
                )
            ),
            "hint": _mask(google_fonts),
            "value": google_fonts if reveal else None,
            "label": "Google Fonts API key",
            "help": "Optional. Enables the full Web Fonts catalog in Review.",
            "env_name": "GOOGLE_FONTS_API_KEY",
        },
        "stored_file": stored_rel,
        "has_stored_file": secrets_path().is_file(),
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
    """Upsert keys into private/api_keys.json and sync process env."""
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
