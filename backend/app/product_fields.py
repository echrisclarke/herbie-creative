"""Resolve per-product copy and scene overrides against campaign brief defaults."""

from __future__ import annotations

from app.schemas import Brief, Product


def product_message(brief: Brief, product: Product) -> str:
    return (product.message or brief.message or "").strip()


def product_cta(brief: Brief, product: Product) -> str:
    return (product.cta or brief.cta or "").strip()


def product_supporting(brief: Brief, product: Product) -> str:
    return (product.supporting_copy or brief.supporting_copy or "").strip()


def product_direction(brief: Brief, product: Product) -> str:
    return (product.creative_direction or brief.creative_direction or "").strip()


def product_style_paths(brief: Brief, product: Product) -> list[str]:
    if product.style_reference_paths:
        return list(product.style_reference_paths)
    return list(brief.style_reference_paths or [])


def product_background_paths(brief: Brief, product: Product) -> list[str]:
    if product.background_reference_paths:
        return list(product.background_reference_paths)
    return list(brief.background_reference_paths or [])
