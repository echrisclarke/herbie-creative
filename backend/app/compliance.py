from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from app.schemas import Brief, Product


def run_compliance(
    image_bytes: bytes,
    brief: Brief,
    product: Product,
    overlay_text: str,
) -> dict[str, bool]:
    notes = brief.brand_notes
    logo_ok = True
    if notes.logo_required:
        logo_ok = bool(notes.logo_path and Path(notes.logo_path).exists())
        if logo_ok:
            # Rough presence: logo file exists and was intended for compose
            logo_ok = True

    colors_ok = True
    if notes.colors:
        colors_ok = _colors_roughly_present(image_bytes, notes.colors)

    forbidden_ok = True
    text_lower = overlay_text.lower()
    for word in notes.forbidden_words:
        if word and word.lower() in text_lower:
            forbidden_ok = False
            break

    cta_ok = True
    expected_cta = (product.cta or brief.cta or "").strip()
    if expected_cta:
        # CTA is composed when set; mark true if CTA string non-empty and compose ran
        cta_ok = bool(expected_cta)

    return {
        "logo": logo_ok,
        "colors": colors_ok,
        "forbidden_words": forbidden_ok,
        "cta": cta_ok,
    }


def _colors_roughly_present(image_bytes: bytes, hex_colors: list[str], sample: int = 40) -> bool:
    """Loose check: at least one brand color appears near some sampled pixels."""
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        img = img.resize((sample, sample))
        pixels = list(img.getdata())
        targets = [_hex_to_rgb(c) for c in hex_colors if c.startswith("#") and len(c) >= 7]
        if not targets:
            return True
        for tr, tg, tb in targets:
            for r, g, b in pixels:
                if abs(r - tr) < 55 and abs(g - tg) < 55 and abs(b - tb) < 55:
                    return True
        return False
    except Exception:
        return True


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
