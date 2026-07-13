"""App-wide Finalize: vision suggest → user choices → Pillow finals.

Brand-agnostic. Same path for every campaign.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.asset_manifest import product_slug
from app.composer import compose_message
from app.config import PROJECT_ROOT
from app.providers.finalize_suggest import suggest_finalize
from app.schemas import (
    RATIO_FOLDER,
    BrandNotes,
    Brief,
    CreativeResult,
    FinalizeChoices,
    Product,
    Report,
)
from app.storage.paths import campaign_dir, locale_slug, slugify_name

logger = logging.getLogger(__name__)

ALLOWED_LOGO = {"top-left", "top-right", "bottom-left", "bottom-right"}
ALLOWED_TEXT = {
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


def resolve_logo_path(brief: Brief, cdir: Path) -> Path | None:
    raw = brief.brand_notes.logo_path
    if not raw:
        return None
    lp = Path(raw)
    if not lp.is_absolute():
        for candidate in (PROJECT_ROOT / lp, cdir / lp, lp):
            if candidate.exists():
                return candidate
        return None
    return lp if lp.exists() else None


def ensure_logo(
    brief: Brief,
    cdir: Path,
    choices: FinalizeChoices,
) -> Path | None:
    """Resolve uploaded logo, or generate one from a description when requested."""
    if not choices.use_logo:
        return None
    existing = resolve_logo_path(brief, cdir)
    if existing:
        return existing
    desc = (
        (choices.logo_description or brief.brand_notes.logo_description or "")
        .strip()
    )
    if not desc:
        return None
    try:
        from app.providers.openai_image import OpenAIImageGenerator
        from PIL import Image
        from io import BytesIO

        gen = OpenAIImageGenerator()
        prompt = (
            "Create a single flat brand logo mark only. Transparent or pure white "
            "background. Vector-clean, high contrast, centered. No mockups, no "
            "scene, no people, no product photos. Logo description: "
            f"{desc}"
        )
        raw = gen.generate(prompt, size="1024x1024")
        img = Image.open(BytesIO(raw)).convert("RGBA")
        # Knock out near-white background so Pillow can composite cleanly.
        pixels = img.load()
        w, h = img.size
        for y in range(h):
            for x in range(w):
                r, g, b, a = pixels[x, y]
                if r > 245 and g > 245 and b > 245:
                    pixels[x, y] = (r, g, b, 0)
        dest_dir = cdir / "uploads" / "logo"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "generated-logo.png"
        img.save(dest, format="PNG")
        brief.brand_notes.logo_path = str(dest)
        paths = list(brief.brand_notes.logo_paths or [])
        if str(dest) not in paths:
            paths.append(str(dest))
        brief.brand_notes.logo_paths = paths
        brief.brand_notes.logo_description = desc
        (cdir / "campaign.json").write_text(
            brief.model_dump_json(indent=2), encoding="utf-8"
        )
        logger.info("Generated logo from description → %s", dest)
        return dest
    except Exception:
        logger.exception("Logo generation from description failed")
        return None


def collect_creative_paths(
    brief: Brief, cdir: Path, *, prefer_ratios: tuple[str, ...] = ("1x1", "9x16", "16x9")
) -> list[Path]:
    """Pick up to 2 creatives (prefer different ratios) for vision suggest."""
    market = slugify_name(brief.market or "us")
    found: list[Path] = []
    names = ("creative.png", "creative.tight.png")

    def pick_in(folder: Path) -> Path | None:
        for name in names:
            p = folder / name
            if p.exists():
                return p
        return None

    for product in brief.products:
        pslug = product_slug(product.name)
        for folder_name in prefer_ratios:
            hit = pick_in(cdir / "outputs" / market / pslug / folder_name)
            if hit is not None:
                found.append(hit)
                break
        if len(found) >= 2:
            break
    if not found:
        outputs = cdir / "outputs"
        if outputs.exists():
            for name in names:
                for p in sorted(outputs.rglob(name)):
                    found.append(p)
                    if len(found) >= 2:
                        return found
    return found


def run_suggest_finalize(campaign_id: str, brief: Brief | None = None) -> dict[str, Any]:
    cdir = campaign_dir(campaign_id)
    if not cdir.exists():
        raise FileNotFoundError(f"campaign not found: {campaign_id}")
    if brief is None:
        brief = Brief.model_validate_json(
            (cdir / "campaign.json").read_text(encoding="utf-8")
        )
    creatives = collect_creative_paths(brief, cdir)
    if not creatives:
        raise FileNotFoundError("No creative.png found. Generate creatives first.")
    logo = resolve_logo_path(brief, cdir)
    style = suggest_finalize(brief, creatives, logo_path=logo)
    out = cdir / "finalize_style_suggest.json"
    out.write_text(json.dumps(style, indent=2, ensure_ascii=False), encoding="utf-8")
    return style


def load_suggest(campaign_id: str) -> dict[str, Any] | None:
    path = campaign_dir(campaign_id) / "finalize_style_suggest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_brand(
    brief: Brief,
    style: dict[str, Any],
    choices: FinalizeChoices,
    logo: Path | None,
) -> BrandNotes:
    bn = brief.brand_notes
    logo_color = choices.logo_color or style.get("logo_color") or bn.logo_color
    text_color = choices.text_color or style.get("text_color") or bn.text_color
    cta_accent = choices.cta_accent or style.get("cta_accent")
    colors = list(bn.colors or [])
    if cta_accent:
        colors = [cta_accent, *[c for c in colors if c != cta_accent]]
    placement = (
        choices.logo_placement
        or style.get("logo_placement")
        or bn.logo_placement
        or "top-left"
    )
    if placement not in ALLOWED_LOGO:
        placement = "top-left"
    text_placement = (
        choices.text_placement
        or style.get("text_placement")
        or bn.text_placement
        or "bottom-center"
    )
    if text_placement == "auto" or choices.ai_decide_placement:
        suggested = style.get("text_placement")
        text_placement = suggested if suggested in ALLOWED_TEXT else "bottom-center"
    if text_placement not in ALLOWED_TEXT:
        text_placement = "bottom-center"
    fonts = choices.font_names or style.get("font_names") or bn.font_names or []
    use_logo = choices.use_logo and logo is not None
    scrim = choices.text_scrim if choices.text_scrim is not None else style.get("text_scrim")
    if scrim is None:
        scrim = bn.text_scrim
    scrim_op = (
        choices.text_scrim_opacity
        if choices.text_scrim_opacity is not None
        else style.get("text_scrim_opacity", bn.text_scrim_opacity)
    )
    shadow_op = (
        choices.text_shadow_opacity
        if choices.text_shadow_opacity is not None
        else style.get("text_shadow_opacity", bn.text_shadow_opacity)
    )
    logo_shadow = (
        choices.logo_shadow_opacity
        if choices.logo_shadow_opacity is not None
        else getattr(bn, "logo_shadow_opacity", None)
    )
    logo_opacity = (
        choices.logo_opacity
        if choices.logo_opacity is not None
        else getattr(bn, "logo_opacity", None)
    )
    logo_scale = (
        choices.logo_scale
        if choices.logo_scale is not None
        else getattr(bn, "logo_scale", None)
    )
    legal_placement = (
        choices.legal_placement
        or getattr(bn, "legal_placement", None)
        or "left"
    )
    if legal_placement not in {"left", "center", "right"}:
        legal_placement = "left"
    return BrandNotes(
        tone=bn.tone,
        colors=colors,
        font_names=list(fonts),
        font_alternates=list(bn.font_alternates or []),
        logo_required=use_logo,
        logo_path=str(logo) if use_logo else None,
        logo_placement=placement,  # type: ignore[arg-type]
        text_placement=text_placement,  # type: ignore[arg-type]
        legal_placement=legal_placement,  # type: ignore[arg-type]
        logo_color=logo_color,
        logo_shadow_opacity=logo_shadow,
        logo_opacity=logo_opacity,
        logo_scale=logo_scale,
        text_color=text_color,
        text_scrim=scrim,
        text_scrim_opacity=scrim_op,
        text_shadow_opacity=shadow_op,
        forbidden_words=list(bn.forbidden_words or []),
        font_file_path=bn.font_file_path,
    )


def _locale_pairs(
    brief: Brief,
    style: dict[str, Any],
    choices: FinalizeChoices,
    *,
    product: Product | None = None,
) -> dict[str, dict[str, str]]:
    from app.product_fields import product_cta, product_message, product_supporting

    if choices.locales is not None:
        locales = list(choices.locales)
    else:
        locales = list(brief.localize_to or [])
    if not locales:
        locales = ["English"]
    style_locales = style.get("locales") or {}
    override = choices.locales_copy or {}
    caption_seed = (choices.caption_text or "").strip()
    sub_seed = (choices.subcaption_text or "").strip()
    source = locales[0]
    source_override = override.get(source)
    if source_override is not None and hasattr(source_override, "model_dump"):
        source_override = source_override.model_dump()

    product_override = None
    if product is not None and choices.product_copy:
        raw_pc = choices.product_copy.get(product.name)
        if raw_pc is None:
            # UI / report keys may be slugified product names.
            from app.asset_manifest import product_slug

            want = product_slug(product.name)
            for key, val in choices.product_copy.items():
                if product_slug(str(key)) == want:
                    raw_pc = val
                    break
        if raw_pc is not None:
            product_override = (
                raw_pc.model_dump() if hasattr(raw_pc, "model_dump") else dict(raw_pc)
            )

    has_product_copy = bool(
        (product_override and (product_override.get("message") or "").strip())
        or (product is not None and (product.message or "").strip())
    )

    # Priority for multi-SKU campaigns: Finalize per-product edit → product brief
    # fields → campaign-level Finalize / brief. Without this, sibling products share copy.
    if product_override and (product_override.get("message") or "").strip():
        source_msg = (product_override.get("message") or "").strip()
        source_cta = (product_override.get("cta") or "").strip()
        source_sup = (product_override.get("supporting") or "").strip()
    elif product is not None and (product.message or "").strip():
        source_msg = product_message(brief, product)
        source_cta = product_cta(brief, product)
        source_sup = product_supporting(brief, product)
    else:
        source_msg = (
            (source_override or {}).get("message")
            or caption_seed
            or (product_message(brief, product) if product else brief.message)
            or ""
        ).strip()
        source_cta = (
            (source_override or {}).get("cta")
            or (product_cta(brief, product) if product else brief.cta)
            or ""
        ).strip()
        source_sup = (
            (source_override or {}).get("supporting")
            or sub_seed
            or (product_supporting(brief, product) if product else brief.supporting_copy)
            or ""
        ).strip()

    seed_brief = brief.model_copy(
        update={
            "message": source_msg,
            "cta": source_cta,
            "supporting_copy": source_sup,
            # Keep localization focused on THIS product's scene, not sibling SKUs.
            "creative_direction": (
                (product.creative_direction or brief.creative_direction or "").strip()
                if product is not None
                else (brief.creative_direction or "")
            ),
        }
    )
    seed: dict[str, dict[str, str]] = {
        source: {
            "message": source_msg,
            "cta": source_cta,
            "supporting": source_sup,
        }
    }
    for loc in locales:
        if loc == source:
            continue
        # Sibling SKUs: if this product already has its own copy, skip vision
        # seeds that may have been written for another shoe in the same suggest.
        pair: dict[str, str] = {}
        if not has_product_copy:
            pair = dict(style_locales.get(loc) or {})
        if loc in override and not has_product_copy:
            raw = override[loc]
            if hasattr(raw, "model_dump"):
                raw = raw.model_dump()
            pair.update({k: v for k, v in dict(raw).items() if v})
        seed[loc] = {
            "message": (pair.get("message") or "").strip(),
            "cta": (pair.get("cta") or "").strip(),
            "supporting": (pair.get("supporting") or "").strip(),
        }

    try:
        from app.providers.openai_writer import fill_localized_copy

        filled = fill_localized_copy(
            seed_brief,
            seed,
            language_list=locales,
            force=True,
            product=product,
        )
        if not has_product_copy:
            for loc, raw in override.items():
                if loc == source:
                    continue
                if hasattr(raw, "model_dump"):
                    raw = raw.model_dump()
                filled[loc] = {
                    "message": str(raw.get("message") or filled.get(loc, {}).get("message") or ""),
                    "cta": str(raw.get("cta") or filled.get(loc, {}).get("cta") or ""),
                    "supporting": str(
                        raw.get("supporting") or filled.get(loc, {}).get("supporting") or ""
                    ),
                }
        filled[source] = {
            "message": source_msg,
            "cta": source_cta,
            "supporting": source_sup,
        }
        return filled
    except Exception:
        logger.exception("locale fill failed; using merged copy as-is")
        return seed


def _slot_modes(choices: FinalizeChoices, brief: Brief):
    """Map caption/subcaption choices → text mode + SlotRenderChoices."""
    from app.schemas import SlotRenderChoices

    base = brief.slot_render or SlotRenderChoices()
    mode_in = (choices.text_render_mode or brief.text_render_mode or "composer").lower()
    if mode_in == "pillow":
        mode_in = "composer"
    if mode_in == "later":
        mode_in = "composer"
    if mode_in == "none" or choices.text_placement == "none":
        return "none", SlotRenderChoices(
            logo=base.logo if choices.use_logo else "skip",
            headline="skip",
            supporting="skip",
            cta="skip",
            legal="skip",
        )

    cap = choices.caption_mode or "composer"
    sub = choices.subcaption_mode or "skip"
    slots = SlotRenderChoices(
        logo=base.logo if choices.use_logo else "skip",
        headline="ai" if cap == "ai" else ("skip" if cap == "skip" else "pillow"),
        supporting="ai" if sub == "ai" else ("skip" if sub == "skip" else "pillow"),
        cta=base.cta if cap != "skip" else "skip",
        legal=(
            "pillow"
            if (brief.legal_disclaimer or "").strip()
            else base.legal
        ),
    )
    if cap == "ai" or sub == "ai":
        mode = "hybrid"
    elif choices.text_render_mode:
        mode = choices.text_render_mode
    else:
        mode = brief.text_render_mode or "composer"
    if mode in {"pillow", "later"}:
        mode = "composer"
    if mode == "none":
        mode = "composer"
    return mode, slots


def _try_ai_text(
    image_bytes: bytes,
    ratio: str,
    message: str,
    cta: str,
    brief: Brief,
    *,
    supporting: str = "",
    style_notes: str = "",
    fit_notes: str = "",
    placement: str = "",
) -> tuple[bytes, bool]:
    from app.providers.openai_editor import OpenAIImageEditor
    from app.pipeline import _ai_text_overlay

    editor = OpenAIImageEditor()
    return _ai_text_overlay(
        editor,
        image_bytes,
        ratio,
        message,
        cta,
        brief,
        supporting=supporting,
        style_notes=style_notes,
        fit_notes=fit_notes,
        placement=placement,
    )


def finalize_campaign(
    campaign_id: str,
    choices: FinalizeChoices | None = None,
    *,
    brief: Brief | None = None,
    style: dict[str, Any] | None = None,
    run_suggest: bool = False,
) -> Report:
    """Apply Pillow finals from locked creatives. Optionally run vision suggest first."""
    choices = choices or FinalizeChoices()
    cdir = campaign_dir(campaign_id)
    if not cdir.exists():
        raise FileNotFoundError(f"campaign not found: {campaign_id}")
    if brief is None:
        brief = Brief.model_validate_json(
            (cdir / "campaign.json").read_text(encoding="utf-8")
        )

    if run_suggest or (
        style is None
        and not choices.skip_suggest
        and not load_suggest(campaign_id)
    ):
        style = run_suggest_finalize(campaign_id, brief)
    if style is None:
        style = load_suggest(campaign_id) or {}

    # If placement is auto, ensure we have a vision suggest to pick from.
    if (
        choices.ai_decide_placement or choices.text_placement == "auto"
    ) and not style.get("text_placement"):
        try:
            style = {**(style or {}), **run_suggest_finalize(campaign_id, brief)}
        except Exception:
            logger.exception("auto placement suggest failed")

    logo = ensure_logo(brief, cdir, choices) if choices.use_logo else None
    brand = _merge_brand(brief, style, choices, logo)
    market = slugify_name(brief.market or "us")
    ratios = [r for r in (brief.outputs or list(RATIO_FOLDER)) if r in RATIO_FOLDER]

    mode, slots = _slot_modes(choices, brief)
    cap_style = (choices.caption_style or "").strip()
    cap_fit = (choices.caption_fit or "").strip()
    sub_style = (choices.subcaption_style or "").strip()
    sub_fit = (choices.subcaption_fit or "").strip()
    style_notes = "; ".join(x for x in (cap_style, sub_style) if x)
    fit_notes = "; ".join(x for x in (cap_fit, sub_fit) if x)
    by_ratio = {
        str(k): str(v)
        for k, v in (choices.text_placement_by_ratio or {}).items()
        if v
    }
    default_placement = brand.text_placement or "bottom-center"

    creatives: list[CreativeResult] = []
    for product in brief.products:
        pairs = _locale_pairs(brief, style, choices, product=product)
        primary = next(iter(pairs.keys()), "English")
        pslug = product_slug(product.name)
        source = (
            "provided_image"
            if product.product_mode.value == "use-provided"
            else "concept_generated"
        )
        for ratio in ratios:
            folder = RATIO_FOLDER[ratio]
            out_dir = cdir / "outputs" / market / pslug / folder
            main = out_dir / "creative.png"
            tight = out_dir / "creative.tight.png"
            # Finalize both the main ratio still and the close-up hero when present.
            targets: list[tuple[str, Path, str]] = []
            if main.exists():
                targets.append((ratio, main, ""))
            if tight.exists():
                if main.exists():
                    targets.append((f"{ratio}-tight", tight, "tight."))
                else:
                    targets.append((ratio, tight, ""))
            if not targets:
                logger.warning("Missing creative: %s", main)
                continue

            for placement_key, creative, name_prefix in targets:
                from app.text_placement import resolve_text_placement

                creative_bytes = creative.read_bytes()
                rel_creative = str(creative.relative_to(PROJECT_ROOT)).replace("\\", "/")
                placement_hint = resolve_text_placement(
                    ratio,
                    by_ratio=by_ratio,
                    placement_key=placement_key,
                    fallback=default_placement,
                )
                if placement_hint == "auto":
                    suggested = style.get("text_placement")
                    placement_hint = (
                        suggested if suggested in ALLOWED_TEXT else "bottom-center"
                    )
                if placement_hint not in ALLOWED_TEXT:
                    placement_hint = "bottom-center"
                brand_ratio = brand.model_copy(update={"text_placement": placement_hint})

                for loc, pair in pairs.items():
                    msg = pair["message"]
                    cta = pair["cta"]
                    supporting = (pair.get("supporting") or "").strip()
                    base_bytes = creative_bytes
                    headline = msg
                    pillow_cta = cta
                    pillow_supporting = supporting

                    need_ai = slots.headline == "ai" or slots.supporting == "ai"
                    if need_ai or mode == "ai":
                        ai_msg = msg if slots.headline == "ai" or mode == "ai" else ""
                        ai_cta = cta if mode == "ai" else ""
                        ai_sup = supporting if slots.supporting == "ai" else ""
                        stamped, failed = _try_ai_text(
                            base_bytes,
                            ratio,
                            ai_msg,
                            ai_cta,
                            brief,
                            supporting=ai_sup,
                            style_notes=style_notes,
                            fit_notes=fit_notes,
                            placement=placement_hint,
                        )
                        if not failed:
                            suffix = (
                                "creative.tight.ai_text.png"
                                if name_prefix
                                else "creative.ai_text.png"
                            )
                            creative.with_name(suffix).write_bytes(stamped)
                            base_bytes = stamped
                            if slots.headline == "ai" or mode == "ai":
                                headline = ""
                            if mode == "ai":
                                pillow_cta = ""
                            if slots.supporting == "ai":
                                pillow_supporting = ""

                    if slots.headline == "skip":
                        headline = ""
                    if slots.cta == "skip":
                        pillow_cta = ""
                    if slots.supporting == "skip":
                        pillow_supporting = ""

                    final_bytes = compose_message(
                        base_bytes,
                        headline,
                        ratio,
                        brand_notes=brand_ratio,
                        cta=pillow_cta,
                        supporting=pillow_supporting,
                        legal=brief.legal_disclaimer or "",
                        slot_render=slots,
                    )

                    out = creative.parent / f"final.{name_prefix}{locale_slug(loc)}.png"
                    out.write_bytes(final_bytes)
                    if loc.lower().startswith("en") or loc == primary:
                        primary_name = (
                            f"final.{name_prefix.rstrip('.')}.png"
                            if name_prefix
                            else "final.png"
                        )
                        (creative.parent / primary_name).write_bytes(final_bytes)
                    rel = str(out.relative_to(PROJECT_ROOT)).replace("\\", "/")
                    creatives.append(
                        CreativeResult(
                            product=product.name,
                            ratio=placement_key,
                            path=rel,
                            locale=loc,
                            creative_path=rel_creative,
                            source=source,  # type: ignore[arg-type]
                            image_provider="openai",
                            text_provider="openai" if need_ai or mode == "ai" else "pillow",
                            message=msg,
                            cta=cta,
                        )
                    )

    from datetime import datetime, timezone

    report_path = cdir / "report.json"
    existing: dict[str, Any] = {}
    if report_path.exists():
        try:
            existing = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    # Keep creative-only rows; replace/append finals
    prior = [
        c
        for c in (existing.get("creatives") or [])
        if isinstance(c, dict) and c.get("locale") == "creative"
    ]
    merged = prior + [c.model_dump() for c in creatives]
    now = datetime.now(timezone.utc).isoformat()
    report = {
        "campaign_id": campaign_id,
        "started_at": existing.get("started_at") or now,
        "finished_at": now,
        "storage_backend": existing.get("storage_backend") or "local",
        "creatives": merged,
        "totals": {
            **(existing.get("totals") or {}),
            "finals": len(creatives),
            "text_render_mode": mode,
            "finalize": True,
        },
        "missing_fields": existing.get("missing_fields") or [],
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = cdir / "report.md"
    md.write_text(
        f"# Finalize report: {campaign_id}\n\nFinals: {len(creatives)}\n",
        encoding="utf-8",
    )
    return Report.model_validate(report)
