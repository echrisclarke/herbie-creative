from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageFilter


def crop_pad_to_size(image_bytes: bytes, width: int, height: int) -> bytes:
    """Cover-fit crop then pad if needed to exact canvas size."""
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    src_w, src_h = img.size
    target_ratio = width / height
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))

    img = img.resize((width, height), Image.Resampling.LANCZOS)
    rgb = Image.new("RGB", (width, height), (0, 0, 0))
    rgb.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
    out = BytesIO()
    rgb.save(out, format="PNG")
    return out.getvalue()


def cover_center_crop(image_bytes: bytes, width: int, height: int) -> bytes:
    """Center cover-crop to exact size (no pad). Used for ratio variants from one master."""
    return crop_pad_to_size(image_bytes, width, height)


def _contain_center_layout(
    src_w: int, src_h: int, width: int, height: int
) -> tuple[int, int, int, int]:
    """Return (new_w, new_h, offset_x, offset_y) for a centered contain fit."""
    scale = min(width / src_w, height / src_h)
    new_w = max(1, int(src_w * scale))
    new_h = max(1, int(src_h * scale))
    return new_w, new_h, (width - new_w) // 2, (height - new_h) // 2


def contain_center_on_canvas(
    image_bytes: bytes,
    width: int,
    height: int,
    *,
    transparent_margins: bool = False,
    fill: tuple[int, int, int] = (0, 0, 0),
) -> bytes:
    """Place the full source image centered on a larger canvas."""
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    src_w, src_h = img.size
    new_w, new_h, ox, oy = _contain_center_layout(src_w, src_h, width, height)
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    if transparent_margins:
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.paste(resized, (ox, oy), resized)
    else:
        canvas_rgb = Image.new("RGB", (width, height), fill)
        canvas_rgb.paste(resized.convert("RGB"), (ox, oy))
        canvas = canvas_rgb
    out = BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def contain_center_edge_extend(
    image_bytes: bytes,
    width: int,
    height: int,
    *,
    blur_radius: float = 1.2,
) -> bytes:
    """Center the master, then fill margins by clamping nearest edge pixels.

    For studio / soft backgrounds this is a much cleaner outpaint seed than
    black bars or transparency (avoids smear/mirror artifacts from the model).
    """
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    src_w, src_h = img.size
    new_w, new_h, ox, oy = _contain_center_layout(src_w, src_h, width, height)
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Build an edge-clamped canvas, then paste the sharp master on top.
    # Left/right: repeat leftmost/rightmost column of the resized master.
    # Top/bottom: repeat top/bottom row (including already-extended sides).
    canvas = Image.new("RGB", (width, height))
    canvas.paste(resized, (ox, oy))

    left_col = resized.crop((0, 0, 1, new_h))
    right_col = resized.crop((new_w - 1, 0, new_w, new_h))
    if ox > 0:
        left_band = left_col.resize((ox, new_h), Image.Resampling.NEAREST)
        canvas.paste(left_band, (0, oy))
    right_w = width - (ox + new_w)
    if right_w > 0:
        right_band = right_col.resize((right_w, new_h), Image.Resampling.NEAREST)
        canvas.paste(right_band, (ox + new_w, oy))

    # After side fill, extend top/bottom across full width from current rows
    if oy > 0:
        top_row = canvas.crop((0, oy, width, oy + 1))
        top_band = top_row.resize((width, oy), Image.Resampling.NEAREST)
        canvas.paste(top_band, (0, 0))
    bot_h = height - (oy + new_h)
    if bot_h > 0:
        bot_row = canvas.crop((0, oy + new_h - 1, width, oy + new_h))
        bot_band = bot_row.resize((width, bot_h), Image.Resampling.NEAREST)
        canvas.paste(bot_band, (0, oy + new_h))

    if blur_radius > 0:
        # Soften only the margin regions so clamp bands don't look striped
        soft = canvas.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        canvas.paste(resized, (ox, oy))  # keep master sharp
        # Re-apply soft margins
        if oy > 0:
            canvas.paste(soft.crop((0, 0, width, oy)), (0, 0))
        if bot_h > 0:
            canvas.paste(
                soft.crop((0, oy + new_h, width, height)),
                (0, oy + new_h),
            )
        if ox > 0:
            canvas.paste(soft.crop((0, oy, ox, oy + new_h)), (0, oy))
        if right_w > 0:
            canvas.paste(
                soft.crop((ox + new_w, oy, width, oy + new_h)),
                (ox + new_w, oy),
            )
        canvas.paste(resized, (ox, oy))

    out = BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def outpaint_margin_mask(
    width: int,
    height: int,
    master_w: int,
    master_h: int,
) -> bytes:
    """PNG mask: transparent = edit (margins), opaque = keep (centered master)."""
    new_w, new_h, ox, oy = _contain_center_layout(master_w, master_h, width, height)
    mask = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    keep = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 255))
    mask.paste(keep, (ox, oy))
    out = BytesIO()
    mask.save(out, format="PNG")
    return out.getvalue()


def lock_master_in_center(
    expanded_bytes: bytes,
    master_bytes: bytes,
    width: int,
    height: int,
) -> bytes:
    """Hard-paste the 1:1 master into the exact center (no feather ghosts)."""
    expanded = Image.open(BytesIO(expanded_bytes)).convert("RGB")
    if expanded.size != (width, height):
        expanded = expanded.resize((width, height), Image.Resampling.LANCZOS)
    master = Image.open(BytesIO(master_bytes)).convert("RGB")
    new_w, new_h, ox, oy = _contain_center_layout(
        master.size[0], master.size[1], width, height
    )
    patched = expanded.copy()
    patched.paste(
        master.resize((new_w, new_h), Image.Resampling.LANCZOS),
        (ox, oy),
    )
    out = BytesIO()
    patched.save(out, format="PNG")
    return out.getvalue()
