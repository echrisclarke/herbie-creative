from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

# creative-automation/backend/app/config.py → project root is parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env")

# Also try parent HerbieCreativeSite private/.env for local convenience
_private = PROJECT_ROOT.parent / "private" / ".env"
if _private.exists():
    load_dotenv(_private, override=False)


def get_openai_api_key() -> str | None:
    # Settings UI (private/api_keys.json) wins over .env for public installs.
    try:
        from app.user_secrets import resolve_openai_key

        return resolve_openai_key()
    except Exception:
        return os.getenv("OPENAI_API_KEY") or None


def openai_image_api() -> str:
    """Which surface to use for image work: auto | responses | images.

    auto: Responses image_generation tool first (ChatGPT path), Images API fallback.
    """
    value = (os.getenv("OPENAI_IMAGE_API", "auto") or "auto").strip().lower()
    if value not in {"auto", "responses", "images"}:
        return "auto"
    return value


def openai_responses_model() -> str:
    """Mainline model that hosts the image_generation tool (not a gpt-image-* id).

    Prefer GPT-5.6: with detail original/auto it keeps input dimensions instead of
    the gpt-5.4 high-path downsample (2.5k patches / 2048px).
    """
    return os.getenv("OPENAI_RESPONSES_MODEL", "gpt-5.6").strip() or "gpt-5.6"


def openai_image_input_detail() -> str:
    """Vision detail for Responses input_image parts: low | high | original | auto."""
    value = (os.getenv("OPENAI_IMAGE_INPUT_DETAIL", "original") or "original").strip().lower()
    if value not in {"low", "high", "original", "auto"}:
        return "original"
    return value


def openai_image_model() -> str:
    """GPT image model for Images API and the Responses image_generation tool.

    Defaults to gpt-image-2 (current Images/Vision SOTA). Override with
    OPENAI_IMAGE_MODEL (e.g. gpt-image-1.5, chatgpt-image-latest), or set
    auto to omit the tool model field and let Responses pick.
    """
    return (os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2").strip() or "gpt-image-2")


_image_quality_override: ContextVar[str | None] = ContextVar(
    "openai_image_quality_override", default=None
)


def normalize_image_quality(value: str | None) -> str:
    q = (value or "medium").strip().lower()
    if q not in {"low", "medium", "high", "auto"}:
        return "medium"
    return q


def openai_image_quality() -> str:
    """Quality for GPT image models: low | medium | high | auto.

    Per-run override (UI/CLI) wins over OPENAI_IMAGE_QUALITY env default.
    Default medium: cheaper/faster than high for iteration.
    """
    override = _image_quality_override.get()
    if override:
        return override
    return normalize_image_quality(os.getenv("OPENAI_IMAGE_QUALITY", "medium"))


@contextmanager
def image_quality_override(quality: str | None) -> Iterator[None]:
    """Temporarily override image quality for the current job/thread."""
    if quality is None:
        yield
        return
    token = _image_quality_override.set(normalize_image_quality(quality))
    try:
        yield
    finally:
        _image_quality_override.reset(token)


def openai_image_output_format() -> str:
    """Output format: jpeg (faster/cheaper transfer), png, or webp."""
    value = (os.getenv("OPENAI_IMAGE_OUTPUT_FORMAT", "jpeg") or "jpeg").strip().lower()
    if value not in {"png", "jpeg", "webp"}:
        return "jpeg"
    return value


def openai_image_output_compression() -> int:
    """Compression 0-100 for jpeg/webp. Ignored for png."""
    raw = os.getenv("OPENAI_IMAGE_OUTPUT_COMPRESSION", "85") or "85"
    try:
        value = int(raw)
    except ValueError:
        return 85
    return max(0, min(100, value))


def openai_image_input_fidelity() -> str:
    """Input fidelity for edits: low | high. High preserves product detail.

    Not sent for gpt-image-2 (always high; API rejects the param).
    """
    value = (os.getenv("OPENAI_IMAGE_INPUT_FIDELITY", "high") or "high").strip().lower()
    if value not in {"low", "high"}:
        return "high"
    return value


def openai_image_supports_input_fidelity(model: str | None = None) -> bool:
    name = (model or openai_image_model()).strip().lower()
    if name.startswith("gpt-image-2"):
        return False
    if name == "gpt-image-1-mini":
        return False
    return True


def get_xai_api_key() -> str | None:
    try:
        from app.user_secrets import resolve_xai_key

        return resolve_xai_key()
    except Exception:
        return os.getenv("XAI_API_KEY") or None


def motion_video_model() -> str:
    return (
        os.getenv("MOTION_VIDEO_MODEL", "grok-imagine-video-1.5").strip()
        or "grok-imagine-video-1.5"
    )


def motion_video_resolution() -> str:
    value = (os.getenv("MOTION_VIDEO_RESOLUTION", "720p") or "720p").strip().lower()
    if value not in {"480p", "720p", "1080p"}:
        return "720p"
    return value


def get_google_fonts_api_key() -> str | None:
    try:
        from app.user_secrets import resolve_google_fonts_key

        return resolve_google_fonts_key()
    except Exception:
        return os.getenv("GOOGLE_FONTS_API_KEY") or None


def motion_enabled_default() -> bool:
    return os.getenv("MOTION_ENABLED", "false").lower() in {"1", "true", "yes"}


def motion_duration_default() -> int:
    try:
        return int(os.getenv("MOTION_DURATION_SECONDS", "6"))
    except ValueError:
        return 6


def campaigns_root() -> Path:
    root = Path(os.getenv("CAMPAIGNS_ROOT", str(PROJECT_ROOT / "campaigns")))
    root.mkdir(parents=True, exist_ok=True)
    return root


def font_cache_root() -> Path:
    root = campaigns_root() / "_font_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def bundled_font_regular() -> Path:
    return Path(__file__).resolve().parent / "assets" / "fonts" / "OpenSans-Regular.ttf"


def bundled_font_bold() -> Path:
    bold = Path(__file__).resolve().parent / "assets" / "fonts" / "OpenSans-Bold.ttf"
    if bold.exists():
        return bold
    return bundled_font_regular()
