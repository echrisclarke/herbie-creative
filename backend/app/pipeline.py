from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.asset_manifest import (
    build_asset_manifest,
    product_slug,
    resolve_path,
    resolve_product_asset_paths,
)
from app.composer import compose_message
from app.compliance import run_compliance
from app.config import PROJECT_ROOT, get_openai_api_key, get_xai_api_key
from app.providers.openai_editor import OpenAIImageEditor
from app.providers.openai_image import OpenAIImageGenerator
from app.providers.openai_writer import OpenAIWriter, build_image_prompt
from app.providers.pillow_editor import crop_pad_to_size
from app.reports import write_live_report, write_report
from app.schemas import (
    MAX_LOCALES,
    RATIO_SIZES,
    Brief,
    CreativeResult,
    Product,
    ProductMode,
    Report,
)
from app.storage.paths import (
    campaign_dir,
    locale_slug,
    output_path,
    slugify_name,
)

logger = logging.getLogger(__name__)

EventCallback = Callable[[str, dict], None]

RATIO_ORDER = ("1:1", "9:16", "16:9")

# Keep these short and concrete. Long brief dumps hurt edit fidelity.
TIGHT_EDIT_PROMPT = (
    "Make a polished close-up product ad still of this product. "
    "Keep the exact product design, materials, and logos from the source image. "
    "Fill most of the frame with the product. Clean environment. "
    "No campaign text in the image."
)

ZOOM_EDIT_PROMPT = (
    "Start from this finished still and pull the camera back for a wider shot of the SAME moment. "
    "Keep the exact same person, pose, body position, clothing, product identity, materials, and logos. "
    "Do not change the pose. Do not stand them up. Do not sit them on a chair, stool, or furniture. "
    "Do not invent new props or a different scene. Only reveal more of the same environment around them. "
    "Keep real-world proportions. Do not warp, stretch, or invent broken geometry. "
    "Place the optical center of the subject near the middle of the frame "
    "(not in the bottom third). Roughly equal empty space above and below. "
    "Subject about 20-40% of the frame. Same environment family. No campaign text."
)

RATIO_CHAIN_PROMPT = (
    "Reframe this exact creative into the new aspect ratio canvas. "
    "Keep the exact same person, pose, product identity, face art, materials, logos, lighting, and environment. "
    "Do not invent a different product, character, pose, chair, or scene. "
    "Compose a fresh full-bleed social ad still for the new frame. "
    "Keep the subject optically centered with natural breathing room. "
    "Do not crop awkwardly or letterbox. No campaign text in the image."
)

FramingMode = str  # "close-up" | "zoomed" | "both"


def run_campaign(
    brief: Brief,
    *,
    campaign_slug: str | None = None,
    project_root: Path | None = None,
    with_motion: bool = False,
    motion_duration: int = 6,
    # Christian: deprecated. No API/CLI caller passes motion_ratios anymore.
    # Harmless leftover from when Generate could animate a ratio subset.
    motion_ratios: list[str] | None = None,
    # Default False for CLI full runs. The UI FastAPI job always sends True.
    creatives_only: bool = False,
    master_only: bool = False,
    zoom_only: bool = False,
    outputs_override: list[str] | None = None,
    framing_override: str | None = None,
    source_image_paths: list[str] | None = None,
    on_event: EventCallback | None = None,
    outputs_by_product: list[list[str]] | None = None,
    finalize_ratios_by_product: list[list[str] | None] | None = None,
    bonus_locale: str | None = None,
) -> Report:
    root = project_root or PROJECT_ROOT
    slug = campaign_slug or slugify_name(brief.campaign_name)
    cdir = campaign_dir(slug)
    log_path = cdir / "run.log"
    _setup_file_logging(log_path)

    started = datetime.now(timezone.utc)
    manifest = build_asset_manifest(brief, base_dir=root)
    if not manifest.ready:
        raise ValueError("; ".join(manifest.blockers) or "Asset manifest not ready")

    (cdir / "campaign.json").write_text(brief.model_dump_json(indent=2), encoding="utf-8")
    (cdir / "asset_manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    if not get_openai_api_key():
        raise RuntimeError("OPENAI_API_KEY is required for the static pipeline")

    writer = OpenAIWriter()
    image_gen = OpenAIImageGenerator()
    image_edit = OpenAIImageEditor()

    market_slug = slugify_name(brief.market or "us")
    creatives: list[CreativeResult] = []
    locale_cache: dict[str, tuple[str, str, str]] = {}
    locales = _normalize_locales(brief.localize_to)
    bonus_locale_norm = (bonus_locale or "").strip() or None
    bonus_locale_applied = False
    # Creatives-first: text mode is applied in Finalize. later/none are deferred.
    text_mode = (brief.text_render_mode or "later").lower()
    if text_mode == "pillow":
        text_mode = "composer"
    if text_mode in {"later", "none"}:
        text_mode = "composer"
    if text_mode not in {"composer", "ai", "hybrid"}:
        text_mode = "composer"
    # Legal disclaimer must render when present (slot default is skip).
    if (brief.legal_disclaimer or "").strip():
        brief.slot_render.legal = "pillow"

    def emit(event: str, data: dict) -> None:
        if on_event:
            on_event(event, data)

    locked_sources = _load_source_still_bytes(source_image_paths or [], root, cdir)
    if locked_sources:
        logger.info(
            "Generate-more locked to %s existing still(s) as source",
            len(locked_sources),
        )

    for product_index, product in enumerate(brief.products, start=1):
        pslug = product_slug(product.name)
        emit(
            "product.started",
            {
                "product": product.name,
                "index": product_index,
                "total": len(brief.products),
            },
        )
        source: str
        seed_bytes: bytes
        reference_bytes: list[bytes] = []
        seed_is_square_master = False

        t0 = time.perf_counter()
        # Per-product copy/locales: do not reuse another shoe's localized lines.
        locale_cache.clear()
        campaign_refs, role_note = _collect_campaign_role_refs(brief, root, product=product)

        if locked_sources:
            # Reframe / extend from chosen existing creatives instead of inventing a new scene.
            seed_bytes = locked_sources[0]
            reference_bytes = list(locked_sources[1:])
            for extra in product.input_asset_paths:
                resolved = resolve_path(extra, root)
                if resolved and resolved.exists():
                    reference_bytes.append(resolved.read_bytes())
            source = "provided_image"
            role_note = (
                f"{role_note} Keep the exact person, pose, wardrobe, product, set, "
                "lighting, and look from the attached source still(s). Only reframe "
                "or zoom for the requested aspect ratio."
            ).strip()
        elif product.product_mode == ProductMode.USE_PROVIDED:
            asset = next(
                (p for p in manifest.products if p.product_name == product.name), None
            )
            asset_paths = list(asset.paths) if asset and asset.paths else []
            if not asset_paths:
                asset_paths = resolve_product_asset_paths(product, root)
            if not asset_paths:
                raise FileNotFoundError(
                    f"This product needs an uploaded image before generation: {product.name}"
                )
            seed_bytes = Path(asset_paths[0]).read_bytes()
            for extra in asset_paths[1:]:
                reference_bytes.append(Path(extra).read_bytes())
            if reference_bytes:
                logger.info(
                    "%s: compositing hero + %s reference image(s)",
                    product.name,
                    len(reference_bytes),
                )
            source = "provided_image"
        else:
            for extra in product.input_asset_paths:
                resolved = resolve_path(extra, root)
                if resolved and resolved.exists():
                    reference_bytes.append(resolved.read_bytes())

            prompt = build_image_prompt(brief, product)
            # Prefer product refs, then campaign role refs, as the seed for concept work
            seed_pool = list(reference_bytes) + list(campaign_refs)
            if seed_pool:
                logger.info(
                    "Generating concept for %s from %s reference image(s)",
                    product.name,
                    len(seed_pool),
                )
                seed_bytes = seed_pool[0]
                reference_bytes = seed_pool[1:]
                campaign_refs = []  # already folded into reference_bytes
            else:
                logger.info("Generating tight square hero for %s", product.name)
                seed_bytes = image_gen.generate(
                    f"{prompt} {TIGHT_EDIT_PROMPT}",
                    ratio="1:1",
                )
                seed_is_square_master = True
            source = "concept_generated"

        if campaign_refs:
            reference_bytes.extend(campaign_refs)
            logger.info(
                "%s: +%s campaign role reference(s)",
                product.name,
                len(campaign_refs),
            )
        reference_bytes = reference_bytes[:5]

        # Placement / framing: product scene first, then campaign (cap length; rules first in asset_hint)
        from app.product_fields import product_cta, product_direction, product_message

        env = product_direction(brief, product)
        hint = (product.asset_hint or "").strip()
        placement = (hint or env)[:320]
        if role_note:
            placement = f"{placement} {role_note}".strip()[:400]
        tight_prompt = TIGHT_EDIT_PROMPT
        zoom_prompt = ZOOM_EDIT_PROMPT
        if placement:
            tight_prompt = f"{TIGHT_EDIT_PROMPT} Placement: {placement}"
            if hint or role_note:
                zoom_prompt = f"{ZOOM_EDIT_PROMPT} Placement: {(hint or role_note)[:280]}"

        work = cdir / "_work" / market_slug / pslug
        work.mkdir(parents=True, exist_ok=True)

        # Legacy flags map onto framing + single 1:1 ratio
        framing = _normalize_framing(
            framing_override
            or ("both" if (zoom_only or master_only) else None)
            or getattr(brief, "framing", None)
            or "both"
        )
        if zoom_only or master_only:
            ordered = ["1:1"]
            framing = "both"
        elif outputs_by_product and (product_index - 1) < len(outputs_by_product):
            ordered = _normalize_outputs(outputs_by_product[product_index - 1])
        else:
            ordered = _normalize_outputs(outputs_override or brief.outputs)

        finalize_for_product: list[str] | None = None
        if finalize_ratios_by_product and (product_index - 1) < len(
            finalize_ratios_by_product
        ):
            finalize_for_product = finalize_ratios_by_product[product_index - 1]
        # None = finalize every generated ratio; [] = creatives only for this product.
        if finalize_for_product is None:
            should_finalize = set(ordered)
        else:
            should_finalize = {r for r in ordered if r in finalize_for_product}

        first_ratio = ordered[0]
        fw, fh = RATIO_SIZES[first_ratio]
        want_close = framing in {"close-up", "both"}
        want_zoom = framing in {"zoomed", "both"}
        # At least one framing step
        if not want_close and not want_zoom:
            want_zoom = True

        ratio_images: dict[str, tuple[bytes, bool, str, int]] = {}
        t_frame = time.perf_counter()
        tight_bytes: bytes | None = None
        provider_tight = "openai"
        fb_tight = False
        hero_bytes: bytes
        provider_hero: str
        fb_hero: bool

        if want_close:
            emit(
                "tile.started",
                {"product": product.name, "ratio": f"{first_ratio}-tight"},
            )
            if seed_is_square_master and first_ratio == "1:1":
                tight_bytes = crop_pad_to_size(seed_bytes, fw, fh)
                fb_tight = False
                provider_tight = "openai"
            else:
                try:
                    tight_bytes, fb_tight = image_edit.adapt(
                        seed_bytes,
                        fw,
                        fh,
                        prompt=tight_prompt,
                        reference_images=(reference_bytes or [])[:5] or None,
                        ratio=first_ratio,
                        preserve_scene=False,
                    )
                    provider_tight = "pillow" if fb_tight else "openai"
                except Exception as exc:
                    logger.warning("Close-up %s failed, Pillow only: %s", first_ratio, exc)
                    tight_bytes = crop_pad_to_size(seed_bytes, fw, fh)
                    fb_tight = True
                    provider_tight = "pillow"
            (work / f"frame-{first_ratio.replace(':', 'x')}-tight.png").write_bytes(
                tight_bytes
            )
            logger.info(
                "%s: close-up %s (%s)", product.name, first_ratio, provider_tight
            )

        if want_zoom:
            emit(
                "tile.started",
                {"product": product.name, "ratio": f"{first_ratio}-zoomed"},
            )
            zoom_src = tight_bytes if tight_bytes is not None else seed_bytes
            try:
                hero_bytes, fb_hero = image_edit.adapt(
                    zoom_src,
                    fw,
                    fh,
                    prompt=zoom_prompt,
                    reference_images=(reference_bytes or [])[:3] or None,
                    ratio=first_ratio,
                    preserve_scene=False,
                )
                provider_hero = "pillow" if fb_hero else "openai"
            except Exception as exc:
                logger.warning("Zoomed %s failed: %s", first_ratio, exc)
                hero_bytes = (
                    tight_bytes
                    if tight_bytes is not None
                    else crop_pad_to_size(seed_bytes, fw, fh)
                )
                fb_hero = True
                provider_hero = "pillow"
            (work / f"frame-{first_ratio.replace(':', 'x')}-zoomed.png").write_bytes(
                hero_bytes
            )
            logger.info("%s: zoomed %s (%s)", product.name, first_ratio, provider_hero)
        else:
            assert tight_bytes is not None
            hero_bytes = tight_bytes
            provider_hero = provider_tight
            fb_hero = fb_tight

        ms_first = int((time.perf_counter() - t0) * 1000) + int(
            (time.perf_counter() - t_frame) * 1000
        )
        ratio_images[first_ratio] = (hero_bytes, fb_hero, provider_hero, ms_first)

        def flush_live_report() -> None:
            write_live_report(
                cdir,
                campaign_id=slug,
                started_at=started.isoformat(),
                creatives=creatives,
                totals={
                    "text_render_mode": "none" if creatives_only else text_mode,
                    "creatives_only": creatives_only,
                },
            )

        def publish_creative(
            ratio: str,
            adapted: bytes,
            fallback: bool,
            image_provider: str,
            image_ms: int,
        ) -> str:
            creative_out = output_path(slug, market_slug, pslug, ratio, "creative.png")
            creative_out.write_bytes(adapted)
            try:
                creative_rel = str(creative_out.relative_to(root)).replace("\\", "/")
            except ValueError:
                creative_rel = str(creative_out)
            if creatives_only:
                creatives.append(
                    CreativeResult(
                        product=pslug,
                        ratio=ratio,
                        path=creative_rel,
                        locale="creative",
                        creative_path=creative_rel,
                        source=source,  # type: ignore[arg-type]
                        image_provider=image_provider,
                        text_provider="none",
                        fallback_triggered=fallback,
                        timings_ms={"image": image_ms, "compose": 0},
                        compliance={},
                    )
                )
            emit(
                "tile.completed",
                {
                    "product": product.name,
                    "ratio": ratio,
                    "locale": "creative",
                    "path": creative_rel,
                    "creative_path": creative_rel,
                    "source": source,
                    "image_provider": image_provider,
                    "text_provider": "none",
                    "fallback_triggered": fallback,
                },
            )
            flush_live_report()
            return creative_rel

        def finalize_ratio(
            ratio: str,
            adapted: bytes,
            fallback: bool,
            image_provider: str,
            image_ms: int,
            overlay_message: str,
            creative_rel: str,
            locales_for_tile: list[str] | None = None,
        ) -> None:
            nonlocal bonus_locale_applied
            locs = list(locales_for_tile or locales)
            for loc in locs:
                if loc not in locale_cache:
                    emit("localize.started", {"product": product.name, "locale": loc})
                    legal_src = brief.legal_disclaimer or ""
                    try:
                        msg_l, cta_l = writer.localize_pair(
                            overlay_message,
                            product_cta(brief, product),
                            loc,
                            brief,
                            product=product,
                        )
                    except Exception as exc:
                        logger.warning("Localize %s failed: %s", loc, exc)
                        msg_l, cta_l = overlay_message, product_cta(brief, product)
                    legal_l = legal_src
                    if legal_src.strip():
                        try:
                            legal_l = writer.localize(
                                legal_src,
                                loc,
                                brief=brief,
                                field="legal_disclaimer",
                            )
                        except Exception as exc:
                            logger.warning("Localize legal %s failed: %s", loc, exc)
                            legal_l = legal_src
                    locale_cache[loc] = (msg_l, cta_l, legal_l)
                msg_l, cta_l, legal_l = locale_cache[loc]

                emit(
                    "tile.started",
                    {
                        "product": product.name,
                        "ratio": ratio,
                        "locale": loc,
                    },
                )
                t_comp = time.perf_counter()
                from app.text_placement import resolve_text_placement

                # Per-ratio defaults (16:9 → top-right) before campaign fallback.
                brand_for_ratio = brief.brand_notes.model_copy(
                    update={
                        "text_placement": resolve_text_placement(
                            ratio,
                            fallback=brief.brand_notes.text_placement,
                        )
                    }
                )
                if text_mode == "ai":
                    final_bytes, ai_fb = _ai_text_overlay(
                        image_edit, adapted, ratio, msg_l, cta_l, brief
                    )
                    if ai_fb:
                        final_bytes = compose_message(
                            adapted,
                            msg_l,
                            ratio,
                            brand_notes=brand_for_ratio,
                            cta=cta_l,
                            supporting=brief.supporting_copy or "",
                            legal=legal_l,
                            slot_render=brief.slot_render,
                        )
                        text_provider = "pillow-fallback"
                    else:
                        # AI typography path: still stamp legal via Pillow when present.
                        if legal_l.strip() and brief.slot_render.legal == "pillow":
                            final_bytes = compose_message(
                                final_bytes,
                                "",
                                ratio,
                                brand_notes=brand_for_ratio,
                                cta="",
                                supporting="",
                                legal=legal_l,
                                slot_render=brief.slot_render,
                            )
                        text_provider = "openai"
                else:
                    final_bytes = compose_message(
                        adapted,
                        msg_l,
                        ratio,
                        brand_notes=brand_for_ratio,
                        cta=cta_l,
                        supporting=brief.supporting_copy or "",
                        legal=legal_l,
                        slot_render=brief.slot_render,
                    )
                    text_provider = "pillow"
                compose_ms = int((time.perf_counter() - t_comp) * 1000)

                loc_file = f"final.{locale_slug(loc)}.png"
                out = output_path(slug, market_slug, pslug, ratio, loc_file)
                out.write_bytes(final_bytes)
                if loc == locs[0]:
                    output_path(slug, market_slug, pslug, ratio, "final.png").write_bytes(
                        final_bytes
                    )

                compliance = run_compliance(
                    final_bytes, brief, product, f"{msg_l} {cta_l} {legal_l}"
                )
                motion_path = None
                # Christian: legacy CLI path (--with-motion on a full run).
                # UI never hits this; it animates from Results via POST /motion.
                if with_motion and loc == locs[0] and ratio == ordered[0]:
                    motion_path = _maybe_motion(
                        out,
                        brief,
                        product.name,
                        duration=motion_duration,
                        root=root,
                        out_name="final.mp4",
                    )

                try:
                    rel = str(out.relative_to(root)).replace("\\", "/")
                except ValueError:
                    rel = str(out)
                result = CreativeResult(
                    product=pslug,
                    ratio=ratio,
                    path=rel,
                    locale=loc,
                    creative_path=creative_rel,
                    source=source,  # type: ignore[arg-type]
                    image_provider=image_provider,
                    text_provider=text_provider,
                    fallback_triggered=fallback,
                    motion_path=motion_path,
                    timings_ms={"image": image_ms, "compose": compose_ms},
                    compliance=compliance,
                    message=msg_l,
                    cta=cta_l,
                )
                creatives.append(result)
                emit(
                    "tile.completed",
                    {
                        "product": product.name,
                        "ratio": ratio,
                        "locale": loc,
                        "path": result.path,
                        "creative_path": creative_rel,
                        "source": source,
                        "image_provider": image_provider,
                        "text_provider": text_provider,
                        "fallback_triggered": fallback,
                        "motion_path": motion_path,
                        "compliance": compliance,
                    },
                )
                flush_live_report()

        def maybe_finalize(
            ratio: str,
            adapted: bytes,
            fallback: bool,
            image_provider: str,
            image_ms: int,
            overlay_message: str,
            creative_rel: str,
        ) -> None:
            nonlocal bonus_locale_applied
            if creatives_only or ratio not in should_finalize:
                if ratio not in should_finalize and not creatives_only:
                    emit(
                        "tile.skipped_text",
                        {
                            "product": product.name,
                            "ratio": ratio,
                            "reason": "creative-only for this smoke/demo tile",
                        },
                    )
                    # Keep creative-only tiles in the live report / Library.
                    creatives.append(
                        CreativeResult(
                            product=pslug,
                            ratio=ratio,
                            path=creative_rel,
                            locale="creative",
                            creative_path=creative_rel,
                            source=source,  # type: ignore[arg-type]
                            image_provider=image_provider,
                            text_provider="none",
                            fallback_triggered=fallback,
                            timings_ms={"image": image_ms, "compose": 0},
                            compliance={},
                        )
                    )
                    flush_live_report()
                return
            locs = list(locales)
            if (
                bonus_locale_norm
                and not bonus_locale_applied
                and product_index == 1
            ):
                if bonus_locale_norm not in locs:
                    locs.append(bonus_locale_norm)
                bonus_locale_applied = True
            finalize_ratio(
                ratio,
                adapted,
                fallback,
                image_provider,
                image_ms,
                overlay_message,
                creative_rel,
                locales_for_tile=locs,
            )

        # Optional close-up artifact on first ratio folder
        if tight_bytes is not None:
            tight_out = output_path(
                slug, market_slug, pslug, first_ratio, "creative.tight.png"
            )
            tight_out.write_bytes(tight_bytes)
            try:
                tight_rel = str(tight_out.relative_to(root)).replace("\\", "/")
            except ValueError:
                tight_rel = str(tight_out)
            creatives.append(
                CreativeResult(
                    product=pslug,
                    ratio=f"{first_ratio}-tight",
                    path=tight_rel,
                    locale="creative",
                    creative_path=tight_rel,
                    source=source,  # type: ignore[arg-type]
                    image_provider=provider_tight,
                    text_provider="none",
                    fallback_triggered=fb_tight,
                    timings_ms={"image": ms_first, "compose": 0},
                    compliance={},
                )
            )
            emit(
                "tile.completed",
                {
                    "product": product.name,
                    "ratio": f"{first_ratio}-tight",
                    "path": tight_rel,
                    "image_provider": provider_tight,
                },
            )
            flush_live_report()

        # Framing-only legacy path: close-up + zoomed on first ratio, stop
        if zoom_only or master_only:
            zoom_out = output_path(
                slug, market_slug, pslug, first_ratio, "creative.png"
            )
            zoom_out.write_bytes(hero_bytes)
            try:
                zoom_rel = str(zoom_out.relative_to(root)).replace("\\", "/")
            except ValueError:
                zoom_rel = str(zoom_out)
            creatives.append(
                CreativeResult(
                    product=pslug,
                    ratio=f"{first_ratio}-zoomed",
                    path=zoom_rel,
                    locale="creative",
                    creative_path=zoom_rel,
                    source=source,  # type: ignore[arg-type]
                    image_provider=provider_hero,
                    text_provider="none",
                    fallback_triggered=fb_hero,
                    timings_ms={"image": ms_first, "compose": 0},
                    compliance={},
                )
            )
            emit(
                "tile.completed",
                {
                    "product": product.name,
                    "ratio": f"{first_ratio}-zoomed",
                    "path": zoom_rel,
                    "image_provider": provider_hero,
                },
            )
            flush_live_report()
            continue

        # Write the first still to disk before other ratios so the UI can show progress.
        first_creative_rel = publish_creative(
            first_ratio, hero_bytes, fb_hero, provider_hero, ms_first
        )
        overlay_message = product_message(brief, product)
        # Christian: legacy CLI path. UI always sends creatives_only=True, then
        # stamps text in the Finalize step. Harmless when False for smoke demos.
        if not creatives_only and should_finalize:
            emit(
                "finalize.started",
                {
                    "product": product.name,
                    "ratios": sorted(should_finalize),
                    "locales": list(locales),
                },
            )
            try:
                polished = writer.generate_copy(brief, product)
                if polished:
                    overlay_message = product_message(brief, product) or polished
            except Exception as exc:
                logger.warning("Copy polish skipped: %s", exc)
        maybe_finalize(
            first_ratio,
            hero_bytes,
            fb_hero,
            provider_hero,
            ms_first,
            overlay_message,
            first_creative_rel,
        )

        # Adapt each extra ratio from the first still so the look stays locked.
        chain_src = hero_bytes
        for ratio in ordered[1:]:
            emit("tile.started", {"product": product.name, "ratio": ratio})
            tw, th = RATIO_SIZES[ratio]
            t_r = time.perf_counter()
            chain_prompt = RATIO_CHAIN_PROMPT
            if placement:
                chain_prompt = f"{RATIO_CHAIN_PROMPT} Placement: {placement[:160]}"
            try:
                adapted, fb = image_edit.adapt(
                    chain_src,
                    tw,
                    th,
                    prompt=chain_prompt,
                    reference_images=(reference_bytes or [])[:2] or None,
                    ratio=ratio,
                    preserve_scene=False,
                )
                prov = "pillow" if fb else "openai"
            except Exception as exc:
                logger.warning(
                    "Chained AI %s -> %s failed, Pillow pad: %s",
                    first_ratio,
                    ratio,
                    exc,
                )
                adapted = crop_pad_to_size(chain_src, tw, th)
                fb = True
                prov = "pillow"
            ms_r = int((time.perf_counter() - t_r) * 1000)
            ratio_images[ratio] = (adapted, fb, prov, ms_r)
            folder = {"1:1": "1x1", "9:16": "9x16", "16:9": "16x9"}.get(
                ratio, ratio.replace(":", "x")
            )
            (work / f"chain-{folder}.png").write_bytes(adapted)
            chain_src = adapted
            logger.info("%s: chained AI %s (%s)", product.name, ratio, prov)
            creative_rel = publish_creative(ratio, adapted, fb, prov, ms_r)
            maybe_finalize(
                ratio,
                adapted,
                fb,
                prov,
                ms_r,
                overlay_message,
                creative_rel,
            )

        if creatives_only:
            # Christian: legacy CLI only (--with-motion --creatives-only).
            # FastAPI Generate always passes with_motion=False, so the UI never enters here.
            if with_motion and ordered:
                want = _normalize_outputs(motion_ratios) if motion_ratios else list(ordered)
                targets = [r for r in ordered if r in want] or list(ordered)
                for ratio in targets:
                    creative_png = output_path(
                        slug, market_slug, pslug, ratio, "creative.png"
                    )
                    if not creative_png.is_file():
                        logger.warning("Skip motion; missing still %s", creative_png)
                        continue
                    emit(
                        "motion.started",
                        {"product": product.name, "ratio": ratio},
                    )
                    motion_rel = _maybe_motion(
                        creative_png,
                        brief,
                        product.name,
                        duration=motion_duration,
                        root=root,
                        out_name="creative.mp4",
                    )
                    emit(
                        "motion.completed" if motion_rel else "motion.skipped",
                        {
                            "product": product.name,
                            "ratio": ratio,
                            "motion_path": motion_rel,
                        },
                    )
                    if motion_rel:
                        for c in reversed(creatives):
                            if (
                                c.product == pslug
                                and c.ratio == ratio
                                and (c.locale or "") == "creative"
                            ):
                                c.motion_path = motion_rel
                                break
                        flush_live_report()
            continue

        # Full pipeline already finalized each ratio above.

    finished = datetime.now(timezone.utc)
    image_keys = {(c.product, c.ratio) for c in creatives}
    from_provided_tiles = len(
        {(c.product, c.ratio) for c in creatives if c.source == "provided_image"}
    )
    concept_tiles = len(
        {(c.product, c.ratio) for c in creatives if c.source == "concept_generated"}
    )
    locales_used = sorted({c.locale for c in creatives})
    framing_used = _normalize_framing(
        framing_override
        or ("both" if (zoom_only or master_only) else None)
        or getattr(brief, "framing", None)
        or "both"
    )
    outputs_used = (
        ["1:1"]
        if zoom_only or master_only
        else _normalize_outputs(outputs_override or brief.outputs)
    )

    # Generate-more: merge this run into report.json without wiping other ratios.
    merged_creatives = list(creatives)
    if creatives_only:
        report_path = cdir / "report.json"
        if report_path.is_file():
            try:
                prior = json.loads(report_path.read_text(encoding="utf-8"))
                prior_rows = prior.get("creatives") if isinstance(prior, dict) else None
            except (OSError, json.JSONDecodeError):
                prior_rows = None
            if isinstance(prior_rows, list):
                replaced = {
                    (
                        str(c.product),
                        str(c.ratio).split("-")[0] if "-" in str(c.ratio) else str(c.ratio),
                        str(c.locale or "creative"),
                    )
                    for c in creatives
                }
                # Also treat base ratio matches (1:1 vs 1:1-tight) carefully:
                # drop prior rows whose base ratio was regenerated this run.
                regenerated_bases = {
                    str(c.ratio).split("-")[0] if str(c.ratio).count(":") else str(c.ratio)
                    for c in creatives
                }
                regenerated_bases |= set(outputs_used)
                kept: list[CreativeResult] = []
                for row in prior_rows:
                    if not isinstance(row, dict):
                        continue
                    try:
                        old = CreativeResult.model_validate(row)
                    except Exception:
                        continue
                    base = str(old.ratio).split("-")[0]
                    key = (str(old.product), base, str(old.locale or "creative"))
                    if base in regenerated_bases and str(old.locale or "creative") in {
                        "creative",
                        "motion",
                    }:
                        # Replaced by this run (or motion will re-attach from disk).
                        continue
                    if key in replaced:
                        continue
                    kept.append(old)
                merged_creatives = kept + list(creatives)

    report = Report(
        campaign_id=slug,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        storage_backend="local",
        creatives=merged_creatives,
        totals={
            "tiles": len(merged_creatives),
            "image_variants": len(image_keys),
            "from_provided": from_provided_tiles,
            "concept_generated": concept_tiles,
            "locales": len(locales_used),
            "text_render_mode": "none" if creatives_only else text_mode,
            "creatives_only": creatives_only,
            "ratio_strategy": "chained-ai-per-selected-ratio",
            "framing": framing_used,
            "outputs": outputs_used,
            "master_only": master_only,
            "zoom_only": zoom_only,
            "cost_usd_estimate": 0,
        },
    )
    write_report(cdir, report)
    try:
        from app.campaign_browser import mark_campaign_completed

        mark_campaign_completed(slug)
    except Exception:
        pass
    emit("run.completed", {"campaign_id": slug, "tiles": len(creatives)})
    logger.info(
        "Campaign %s complete: %s tiles (%s image variants, locales=%s, text=%s)",
        slug,
        len(creatives),
        len(image_keys),
        "creatives-only" if creatives_only else ",".join(locales_used),
        "none" if creatives_only else text_mode,
    )
    return report


def _ai_text_overlay(
    image_edit: OpenAIImageEditor,
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
    """AI typography for Finalize (_try_ai_text). Not used while inventing ratio stills."""
    width, height = RATIO_SIZES.get(ratio, (1080, 1080))
    tone = brief.brand_notes.tone or "premium advertising"
    colors = ", ".join(brief.brand_notes.colors) if brief.brand_notes.colors else ""
    font_hint = (
        ", ".join(brief.brand_notes.font_names)
        if brief.brand_notes.font_names
        else "clean modern sans"
    )
    parts: list[str] = []
    if message.strip():
        parts.append(f"Headline: {message.strip()}")
    if supporting.strip():
        parts.append(f"Sub-caption: {supporting.strip()}")
    if cta.strip():
        parts.append(f"CTA: {cta.strip()}")
    lines = "\n".join(parts)
    place = placement.strip() or "lower third"
    style_bit = style_notes.strip() or f"Style: {tone}. Typography feel: {font_hint}."
    fit_bit = fit_notes.strip() or f"Place readable type in the {place} with elegant hierarchy."
    prompt = (
        "Add professional social-ad typography to this exact image. "
        "Keep the product and scene unchanged. Do not restyle or recolor the photo. "
        f"Render this exact copy (character-accurate):\n{lines}\n"
        f"{style_bit} "
        f"{'Brand colors: ' + colors + '. ' if colors else ''}"
        f"{fit_bit} "
        "Keep all type fully inside safe margins. No extra slogans. "
        "Do not add legal disclaimers, fine print, or copyright lines."
    )
    try:
        return image_edit.adapt(
            image_bytes,
            width,
            height,
            prompt=prompt,
            reference_images=None,
            ratio=ratio,
            preserve_scene=True,
        )
    except Exception as exc:
        logger.warning("AI text overlay failed: %s", exc)
        return image_bytes, True


def _normalize_outputs(outputs: list[str] | None) -> list[str]:
    """Keep known ratios in request order; default all three if empty."""
    allowed = set(RATIO_ORDER)
    out: list[str] = []
    seen: set[str] = set()
    for raw in outputs or []:
        r = str(raw).strip()
        if r not in allowed or r in seen:
            continue
        seen.add(r)
        out.append(r)
    return out or list(RATIO_ORDER)


def _load_source_still_bytes(
    paths: list[str],
    root: Path,
    cdir: Path,
) -> list[bytes]:
    """Load existing creative stills to lock look for generate-more."""
    loaded: list[bytes] = []
    seen: set[str] = set()
    for raw in paths:
        text = str(raw or "").strip().replace("\\", "/")
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        if text.lower().endswith(".mp4"):
            continue
        candidates: list[Path] = []
        resolved = resolve_path(text, root)
        if resolved is not None:
            candidates.append(resolved)
        # Accept campaign-relative and /outputs/... forms from the UI.
        rel = text
        if rel.startswith("/outputs/"):
            rel = rel[len("/outputs/") :]
        if rel.startswith("outputs/"):
            rel = rel[len("outputs/") :]
        if rel.startswith("campaigns/"):
            parts = rel.split("/", 2)
            if len(parts) >= 3:
                rel = parts[2]
        candidates.append(cdir / rel)
        candidates.append(root / text)
        for candidate in candidates:
            try:
                if candidate.is_file():
                    loaded.append(candidate.read_bytes())
                    break
            except OSError:
                continue
    return loaded[:5]


def _normalize_framing(framing: str | None) -> FramingMode:
    f = (framing or "both").strip().lower().replace("_", "-")
    if f in {"close-up", "closeup", "tight"}:
        return "close-up"
    if f in {"zoomed", "zoom", "wide", "zoomed-out"}:
        return "zoomed"
    return "both"


def _collect_campaign_role_refs(
    brief: Brief, root: Path, *, product: Product | None = None
) -> tuple[list[bytes], str]:
    """Load likeness / style / background refs. Order: likeness, style, background.

    When product is set, prefer that product's style/background paths over campaign defaults.
    """
    from app.product_fields import product_background_paths, product_style_paths

    blobs: list[bytes] = []
    notes: list[str] = []

    def add(paths: list[str], label: str, limit: int) -> None:
        n = 0
        for raw in paths or []:
            if n >= limit:
                break
            resolved = resolve_path(raw, root)
            if resolved and resolved.exists():
                blobs.append(resolved.read_bytes())
                n += 1
        if n:
            notes.append(f"{label} reference ({n} image{'s' if n != 1 else ''})")

    add(list(brief.likeness_reference_paths or []), "character/actor likeness", 2)
    if product is not None:
        style_paths = product_style_paths(brief, product)
        bg_paths = product_background_paths(brief, product)
    else:
        style_paths = list(brief.style_reference_paths or [])
        bg_paths = list(brief.background_reference_paths or [])
    add(style_paths, "style/mood", 2)
    add(bg_paths, "background plate", 1)
    note = ""
    if notes:
        note = (
            "Use attached references as labeled: "
            + "; ".join(notes)
            + ". Match likeness identity when provided; match style lighting/mood; "
            "use background plate for environment when provided."
        )
    return blobs, note


def _normalize_locales(localize_to: list[str] | None) -> list[str]:
    raw = [x.strip() for x in (localize_to or ["en-US"]) if x and str(x).strip()]
    if not raw:
        raw = ["en-US"]
    seen: set[str] = set()
    out: list[str] = []
    for loc in raw:
        key = loc.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(loc)
    if len(out) > MAX_LOCALES:
        logger.warning(
            "localize_to has %s locales; capping at %s", len(out), MAX_LOCALES
        )
        out = out[:MAX_LOCALES]
    return out


def _maybe_motion(
    png_path: Path,
    brief: Brief,
    product_name: str,
    duration: int,
    *,
    root: Path | None = None,
    out_name: str | None = None,
) -> str | None:
    """Legacy CLI / pipeline motion helper.

    Christian: deprecated for the UI. Results uses main.create_motion instead
    (better errors + aspect_ratio). Kept for CLI --with-motion; safe to leave.
    """
    from app.config import motion_video_model, motion_video_resolution
    from app.providers import xai_video

    key = get_xai_api_key()
    prompt = brief.motion_notes or brief.creative_direction or brief.message
    prompt = f"{prompt} Product focus: {product_name}."
    name = out_name or (
        "creative.mp4" if png_path.stem.lower().startswith("creative") else "final.mp4"
    )
    out = png_path.with_name(name)
    result = xai_video.generate_motion(
        png_path,
        out,
        prompt=prompt,
        duration_seconds=duration,
        api_key=key,
        model=motion_video_model(),
        resolution=motion_video_resolution(),
    )
    if not result:
        return None
    base = root or PROJECT_ROOT
    try:
        return str(result.relative_to(base)).replace("\\", "/")
    except ValueError:
        return str(result).replace("\\", "/")


def _setup_file_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if not any(
        isinstance(h, logging.FileHandler)
        and getattr(h, "baseFilename", "") == str(log_path)
        for h in root.handlers
    ):
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        root.addHandler(fh)
    if not root.handlers:
        logging.basicConfig(level=logging.INFO)
    root.setLevel(logging.INFO)
