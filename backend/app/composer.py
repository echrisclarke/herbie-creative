from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.providers.fonts import resolve_font_path
from app.schemas import BrandNotes, SlotRenderChoices

# Base layout template per aspect ratio (percent of canvas). Text band is remapped
# by BrandNotes.text_placement (top / middle / bottom × left / center / right).
LAYOUT_TEMPLATES: dict[str, dict[str, dict[str, float]]] = {
    "1:1": {
        "logo": {"x": 0.045, "y": 0.045, "w": 0.22, "h": 0.09},
        "headline": {"x": 0.08, "y": 0.72, "w": 0.84, "h": 0.14},
        "supporting": {"x": 0.08, "y": 0.66, "w": 0.84, "h": 0.06},
        "cta": {"x": 0.08, "y": 0.88, "w": 0.84, "h": 0.06},
        "legal": {"x": 0.08, "y": 0.94, "w": 0.84, "h": 0.04},
    },
    "9:16": {
        "logo": {"x": 0.08, "y": 0.06, "w": 0.28, "h": 0.07},
        "headline": {"x": 0.08, "y": 0.70, "w": 0.84, "h": 0.12},
        "supporting": {"x": 0.08, "y": 0.64, "w": 0.84, "h": 0.05},
        "cta": {"x": 0.08, "y": 0.84, "w": 0.84, "h": 0.05},
        "legal": {"x": 0.08, "y": 0.90, "w": 0.84, "h": 0.04},
    },
    "16:9": {
        "logo": {"x": 0.04, "y": 0.06, "w": 0.18, "h": 0.10},
        "headline": {"x": 0.07, "y": 0.72, "w": 0.86, "h": 0.12},
        "supporting": {"x": 0.07, "y": 0.66, "w": 0.86, "h": 0.05},
        "cta": {"x": 0.07, "y": 0.86, "w": 0.86, "h": 0.06},
        "legal": {"x": 0.07, "y": 0.93, "w": 0.86, "h": 0.04},
    },
}

SAFE_ZONES = {
    "9:16": {"bottom": 0.22, "side": 0.08},
    "1:1": {"bottom": 0.20, "side": 0.08},
    "16:9": {"bottom": 0.18, "side": 0.07},
}

TEXT_PLACEMENTS = {
    "bottom-left",
    "bottom-center",
    "bottom-right",
    "middle-left",
    "middle-center",
    "middle-right",
    "top-left",
    "top-center",
    "top-right",
    "none",
}


def compose_message(
    image_bytes: bytes,
    message: str,
    ratio: str,
    brand_notes: BrandNotes | None = None,
    cta: str = "",
    *,
    supporting: str = "",
    legal: str = "",
    slot_render: SlotRenderChoices | None = None,
) -> bytes:
    """Deterministic Pillow overlay into placement-aware regions per ratio."""
    brand_notes = brand_notes or BrandNotes()
    slots = slot_render or SlotRenderChoices()
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    width, height = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    placement = (brand_notes.text_placement or "bottom-center").strip().lower()
    if placement not in TEXT_PLACEMENTS:
        placement = "bottom-center"
    skip_caption = placement == "none"
    template, align = _template_for_placement(ratio, placement)

    legal_text = (legal or "").strip()
    # Never paint the disclaimer as caption if it leaked into message/supporting.
    if legal_text and slots.legal == "pillow":
        if supporting.strip() == legal_text:
            supporting = ""
        if message.strip() == legal_text:
            message = ""

    scrim_on = True if brand_notes.text_scrim is None else bool(brand_notes.text_scrim)
    scrim_opacity = _clamp01(brand_notes.text_scrim_opacity, default=0.65)
    draw_text = not skip_caption and (
        (message and slots.headline == "pillow")
        or (cta and slots.cta == "pillow")
        or (supporting and slots.supporting == "pillow")
    )
    if scrim_on and scrim_opacity > 0.01 and draw_text:
        _draw_scrim(draw, width, height, placement, template, scrim_opacity)

    sample = f"{message} {cta} {supporting} {legal_text}".strip()
    font_path = resolve_font_path(
        font_names=brand_notes.font_names,
        font_file_path=brand_notes.font_file_path,
        bold=True,
        sample_text=sample,
    )
    cta_path = resolve_font_path(
        font_names=brand_notes.font_names,
        font_file_path=brand_notes.font_file_path,
        bold=False,
        sample_text=sample,
    )
    accent = _pick_accent(brand_notes.colors)
    text_rgb = _parse_hex_color(brand_notes.text_color) or (255, 255, 255)
    shadow_opacity = _clamp01(brand_notes.text_shadow_opacity, default=0.6)
    shadow_alpha = int(160 * shadow_opacity)

    if not skip_caption:
        if supporting.strip() and slots.supporting == "pillow":
            box = template["supporting"]
            _draw_in_box(
                overlay,
                draw,
                supporting.strip(),
                box,
                width,
                height,
                font_path,
                size_frac=0.028,
                fill=(*text_rgb, 220),
                shadow_alpha=shadow_alpha,
                bold=False,
                uppercase=False,
                align=align,
            )
            draw = ImageDraw.Draw(overlay)

        if message.strip() and slots.headline == "pillow":
            box = template["headline"]
            _draw_in_box(
                overlay,
                draw,
                message.strip(),
                box,
                width,
                height,
                font_path,
                size_frac=0.048,
                fill=(*text_rgb, 255),
                shadow_alpha=shadow_alpha,
                bold=True,
                uppercase=False,
                align=align,
            )
            draw = ImageDraw.Draw(overlay)

        if cta.strip() and slots.cta == "pillow":
            box = template["cta"]
            _draw_in_box(
                overlay,
                draw,
                cta.strip().upper(),
                box,
                width,
                height,
                cta_path,
                size_frac=0.028,
                fill=(*accent, 255),
                shadow_alpha=shadow_alpha,
                bold=False,
                uppercase=True,
                align=align,
            )
            draw = ImageDraw.Draw(overlay)

    # Dedicated bottom footer: never uses caption text_placement boxes.
    if legal_text and slots.legal == "pillow":
        side = SAFE_ZONES.get(ratio, {"side": 0.08}).get("side", 0.08)
        legal_align = (getattr(brand_notes, "legal_placement", None) or "left").strip().lower()
        if legal_align not in {"left", "center", "right"}:
            legal_align = "left"
        legal_box = {
            "x": side,
            "y": 0.905,
            "w": 1.0 - 2 * side,
            "h": 0.085,
        }
        _draw_in_box(
            overlay,
            draw,
            legal_text,
            legal_box,
            width,
            height,
            cta_path,
            size_frac=0.015,
            fill=(200, 200, 200, 200),
            shadow_alpha=0,
            bold=False,
            uppercase=False,
            align=legal_align,
            valign="bottom",
        )

    if brand_notes.logo_path and slots.logo == "pillow":
        logo_file = Path(brand_notes.logo_path)
        if logo_file.exists():
            # Corner placement on the full canvas (do not clamp to the
            # top-left template logo box, or bottom/right never move).
            _paste_logo(
                overlay,
                logo_file,
                brand_notes.logo_placement,
                width,
                height,
                logo_color=brand_notes.logo_color,
                region=None,
                logo_shadow_opacity=float(brand_notes.logo_shadow_opacity or 0.0),
                logo_opacity=(
                    1.0
                    if brand_notes.logo_opacity is None
                    else float(brand_notes.logo_opacity)
                ),
                logo_scale=(
                    1.0 if brand_notes.logo_scale is None else float(brand_notes.logo_scale)
                ),
            )

    composed = Image.alpha_composite(img, overlay).convert("RGB")
    out = BytesIO()
    composed.save(out, format="PNG")
    return out.getvalue()


def _template_for_placement(
    ratio: str, placement: str
) -> tuple[dict[str, dict[str, float]], str]:
    # Legal footer stays bottom full-width; only the caption band moves with placement.
    base = LAYOUT_TEMPLATES.get(ratio, LAYOUT_TEMPLATES["1:1"])
    template = {k: dict(v) for k, v in base.items()}
    # Pin legal to the bottom band from the base layout (independent of caption).
    legal_base = dict(base["legal"])
    side = SAFE_ZONES.get(ratio, {"side": 0.08})["side"]
    legal_base["x"] = side
    legal_base["w"] = 1.0 - 2 * side
    template["legal"] = legal_base

    if placement == "none":
        return template, "center"

    parts = placement.split("-", 1)
    v_band = parts[0] if parts else "bottom"
    h_align = parts[1] if len(parts) > 1 else "center"
    if h_align not in {"left", "center", "right"}:
        h_align = "center"

    full_w = 1.0 - 2 * side
    half_w = min(0.58, full_w)

    def h_box() -> tuple[float, float]:
        if h_align == "left":
            return side, half_w
        if h_align == "right":
            return 1.0 - side - half_w, half_w
        return side, full_w

    if v_band == "top":
        ys = {
            "supporting": 0.14,
            "headline": 0.20,
            "cta": 0.34,
        }
    elif v_band == "middle":
        ys = {
            "supporting": 0.40,
            "headline": 0.46,
            "cta": 0.60,
        }
    else:
        ys = {
            "supporting": base["supporting"]["y"],
            "headline": base["headline"]["y"],
            "cta": base["cta"]["y"],
        }

    for key in ("supporting", "headline", "cta"):
        x, w = h_box()
        template[key]["x"] = x
        template[key]["w"] = w
        template[key]["y"] = ys[key]

    return template, h_align


def _draw_scrim(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    placement: str,
    template: dict[str, dict[str, float]],
    scrim_opacity: float,
) -> None:
    """Full-width gradient band covering the caption stack (not bottom legal)."""
    v_band = placement.split("-", 1)[0] if placement != "none" else "bottom"
    keys = ("supporting", "headline", "cta")
    ys = [template[k]["y"] for k in keys if k in template]
    hs = [template[k]["h"] for k in keys if k in template]
    if not ys:
        ys = [0.72]
        hs = [0.14]
    top_frac = max(0.0, min(ys) - 0.04)
    bottom_frac = min(1.0, max(y + h for y, h in zip(ys, hs)) + 0.05)
    if v_band == "top":
        top_frac = 0.0
        bottom_frac = max(bottom_frac, 0.42)
    elif v_band == "middle":
        top_frac = max(0.28, top_frac - 0.02)
        bottom_frac = min(0.78, bottom_frac + 0.02)
    else:
        top_frac = min(top_frac, 0.62)
        bottom_frac = 1.0

    y0 = int(height * top_frac)
    y1 = int(height * bottom_frac)
    band_h = max(1, y1 - y0)
    for i in range(band_h):
        t = i / max(1, band_h - 1)
        if v_band == "top":
            strength = 1.0 - (t**1.25)
        elif v_band == "middle":
            strength = 1.0 - abs(t - 0.5) * 2
        else:
            strength = t**1.25
        alpha = int((25 + 175 * max(0.0, strength)) * scrim_opacity)
        if alpha <= 0:
            continue
        yy = y0 + i
        if 0 <= yy < height:
            draw.line([(0, yy), (width, yy)], fill=(0, 0, 0, alpha))


def _draw_in_box(
    overlay: Image.Image,
    draw: ImageDraw.ImageDraw,
    text: str,
    box: dict[str, float],
    width: int,
    height: int,
    font_path: Path,
    *,
    size_frac: float,
    fill: tuple[int, int, int, int],
    shadow_alpha: int,
    bold: bool,
    uppercase: bool,
    align: str = "center",
    valign: str = "middle",
) -> None:
    del bold, uppercase  # font already resolved
    anchor = "lt"
    x0 = int(width * box["x"])
    y0 = int(height * box["y"])
    max_w = int(width * box["w"])
    max_h = int(height * box["h"])
    font_size = max(14, int(height * size_frac))
    font = ImageFont.truetype(str(font_path), font_size)
    lines = _wrap_text(draw, text, font, max_w)
    line_gap = max(4, int(font_size * 0.22))
    rows: list[tuple[str, int]] = []
    for i, part in enumerate(lines):
        adv = _line_advance(draw, part, font, anchor)
        gap = line_gap if i < len(lines) - 1 else 0
        rows.append((part, adv + gap))
    total_h = sum(s for _, s in rows)
    if total_h > max_h and rows:
        scale = max(0.45, (max_h / total_h) * 0.92)
        font_size = max(10, int(font_size * scale))
        font = ImageFont.truetype(str(font_path), font_size)
        line_gap = max(2, int(font_size * 0.18))
        lines = _wrap_text(draw, text, font, max_w)
        rows = []
        for i, part in enumerate(lines):
            adv = _line_advance(draw, part, font, anchor)
            gap = line_gap if i < len(lines) - 1 else 0
            rows.append((part, adv + gap))
        total_h = sum(s for _, s in rows)
        # If still too tall, drop trailing lines rather than overflowing upward.
        while rows and sum(s for _, s in rows) > max_h:
            rows.pop()
        total_h = sum(s for _, s in rows)

    if valign == "bottom":
        y = y0 + max(0, max_h - total_h)
    elif valign == "top":
        y = y0
    else:
        y = y0 + max(0, (max_h - total_h) // 2)
    for part, step in rows:
        bbox = draw.textbbox((0, 0), part, font=font, anchor=anchor)
        tw = bbox[2] - bbox[0]
        if align == "left":
            x = x0
        elif align == "right":
            x = x0 + max(0, max_w - tw)
        else:
            x = x0 + max(0, (max_w - tw) // 2)
        if shadow_alpha > 0:
            shadow = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
            sdraw = ImageDraw.Draw(shadow)
            sdraw.text(
                (x + 2, y + 2),
                part,
                font=font,
                fill=(0, 0, 0, shadow_alpha),
                anchor=anchor,
            )
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=2))
            overlay.alpha_composite(shadow)
            draw = ImageDraw.Draw(overlay)
        draw.text((x, y), part, font=font, fill=fill, anchor=anchor)
        y += step


def _clamp01(value: float | None, *, default: float) -> float:
    if value is None:
        return default
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _line_advance(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    anchor: str,
) -> int:
    """Ink height for one line when drawn with the given anchor (use with anchor='lt')."""
    bbox = draw.textbbox((0, 0), text, font=font, anchor=anchor)
    return max(1, bbox[3] - bbox[1])


def _parse_hex_color(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    raw = value.strip().lower()
    if raw in {"original", "none", "as-is"}:
        return None
    hexv = raw.lstrip("#")
    if len(hexv) != 6:
        return None
    try:
        return int(hexv[0:2], 16), int(hexv[2:4], 16), int(hexv[4:6], 16)
    except ValueError:
        return None


def _pick_accent(colors: list[str]) -> tuple[int, int, int]:
    for raw in colors or []:
        parsed = _parse_hex_color(raw)
        if parsed:
            return parsed
    return (230, 230, 230)


def _tint_logo(logo: Image.Image, color: tuple[int, int, int] | None) -> Image.Image:
    """Recolor opaque pixels; keep alpha. None = leave original RGB."""
    if color is None:
        return logo
    rgba = logo.convert("RGBA")
    r, g, b = color
    pixels = rgba.load()
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            pr, pg, pb, pa = pixels[x, y]
            if pa <= 0:
                continue
            # Flat marks (near black/white/grey): replace RGB, keep alpha
            if max(pr, pg, pb) - min(pr, pg, pb) < 40:
                pixels[x, y] = (r, g, b, pa)
    return rgba


def _wrap_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int
) -> list[str]:
    # Prefer character wrap for CJK (few spaces)
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return _wrap_cjk(draw, text, font, max_width)
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _wrap_cjk(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int
) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in text:
        trial = current + ch
        bbox = draw.textbbox((0, 0), trial, font=font)
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(current)
            current = ch
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def _paste_logo(
    canvas: Image.Image,
    logo_path: Path,
    placement: str,
    width: int,
    height: int,
    logo_color: str | None = None,
    region: dict[str, float] | None = None,
    *,
    logo_shadow_opacity: float = 0.0,
    logo_opacity: float = 1.0,
    logo_scale: float = 1.0,
) -> None:
    logo = Image.open(logo_path).convert("RGBA")
    if logo_color and logo_color.strip().lower() in {"original", "none", "as-is"}:
        tint = None
    else:
        tint = _parse_hex_color(logo_color) or (255, 255, 255)
    logo = _tint_logo(logo, tint)
    scale_mul = max(0.35, min(2.5, float(logo_scale or 1.0)))
    opacity = _clamp01(logo_opacity, default=1.0)
    shadow_op = _clamp01(logo_shadow_opacity, default=0.0)
    if region:
        max_h = max(28, int(height * region["h"] * scale_mul))
        max_w = max(28, int(width * region["w"] * scale_mul))
        scale = min(max_h / logo.height, max_w / logo.width)
        new_size = (max(1, int(logo.width * scale)), max(1, int(logo.height * scale)))
        logo = logo.resize(new_size, Image.Resampling.LANCZOS)
        rx = int(width * region["x"])
        ry = int(height * region["y"])
        if placement == "top-right":
            pos = (rx + max_w - logo.width, ry)
        elif placement == "bottom-left":
            pos = (rx, ry + max_h - logo.height)
        elif placement == "bottom-right":
            pos = (rx + max_w - logo.width, ry + max_h - logo.height)
        else:
            pos = (rx, ry)
    else:
        max_h = max(28, int(height * 0.09 * scale_mul))
        scale = max_h / logo.height
        new_size = (max(1, int(logo.width * scale)), max_h)
        logo = logo.resize(new_size, Image.Resampling.LANCZOS)
        margin = int(min(width, height) * 0.045)
        if placement == "top-right":
            pos = (width - logo.width - margin, margin)
        elif placement == "bottom-left":
            pos = (margin, height - logo.height - margin)
        elif placement == "bottom-right":
            pos = (width - logo.width - margin, height - logo.height - margin)
        else:
            pos = (margin, margin)

    if opacity < 0.999:
        r, g, b, a = logo.split()
        a = a.point(lambda v: int(v * opacity))
        logo = Image.merge("RGBA", (r, g, b, a))

    if shadow_op > 0.01:
        _r, _g, _b, a = logo.split()
        shadow = Image.new("RGBA", logo.size, (0, 0, 0, 0))
        shadow.putalpha(a.point(lambda v: int(v * shadow_op * 0.9)))
        blur = max(1, logo.height // 18)
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=blur))
        offset = max(1, logo.height // 22)
        canvas.paste(shadow, (pos[0] + offset, pos[1] + offset), shadow)

    canvas.paste(logo, pos, logo)
