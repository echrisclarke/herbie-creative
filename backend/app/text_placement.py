"""Default caption placement by aspect ratio.

Horizontal 16:9 gets top-right so the caption sits in the open sky/wall band
instead of fighting the product along the bottom. Square and Stories keep
bottom-center. Per-ratio overrides on the brief always win.
"""

from __future__ import annotations

DEFAULT_TEXT_PLACEMENT = "bottom-center"

DEFAULT_TEXT_PLACEMENT_BY_RATIO: dict[str, str] = {
    "1:1": "bottom-center",
    "9:16": "bottom-center",
    "16:9": "top-right",
}


def base_output_ratio(ratio: str | None) -> str:
    """Map '16:9-tight' / '16:9' → '16:9'."""
    raw = (ratio or "").strip()
    for known in ("16:9", "9:16", "1:1"):
        if raw == known or raw.startswith(f"{known}-"):
            return known
    if "-" in raw:
        return raw.split("-", 1)[0] or "1:1"
    return raw or "1:1"


def default_text_placement_for_ratio(ratio: str | None) -> str:
    return DEFAULT_TEXT_PLACEMENT_BY_RATIO.get(
        base_output_ratio(ratio), DEFAULT_TEXT_PLACEMENT
    )


def resolve_text_placement(
    ratio: str | None,
    *,
    by_ratio: dict[str, str] | None = None,
    placement_key: str | None = None,
    fallback: str | None = None,
) -> str:
    """Resolve caption band for a still.

    Priority: explicit by_ratio key → by_ratio for this ratio → built-in
    ratio default (16:9 top-right) → campaign fallback → bottom-center.
    """
    mapping = {str(k): str(v) for k, v in (by_ratio or {}).items() if v}
    base = base_output_ratio(ratio)
    key = (placement_key or ratio or base).strip()
    for candidate in (key, ratio, base):
        if candidate and candidate in mapping:
            return mapping[candidate]
    return (
        default_text_placement_for_ratio(base)
        or (fallback or "").strip()
        or DEFAULT_TEXT_PLACEMENT
    )
