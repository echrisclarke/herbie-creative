from __future__ import annotations

import logging

import httpx

from app.config import get_google_fonts_api_key

logger = logging.getLogger(__name__)

_CACHE: list[str] | None = None


def clear_google_fonts_cache() -> None:
    global _CACHE
    _CACHE = None


def list_google_fonts(query: str = "") -> list[str]:
    global _CACHE
    key = get_google_fonts_api_key()
    if not key:
        # Small curated fallback list when API key missing
        fallback = [
            "Inter",
            "Open Sans",
            "Roboto",
            "Montserrat",
            "Oswald",
            "Playfair Display",
            "Lato",
            "Poppins",
            "Source Sans 3",
            "IBM Plex Sans",
        ]
        q = query.lower().strip()
        return [f for f in fallback if q in f.lower()] if q else fallback

    try:
        if _CACHE is None:
            resp = httpx.get(
                "https://www.googleapis.com/webfonts/v1/webfonts",
                params={"key": key, "sort": "popularity"},
                timeout=30,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            _CACHE = [i.get("family", "") for i in items if i.get("family")]
        q = query.lower().strip()
        if not q:
            return (_CACHE or [])[:100]
        return [f for f in (_CACHE or []) if q in f.lower()][:50]
    except Exception as exc:
        logger.warning("Google Fonts catalog failed: %s", exc)
        fallback = ["Inter", "Open Sans", "Roboto", "Montserrat", "Oswald"]
        q = query.lower().strip()
        return [f for f in fallback if q in f.lower()] if q else fallback
