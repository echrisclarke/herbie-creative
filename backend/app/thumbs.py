"""On-demand image thumbnails with disk cache (grids never download full creatives)."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.config import campaigns_base, data_root, hosted_mode
from app.public_examples import examples_root

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_SRC_RE = re.compile(r"^/(outputs|examples|sample-assets|brand)/", re.I)


def thumb_cache_root() -> Path:
    root = data_root() / ".cache" / "thumbs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def clamp_edge(value: int | None, default: int = 480) -> int:
    try:
        edge = int(value if value is not None else default)
    except (TypeError, ValueError):
        edge = default
    return max(64, min(edge, 720))


def normalize_src(src: str) -> str:
    text = (src or "").strip().replace("\\", "/")
    if not text:
        raise ValueError("Missing image path")
    if "://" in text:
        raise ValueError("Remote URLs are not allowed")
    if text.startswith("/pipeline/"):
        text = text[len("/pipeline") :]
    if not text.startswith("/"):
        text = f"/{text}"
    # Drop query/hash if a full path was pasted
    text = text.split("?", 1)[0].split("#", 1)[0]
    if ".." in text.split("/"):
        raise ValueError("Invalid image path")
    if not _SRC_RE.match(text):
        raise ValueError("Image path must be under /outputs, /examples, /sample-assets, or /brand")
    return text


def resolve_source(src: str, *, user_id: str | None) -> Path:
    """Resolve a public app path to a file on disk; enforce tenant isolation when hosted."""
    text = normalize_src(src)
    if text.startswith("/examples/"):
        root = examples_root()
        if root is None:
            raise FileNotFoundError("Examples not available")
        rel = text[len("/examples/") :]
        path = (root / rel).resolve()
        if not str(path).startswith(str(root.resolve())) or not path.is_file():
            raise FileNotFoundError("Image not found")
        return path

    if text.startswith("/sample-assets/"):
        from app.config import PROJECT_ROOT

        root = (PROJECT_ROOT / "sample-assets").resolve()
        rel = text[len("/sample-assets/") :]
        path = (root / rel).resolve()
        if not str(path).startswith(str(root)) or not path.is_file():
            raise FileNotFoundError("Image not found")
        return path

    if text.startswith("/brand/"):
        from app.config import PROJECT_ROOT

        for root in (
            (PROJECT_ROOT / "frontend" / "dist" / "brand").resolve(),
            (PROJECT_ROOT / "frontend" / "public" / "brand").resolve(),
        ):
            if not root.is_dir():
                continue
            rel = text[len("/brand/") :]
            path = (root / rel).resolve()
            if str(path).startswith(str(root)) and path.is_file():
                return path
        raise FileNotFoundError("Image not found")

    # /outputs/...
    base = campaigns_base().resolve()
    rel = text[len("/outputs/") :]
    path = (base / rel).resolve()
    if not str(path).startswith(str(base)) or not path.is_file():
        raise FileNotFoundError("Image not found")
    if hosted_mode():
        if not user_id:
            raise PermissionError("Sign in required")
        user_root = (base / user_id).resolve()
        if not str(path).startswith(str(user_root)):
            raise PermissionError("Sign in required")
    return path


def ensure_thumb(source: Path, max_edge: int) -> Path:
    if source.suffix.lower() not in _IMAGE_EXTS:
        raise ValueError("Not an image file")

    stat = source.stat()
    key = hashlib.sha1(
        f"{source.resolve()}|{stat.st_mtime_ns}|{stat.st_size}|{max_edge}|v1".encode("utf-8")
    ).hexdigest()
    cached = thumb_cache_root() / f"{key}.webp"
    if cached.is_file() and cached.stat().st_size > 0:
        return cached

    from PIL import Image, ImageOps

    with Image.open(source) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
        im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        if im.mode == "RGBA":
            background = Image.new("RGB", im.size, (18, 18, 18))
            background.paste(im, mask=im.split()[-1])
            im = background
        elif im.mode != "RGB":
            im = im.convert("RGB")
        tmp = cached.with_suffix(".tmp.webp")
        im.save(tmp, format="WEBP", quality=72, method=4)
        tmp.replace(cached)
    return cached


def is_public_src(src: str) -> bool:
    try:
        text = normalize_src(src)
    except ValueError:
        return False
    return text.startswith(("/examples/", "/brand/", "/sample-assets/"))
