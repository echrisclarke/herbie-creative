"""Canonical sample briefs for in-app Load / Run sample."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from app.asset_manifest import build_asset_manifest
from app.brief_loader import missing_required_fields
from app.config import PROJECT_ROOT
from app.schemas import Brief
from app.storage.paths import campaign_dir, slugify_name

# Demo-ready samples (no brand-specific code; data only).
# Order = Intake UI order. Lead with Jordan hero zoom, then other demos.
SAMPLE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "jordan-hero-zoom",
        "title": "Jordan hero zoom",
        "brief": "sample-briefs/jordan-hero-zoom.json",
        "description": (
            "Featured demo (same as Local CLI): Frozen Moments AJ4 + Shattered Backboard AJ1 "
            "with separate copy and scenes each; 1:1 / 9:16 / 16:9; en/es/zh finals with "
            "message + CTA + legal."
        ),
    },
    {
        "id": "jordan-candid",
        "title": "Jordan Frozen Moments (candid)",
        "brief": "sample-briefs/jordan-frozen-moments-candid.json",
        "description": "Candid streetwear hero with product refs staged from sample-assets.",
    },
    {
        "id": "jordan-shattered-candid",
        "title": "Jordan Shattered Backboard (candid)",
        "brief": "sample-briefs/jordan-shattered-backboard-candid.json",
        "description": "Person wearing AJ1 Shattered Backboard (2025); separate lifestyle sample.",
    },
    {
        "id": "jordan-clara-candid",
        "title": "Jordan Clara studio candid",
        "brief": "sample-briefs/jordan-candid-daytime-clara.json",
        "description": "Studio candid with Clara likeness + AJ4 product refs.",
    },
    {
        "id": "cardobot",
        "title": "Card-o-Bot (deck + app)",
        "brief": "sample-briefs/cardobot.json",
        "description": "Two products: printed deck + app-on-device, with staged refs.",
    },
    {
        "id": "cardobot-apartment-deck",
        "title": "Card-o-Bot apartment deck",
        "brief": "sample-briefs/cardobot-apartment-deck.json",
        "description": "Apartment coffee-table deck scene.",
    },
    {
        "id": "cardobot-hologram-deal",
        "title": "Card-o-Bot hologram deal",
        "brief": "sample-briefs/cardobot-hologram-deal.json",
        "description": "Hologram / device UI creative track.",
    },
    {
        "id": "spitfire-deathmask-us",
        "title": "Spitfire Deathmask II (US)",
        "brief": "sample-briefs/spitfire-deathmask-us.json",
        "description": "Optional extra: two skate products with logo + refs.",
    },
]


def list_sample_catalog() -> list[dict[str, Any]]:
    out = []
    for item in SAMPLE_CATALOG:
        path = PROJECT_ROOT / item["brief"]
        out.append({**item, "available": path.exists()})
    return out


def _resolve_src(raw: str) -> Path | None:
    path = Path(raw)
    if path.is_absolute():
        return path if path.exists() else None
    candidate = PROJECT_ROOT / raw
    return candidate if candidate.exists() else None


def _copy_asset(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return dest


def _stage(raw: str | None, dest_dir: Path, *, required: bool = False) -> str | None:
    if not raw:
        if required:
            raise FileNotFoundError("Sample asset path is empty")
        return None
    src = _resolve_src(raw)
    if not src:
        if required:
            raise FileNotFoundError(f"Sample asset missing: {raw}")
        return None
    return str(_copy_asset(src, dest_dir))


def create_campaign_from_sample(sample_id: str) -> dict[str, Any]:
    meta = next((s for s in SAMPLE_CATALOG if s["id"] == sample_id), None)
    if meta is None:
        raise FileNotFoundError(f"Unknown sample: {sample_id}")
    brief_path = PROJECT_ROOT / meta["brief"]
    if not brief_path.exists():
        raise FileNotFoundError(f"Brief not found: {meta['brief']}")

    brief = Brief.model_validate_json(brief_path.read_text(encoding="utf-8"))
    campaign_id = f"{slugify_name(brief.campaign_name)}-{uuid.uuid4().hex[:8]}"
    cdir = campaign_dir(campaign_id)
    uploads = cdir / "uploads"
    role_dirs = {
        "logo": uploads / "logo",
        "product": uploads / "product",
        "style": uploads / "style",
        "likeness": uploads / "likeness",
        "background": uploads / "background",
        "fonts": uploads / "fonts",
    }
    for d in role_dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    (cdir / "intake").mkdir(parents=True, exist_ok=True)
    shutil.copy2(brief_path, cdir / "intake" / "brief.json")

    # Stage product heroes/extras into uploads/product/
    for product in brief.products:
        if product.input_asset_path:
            dest = _stage(product.input_asset_path, role_dirs["product"], required=True)
            product.input_asset_path = dest
        extras: list[str] = []
        for extra in product.input_asset_paths or []:
            dest = _stage(extra, role_dirs["product"], required=True)
            if dest:
                extras.append(dest)
        product.input_asset_paths = extras

    logo_sources: list[str] = []
    for raw in brief.brand_notes.logo_paths or []:
        if raw and raw not in logo_sources:
            logo_sources.append(raw)
    if brief.brand_notes.logo_path and brief.brand_notes.logo_path not in logo_sources:
        logo_sources.insert(0, brief.brand_notes.logo_path)
    staged_logos: list[str] = []
    for raw in logo_sources:
        dest = _stage(raw, role_dirs["logo"], required=bool(brief.brand_notes.logo_path == raw))
        if dest and dest not in staged_logos:
            staged_logos.append(dest)
    if staged_logos:
        brief.brand_notes.logo_paths = staged_logos
        if (
            not brief.brand_notes.logo_path
            or brief.brand_notes.logo_path not in staged_logos
        ):
            brief.brand_notes.logo_path = staged_logos[0]
        else:
            # Keep selection; remap to staged path by filename if needed
            want = Path(brief.brand_notes.logo_path).name
            match = next((p for p in staged_logos if Path(p).name == want), staged_logos[0])
            brief.brand_notes.logo_path = match

    if brief.brand_notes.font_file_path:
        dest = _stage(brief.brand_notes.font_file_path, role_dirs["fonts"], required=True)
        if dest:
            brief.brand_notes.font_file_path = dest

    for attr, role in (
        ("style_reference_paths", "style"),
        ("likeness_reference_paths", "likeness"),
        ("background_reference_paths", "background"),
    ):
        staged: list[str] = []
        for raw in getattr(brief, attr) or []:
            dest = _stage(raw, role_dirs[role], required=True)
            if dest:
                staged.append(dest)
        setattr(brief, attr, staged)

    # Per-product style / background refs (e.g. Frozen Moments mood on product 1 only).
    for product in brief.products:
        for attr, role in (
            ("style_reference_paths", "style"),
            ("background_reference_paths", "background"),
        ):
            staged: list[str] = []
            for raw in getattr(product, attr) or []:
                dest = _stage(raw, role_dirs[role], required=True)
                if dest:
                    staged.append(dest)
            setattr(product, attr, staged)

    (cdir / "campaign.json").write_text(
        brief.model_dump_json(indent=2), encoding="utf-8"
    )
    manifest = build_asset_manifest(brief, base_dir=PROJECT_ROOT)
    (cdir / "asset_manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    return {
        "campaign_id": campaign_id,
        "brief": brief.model_dump(),
        "asset_manifest": manifest.model_dump(),
        "missing_fields": missing_required_fields(brief),
        "sample_id": sample_id,
    }
