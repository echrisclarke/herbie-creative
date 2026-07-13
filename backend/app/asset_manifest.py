from __future__ import annotations

from pathlib import Path

from app.config import PROJECT_ROOT
from app.schemas import AssetManifest, AssetStatus, Brief, Product, ProductMode
from app.storage.paths import slugify_name


def build_asset_manifest(brief: Brief, base_dir: Path | None = None) -> AssetManifest:
    base = base_dir or PROJECT_ROOT
    statuses: list[AssetStatus] = []
    blockers: list[str] = []

    for product in brief.products:
        paths = resolve_product_asset_paths(product, base)
        has_image = bool(paths)
        missing_message = None
        if product.product_mode == ProductMode.USE_PROVIDED and not has_image:
            missing_message = "This product needs an uploaded image before generation."
            blockers.append(f"{product.name}: {missing_message}")
        statuses.append(
            AssetStatus(
                product_name=product.name,
                product_mode=product.product_mode,
                has_image=has_image,
                path=paths[0] if paths else product.input_asset_path,
                paths=paths,
                missing_message=missing_message,
            )
        )

    logo_path = None
    if brief.brand_notes.logo_path:
        logo_resolved = _resolve_path(brief.brand_notes.logo_path, base)
        if logo_resolved and logo_resolved.exists():
            logo_path = str(logo_resolved)
        elif brief.brand_notes.logo_required:
            blockers.append("Logo is required but missing.")

    return AssetManifest(
        products=statuses,
        logo_path=logo_path,
        ready=len(blockers) == 0,
        blockers=blockers,
    )


def resolve_product_asset_paths(product: Product, base: Path | None = None) -> list[str]:
    """Hero first (input_asset_path), then extra references (input_asset_paths)."""
    base = base or PROJECT_ROOT
    ordered: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        resolved = _resolve_path(value, base)
        if not resolved or not resolved.exists():
            return
        key = str(resolved.resolve())
        if key in seen:
            return
        seen.add(key)
        ordered.append(str(resolved))

    add(product.input_asset_path)
    for extra in product.input_asset_paths:
        add(extra)
    return ordered


def resolve_path(value: str | None, base: Path | None = None) -> Path | None:
    return _resolve_path(value, base or PROJECT_ROOT)


def _resolve_path(value: str | None, base: Path) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute() and path.exists():
        return path
    candidate = (base / value).resolve()
    if candidate.exists():
        return candidate
    cwd_candidate = Path.cwd() / value
    if cwd_candidate.exists():
        return cwd_candidate.resolve()
    return candidate if path.suffix else None


def product_slug(name: str) -> str:
    return slugify_name(name)
