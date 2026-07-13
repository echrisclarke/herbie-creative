from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.asset_manifest import build_asset_manifest
from app.brief_loader import missing_required_fields, try_parse_structured
from app.config import PROJECT_ROOT
from app.providers.openai_writer import OpenAIWriter
from app.schemas import Brief, ProductMode
from app.storage.paths import campaign_dir, slugify_name

TEXT_SUFFIXES = {".txt", ".md", ".json", ".yaml", ".yml"}
PDF_SUFFIXES = {".pdf"}
BRIEF_SUFFIXES = TEXT_SUFFIXES | PDF_SUFFIXES
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
FONT_SUFFIXES = {".ttf", ".otf"}

UPLOAD_ROLES = ("logo", "product", "style", "likeness", "background", "font", "brief")


def _ensure_upload_dirs(cdir: Path) -> dict[str, Path]:
    intake = cdir / "intake"
    uploads = cdir / "uploads"
    dirs = {
        "intake": intake,
        "uploads": uploads,
        "logo": uploads / "logo",
        "product": uploads / "product",
        "style": uploads / "style",
        "likeness": uploads / "likeness",
        "background": uploads / "background",
        "font": uploads / "fonts",
        "brief": intake,
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def _list_images(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


def _unique_dest(folder: Path, name: str) -> Path:
    dest = folder / name
    if not dest.exists():
        return dest
    stem = Path(name).stem
    suffix = Path(name).suffix
    i = 2
    while True:
        candidate = folder / f"{stem}-{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


async def stage_upload(
    data: bytes,
    filename: str,
    role: str,
    dirs: dict[str, Path],
) -> Path:
    role = (role or "product").strip().lower()
    if role not in dirs and role != "brief":
        role = "product"
    name = filename or "upload.bin"
    suffix = Path(name).suffix.lower()

    if role == "brief" or suffix in BRIEF_SUFFIXES:
        dest = _unique_dest(dirs["brief"], name)
    elif role == "font" or suffix in FONT_SUFFIXES:
        dest = _unique_dest(dirs["font"], name)
    elif role in {"logo", "product", "style", "likeness", "background"}:
        dest = _unique_dest(dirs[role], name)
    else:
        dest = _unique_dest(dirs["product"], name)
    dest.write_bytes(data)
    return dest


async def create_campaign(
    brief_text: str | None,
    files: list[UploadFile],
    *,
    roles: list[str] | None = None,
    campaign_id: str | None = None,
) -> str:
    cid = campaign_id or slugify_name(f"campaign-{uuid.uuid4().hex[:8]}")
    cdir = campaign_dir(cid)
    dirs = _ensure_upload_dirs(cdir)

    role_list = list(roles or [])
    staged: list[Path] = []
    for i, f in enumerate(files):
        name = f.filename or "upload.bin"
        data = await f.read()
        role = role_list[i] if i < len(role_list) else _guess_role(name)
        staged.append(await stage_upload(data, name, role, dirs))

    notes = (brief_text or "").strip()
    has_brief_file = any(
        p.suffix.lower() in BRIEF_SUFFIXES and p.parent == dirs["brief"] for p in staged
    ) or any(
        (role_list[i] if i < len(role_list) else "").lower() == "brief"
        for i in range(len(files))
    )
    if notes:
        if has_brief_file:
            (dirs["brief"] / "additional_instructions.txt").write_text(
                notes, encoding="utf-8"
            )
        else:
            (dirs["brief"] / "raw_brief.txt").write_text(notes, encoding="utf-8")

    return cid


def _guess_role(filename: str) -> str:
    """Fallback when role tags are missing (legacy single dump)."""
    lower = filename.lower()
    suffix = Path(filename).suffix.lower()
    if suffix in BRIEF_SUFFIXES:
        return "brief"
    if suffix in FONT_SUFFIXES:
        return "font"
    if "logo" in lower:
        return "logo"
    if any(k in lower for k in ("likeness", "actor", "character", "face", "person")):
        return "likeness"
    if any(k in lower for k in ("style", "mood", "look", "ref")):
        return "style"
    if any(k in lower for k in ("background", "bg", "env", "scene")):
        return "background"
    return "product"


def parse_campaign(campaign_id: str) -> dict:
    from app.document_text import BRIEF_SUFFIXES as DOC_BRIEF_SUFFIXES
    from app.document_text import PDF_SUFFIX, read_document_text

    cdir = campaign_dir(campaign_id)
    intake = cdir / "intake"
    uploads = cdir / "uploads"
    _ensure_upload_dirs(cdir)

    extra_path = intake / "additional_instructions.txt"
    extra = (
        extra_path.read_text(encoding="utf-8", errors="replace").strip()
        if extra_path.exists()
        else ""
    )

    text = ""
    raw = intake / "raw_brief.txt"
    if raw.exists():
        text = raw.read_text(encoding="utf-8")
    else:
        brief_files = [
            p
            for p in intake.iterdir()
            if p.is_file()
            and p.suffix.lower() in DOC_BRIEF_SUFFIXES
            and p.name.lower()
            not in {"raw_brief.txt", "additional_instructions.txt"}
        ]
        # Prefer non-PDF structured/text files first, then PDF.
        brief_files.sort(key=lambda p: (p.suffix.lower() == PDF_SUFFIX, p.name.lower()))
        for path in brief_files:
            text = read_document_text(path)
            if text.strip():
                break

        if extra:
            text = (
                f"{text.rstrip()}\n\n--- Additional instructions ---\n{extra}"
                if text.strip()
                else extra
            )
        if text.strip():
            raw.write_text(text, encoding="utf-8")

    brief = try_parse_structured(text) if text else None
    if brief is None:
        if not text.strip():
            raise ValueError(
                "No brief found. Paste a brief or upload a text/JSON/YAML/PDF file."
            )
        writer = OpenAIWriter()
        brief = writer.parse_brief(text)

    _map_uploads_to_brief(brief, uploads)

    font_dir = uploads / "fonts"
    if font_dir.exists():
        fonts = [p for p in font_dir.iterdir() if p.is_file()]
        if fonts:
            brief.brand_notes.font_file_path = str(fonts[0])

    manifest = build_asset_manifest(brief, base_dir=PROJECT_ROOT)
    (cdir / "campaign.json").write_text(brief.model_dump_json(indent=2), encoding="utf-8")
    (cdir / "asset_manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    from app.product_seeds import init_product_seeds_status

    seeds = init_product_seeds_status(campaign_id, brief)

    return {
        "brief": brief.model_dump(),
        "asset_manifest": manifest.model_dump(),
        "missing_fields": missing_required_fields(brief),
        "product_seeds": seeds,
        "product_seeds_pending": seeds.get("status") == "pending",
    }


def save_campaign_brief(campaign_id: str, brief: Brief) -> None:
    cdir = campaign_dir(campaign_id)
    (cdir / "campaign.json").write_text(brief.model_dump_json(indent=2), encoding="utf-8")
    manifest = build_asset_manifest(brief, base_dir=PROJECT_ROOT)
    (cdir / "asset_manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )


def approve_campaign(campaign_id: str, brief: Brief) -> None:
    from app.product_seeds import product_seeds_block_approve

    seed_block = product_seeds_block_approve(campaign_id)
    if seed_block:
        raise ValueError(seed_block)
    save_campaign_brief(campaign_id, brief)
    manifest = build_asset_manifest(brief, base_dir=PROJECT_ROOT)
    if not manifest.ready:
        raise ValueError("; ".join(manifest.blockers))


async def save_role_uploads(
    campaign_id: str,
    files: list[UploadFile],
    roles: list[str],
) -> list[str]:
    cdir = campaign_dir(campaign_id)
    dirs = _ensure_upload_dirs(cdir)
    saved: list[str] = []
    for i, f in enumerate(files):
        name = f.filename or "upload.bin"
        data = await f.read()
        role = roles[i] if i < len(roles) else _guess_role(name)
        dest = await stage_upload(data, name, role, dirs)
        saved.append(str(dest))
    return saved


def remap_uploaded_assets(campaign_id: str) -> dict:
    """Map role folders onto the saved campaign without re-parsing the brief."""
    cdir = campaign_dir(campaign_id)
    path = cdir / "campaign.json"
    if not path.exists():
        return {"brief": None, "asset_manifest": None, "missing_fields": []}
    brief = Brief.model_validate_json(path.read_text(encoding="utf-8"))
    uploads = cdir / "uploads"
    _ensure_upload_dirs(cdir)
    _map_uploads_to_brief(brief, uploads)
    font_dir = uploads / "fonts"
    if font_dir.exists():
        fonts = [p for p in font_dir.iterdir() if p.is_file()]
        if fonts and not brief.brand_notes.font_file_path:
            brief.brand_notes.font_file_path = str(fonts[0])
    manifest = build_asset_manifest(brief, base_dir=PROJECT_ROOT)
    path.write_text(brief.model_dump_json(indent=2), encoding="utf-8")
    (cdir / "asset_manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    from app.product_seeds import init_product_seeds_status, products_needing_seeds

    # Uploads may satisfy products that were waiting on background seeds.
    if not products_needing_seeds(brief):
        init_product_seeds_status(campaign_id, brief)
    return {
        "brief": brief.model_dump(),
        "asset_manifest": manifest.model_dump(),
        "missing_fields": missing_required_fields(brief),
    }


def load_campaign_brief(campaign_id: str) -> Brief:
    path = campaign_dir(campaign_id) / "campaign.json"
    if not path.exists():
        raise FileNotFoundError(f"No campaign.json for {campaign_id}")
    return Brief.model_validate_json(path.read_text(encoding="utf-8"))


def _map_uploads_to_brief(brief: Brief, uploads: Path) -> None:
    """Map role folders into brief fields. Prefer role dirs over flat dumps."""
    if not uploads.exists():
        return

    logo_dir = uploads / "logo"
    product_dir = uploads / "product"
    style_dir = uploads / "style"
    likeness_dir = uploads / "likeness"
    background_dir = uploads / "background"

    logos = _list_images(logo_dir)
    products = _list_images(product_dir)
    styles = _list_images(style_dir)
    likenesses = _list_images(likeness_dir)
    backgrounds = _list_images(background_dir)

    # Legacy flat uploads/ (pre-role) still supported
    flat = [
        p
        for p in uploads.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    ]
    if not logos and not products and flat:
        for p in flat:
            role = _guess_role(p.name)
            if role == "logo":
                logos.append(p)
            elif role == "style":
                styles.append(p)
            elif role == "likeness":
                likenesses.append(p)
            elif role == "background":
                backgrounds.append(p)
            else:
                products.append(p)

    if logos:
        paths = [str(p) for p in logos]
        brief.brand_notes.logo_paths = paths
        current = brief.brand_notes.logo_path
        current_name = Path(current).name if current else None
        still_valid = bool(
            current
            and any(
                str(p) == current or p.name == current_name for p in logos
            )
        )
        if not still_valid:
            brief.brand_notes.logo_path = paths[0]

    if styles:
        brief.style_reference_paths = [str(p) for p in styles]
    if likenesses:
        brief.likeness_reference_paths = [str(p) for p in likenesses]
    if backgrounds:
        brief.background_reference_paths = [str(p) for p in backgrounds]

    if not products:
        return

    idx = 0
    for product in brief.products:
        if product.product_mode != ProductMode.USE_PROVIDED:
            # Concept products can still take product refs as extras
            if not product.input_asset_paths and idx < len(products):
                # leave hero unset; stash remaining as refs later
                pass
            continue
        needs_hero = not product.input_asset_path or not Path(
            product.input_asset_path
        ).exists()
        if needs_hero and idx < len(products):
            product.input_asset_path = str(products[idx])
            idx += 1

    # Leftover product images → extras on first product that can use them
    if idx < len(products):
        extras = [str(p) for p in products[idx:]]
        target = next(
            (
                p
                for p in brief.products
                if p.product_mode == ProductMode.USE_PROVIDED
            ),
            brief.products[0] if brief.products else None,
        )
        if target is not None:
            existing = list(target.input_asset_paths or [])
            for path in extras:
                if path not in existing and path != target.input_asset_path:
                    existing.append(path)
            target.input_asset_paths = existing
