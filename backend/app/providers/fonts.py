from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx

from app.config import bundled_font_bold, bundled_font_regular, font_cache_root

logger = logging.getLogger(__name__)


def resolve_font_path(
    font_names: list[str] | None = None,
    font_file_path: str | None = None,
    bold: bool = False,
    sample_text: str = "",
) -> Path:
    if font_file_path:
        path = Path(font_file_path)
        if path.exists():
            return path

    # Non-Latin overlays need a font with those glyphs
    script_font = _resolve_script_font(sample_text)
    if script_font:
        return script_font

    for name in font_names or []:
        cached = _try_google_font(name, bold=bold)
        if cached:
            return cached

    return bundled_font_bold() if bold else bundled_font_regular()


def _resolve_script_font(text: str) -> Path | None:
    script = _detect_script(text or "")
    if script == "cjk":
        return _resolve_cjk_font()
    if script == "bengali":
        return _resolve_noto_family(
            "noto_sans_bengali",
            family="Noto Sans Bengali",
            windows=("C:/Windows/Fonts/Nirmala.ttf", "C:/Windows/Fonts/vrinda.ttf"),
        )
    if script == "devanagari":
        return _resolve_noto_family(
            "noto_sans_devanagari",
            family="Noto Sans Devanagari",
            windows=("C:/Windows/Fonts/Nirmala.ttf", "C:/Windows/Fonts/mangal.ttf"),
        )
    if script == "arabic":
        return _resolve_noto_family(
            "noto_sans_arabic",
            family="Noto Sans Arabic",
            windows=("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/tahoma.ttf"),
        )
    if script == "tamil":
        return _resolve_noto_family(
            "noto_sans_tamil",
            family="Noto Sans Tamil",
            windows=("C:/Windows/Fonts/Nirmala.ttf", "C:/Windows/Fonts/latha.ttf"),
        )
    return None


def _detect_script(text: str) -> str | None:
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return "cjk"
    if any("\u0980" <= ch <= "\u09FF" for ch in text):
        return "bengali"
    if any("\u0900" <= ch <= "\u097F" for ch in text):
        return "devanagari"
    if any("\u0600" <= ch <= "\u06FF" for ch in text):
        return "arabic"
    if any("\u0B80" <= ch <= "\u0BFF" for ch in text):
        return "tamil"
    if any("\u3040" <= ch <= "\u30FF" for ch in text):
        return "cjk"
    if any("\uAC00" <= ch <= "\uD7AF" for ch in text):
        return "cjk"
    return None


def _needs_cjk(text: str) -> bool:
    return _detect_script(text) == "cjk"


def _resolve_noto_family(
    cache_key: str,
    *,
    family: str,
    windows: tuple[str, ...] = (),
) -> Path | None:
    cache = font_cache_root() / cache_key / "400.ttf"
    if cache.exists() and cache.stat().st_size > 1000:
        return cache
    downloaded = _try_google_font(family, bold=False)
    if downloaded:
        return downloaded
    for candidate in windows:
        path = Path(candidate)
        if path.exists():
            return path
    return None


def _resolve_cjk_font() -> Path | None:
    # Prefer cached Noto Sans SC; else common Windows CJK faces
    cache = font_cache_root() / "noto_sans_sc" / "400.otf"
    if cache.exists() and cache.stat().st_size > 1000:
        return cache
    downloaded = _try_noto_sans_sc()
    if downloaded:
        return downloaded
    for candidate in (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ):
        if candidate.exists():
            return candidate
    return None


def _try_noto_sans_sc() -> Path | None:
    """Best-effort download of a CJK-capable face for zh overlays."""
    cache_dir = font_cache_root() / "noto_sans_sc"
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / "400.otf"
    if target.exists() and target.stat().st_size > 1000:
        return target
    # Google Fonts CSS often returns woff2; try known gstatic TTF for Noto Sans SC
    urls = [
        "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansSC-Regular.otf",
        "https://github.com/googlefonts/noto-cjk/raw/main/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf",
    ]
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            for url in urls:
                try:
                    resp = client.get(url)
                    if resp.status_code == 200 and len(resp.content) > 50_000:
                        target.write_bytes(resp.content)
                        return target
                except Exception:
                    continue
    except Exception as exc:
        logger.warning("Noto Sans SC download failed: %s", exc)
    return None


def _try_google_font(family: str, bold: bool = False) -> Path | None:
    family = family.strip()
    if not family:
        return None
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", family).strip("_").lower()
    weight = "700" if bold else "400"
    cache_dir = font_cache_root() / slug
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{weight}.ttf"
    if target.exists() and target.stat().st_size > 1000:
        return target

    # Prefer known raw TTF mirrors for single-weight / pixel faces (CSS2 often 400-only or woff2).
    raw = _known_google_ttf(family, bold=bold)
    if raw:
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(raw)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    target.write_bytes(resp.content)
                    return target
        except Exception as exc:
            logger.warning("Raw font fetch failed for %s: %s", family, exc)

    css_family = family.replace(" ", "+")
    # Try requested weight, then 400 (many display faces have no 700).
    for try_weight in (weight, "400"):
        css_url = (
            f"https://fonts.googleapis.com/css2?family={css_family}:wght@{try_weight}&display=swap"
        )
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                css = client.get(
                    css_url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        )
                    },
                )
                if css.status_code >= 400:
                    continue
                urls = re.findall(r"url\((https://[^)]+)\)", css.text)
                if not urls:
                    continue
                font_url = urls[0]
                resp = client.get(font_url)
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "")
                data = resp.content
                if "woff2" in ctype or font_url.endswith(".woff2"):
                    logger.info(
                        "Google Fonts returned woff2 for %s; trying next weight/fallback",
                        family,
                    )
                    continue
                suffix = (
                    ".otf" if font_url.endswith(".otf") or "opentype" in ctype else ".ttf"
                )
                out = cache_dir / f"{try_weight}{suffix}"
                out.write_bytes(data)
                return out
        except Exception as exc:
            logger.warning("Google Fonts fetch failed for %s @%s: %s", family, try_weight, exc)
            continue
    return None


def _known_google_ttf(family: str, bold: bool = False) -> str | None:
    """Direct TTF URLs for faces that break CSS2 weight queries (e.g. Press Start 2P)."""
    key = family.strip().lower()
    # github.com/google/fonts raw paths
    known = {
        "press start 2p": (
            "https://github.com/google/fonts/raw/main/ofl/pressstart2p/PressStart2P-Regular.ttf"
        ),
        "vt323": "https://github.com/google/fonts/raw/main/ofl/vt323/VT323-Regular.ttf",
        "silkscreen": (
            "https://github.com/google/fonts/raw/main/ofl/silkscreen/Silkscreen-Regular.ttf"
        ),
        "bebas neue": (
            "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf"
        ),
        "fredoka": (
            "https://github.com/google/fonts/raw/main/ofl/fredoka/Fredoka%5Bwdth,wght%5D.ttf"
        ),
        "noto sans bengali": (
            "https://github.com/google/fonts/raw/main/ofl/notosansbengali/NotoSansBengali%5Bwdth,wght%5D.ttf"
        ),
        "noto sans arabic": (
            "https://github.com/google/fonts/raw/main/ofl/notosansarabic/NotoSansArabic%5Bwdth,wght%5D.ttf"
        ),
        "noto sans tamil": (
            "https://github.com/google/fonts/raw/main/ofl/notosanstamil/NotoSansTamil%5Bwdth,wght%5D.ttf"
        ),
        "noto sans devanagari": (
            "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth,wght%5D.ttf"
        ),
    }
    return known.get(key)
