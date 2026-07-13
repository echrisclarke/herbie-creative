from __future__ import annotations

from pathlib import Path

from slugify import slugify

from app.config import campaigns_root
from app.schemas import RATIO_FOLDER


def slugify_name(value: str) -> str:
    return slugify(value) or "item"


def ratio_folder(ratio: str) -> str:
    return RATIO_FOLDER.get(ratio, ratio.replace(":", "x"))


def campaign_dir(campaign_slug: str) -> Path:
    path = campaigns_root() / campaign_slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def output_dir(
    campaign_slug: str,
    market_slug: str,
    product_slug: str,
    ratio: str,
) -> Path:
    path = (
        campaign_dir(campaign_slug)
        / "outputs"
        / market_slug
        / product_slug
        / ratio_folder(ratio)
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def output_path(
    campaign_slug: str,
    market_slug: str,
    product_slug: str,
    ratio: str,
    filename: str = "final.png",
) -> Path:
    return output_dir(campaign_slug, market_slug, product_slug, ratio) / filename


def locale_slug(locale: str) -> str:
    return slugify_name(locale.replace("_", "-")) or "en-us"
