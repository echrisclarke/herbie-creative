from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from app.brief_loader import load_brief, missing_required_fields
from app.branding import print_cli_hero
from app.cli_progress import CliProgress
from app.config import (
    PROJECT_ROOT,
    get_openai_api_key,
    get_xai_api_key,
    image_quality_override,
    motion_duration_default,
    motion_video_model,
    motion_video_resolution,
)
from app.pipeline import run_campaign
from app.providers import xai_video
from app.storage.paths import campaign_dir, slugify_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("cli")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Creative automation CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run a structured campaign brief")
    run_p.add_argument("brief", type=str, help="Path to smoke-test.json or other brief")
    # Christian: legacy CLI flag. Product UX is Results → Animate. Still works for
    # smoke / demos that want a one-shot mp4 without the browser. Harmless.
    run_p.add_argument("--with-motion", action="store_true")
    run_p.add_argument("--motion-duration", type=int, default=6)
    run_p.add_argument("--campaign-id", type=str, default=None)
    run_p.add_argument(
        "--creatives-only",
        action="store_true",
        help="Generate no-text creatives only (skip localize/text finals)",
    )
    run_p.add_argument(
        "--outputs",
        type=str,
        default=None,
        help="Comma-separated ratios to generate, e.g. 1:1 or 1:1,9:16,16:9 "
        "(default: brief.outputs)",
    )
    run_p.add_argument(
        "--framing",
        choices=["close-up", "zoomed", "both"],
        default=None,
        help="Framing for the first selected ratio (default: brief.framing or both)",
    )
    run_p.add_argument(
        "--master-only",
        action="store_true",
        # Christian: deprecated alias; same as --outputs 1:1 --framing both.
        help="Deprecated: close-up + zoomed on 1:1 only (same as --outputs 1:1 --framing both)",
    )
    run_p.add_argument(
        "--zoom-only",
        action="store_true",
        help="Deprecated alias for --master-only",
    )
    run_p.add_argument(
        "--image-quality",
        choices=["low", "medium", "high"],
        default=None,
        help="GPT Image quality for this run (default: OPENAI_IMAGE_QUALITY or medium)",
    )
    run_p.add_argument(
        "--allow-single-product",
        action="store_true",
        help="Allow briefs with one product (content sample smokes). Local CLI still uses 2+.",
    )

    motion_p = sub.add_parser(
        "motion",
        help="Animate an existing creative still (post-generate Image-to-Video)",
    )
    motion_p.add_argument(
        "image",
        type=str,
        help="Path to creative.png / final.png (or any still)",
    )
    motion_p.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Motion prompt (default: subtle cinematic product motion)",
    )
    motion_p.add_argument(
        "--duration",
        type=int,
        default=None,
        help=f"Seconds 1-15 (default: {motion_duration_default()})",
    )
    motion_p.add_argument(
        "--resolution",
        choices=["480p", "720p", "1080p"],
        default=None,
        help=f"Output resolution (default: {motion_video_resolution()})",
    )
    motion_p.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output MP4 path (default: same folder as image, creative.mp4 / final.mp4)",
    )
    motion_p.add_argument(
        "--aspect-ratio",
        choices=["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
        default=None,
        help="Override output aspect (default: match source image)",
    )

    smoke_p = sub.add_parser(
        "smoke",
        aliases=["assignment"],
        help=(
            "Local CLI: Jordan hero zoom exercise coverage "
            "(2 products, 3 ratios, en/es/zh finals with legal, report)"
        ),
    )
    smoke_p.add_argument(
        "--image-quality",
        choices=["low", "medium", "high"],
        default="low",
        help="GPT Image quality (default: low for speed)",
    )
    smoke_p.add_argument(
        "--campaign-id",
        type=str,
        default=None,
        help="Optional campaign folder slug",
    )

    fin_p = sub.add_parser(
        "finalize",
        help="Vision suggest + Pillow finals from existing creatives",
    )
    fin_p.add_argument("campaign_id", type=str)
    fin_p.add_argument(
        "--brief",
        type=str,
        default=None,
        help="Brief JSON (default: campaigns/{id}/campaign.json)",
    )
    fin_p.add_argument(
        "--suggest-only",
        action="store_true",
        help="Only run vision suggest; do not write finals",
    )
    fin_p.add_argument(
        "--skip-suggest",
        action="store_true",
        help="Use existing finalize_style_suggest.json / brief copy only",
    )
    fin_p.add_argument(
        "--finalize-only",
        action="store_true",
        help="Alias: apply finals (same as default without --suggest-only)",
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command in ("smoke", "assignment"):
        return cmd_smoke(args)
    if args.command == "motion":
        return cmd_motion(args)
    if args.command == "finalize":
        return cmd_finalize(args)
    return 1


def _parse_outputs(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts or None


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    if path.exists():
        return path.resolve()
    alt = PROJECT_ROOT / path
    if alt.exists():
        return alt.resolve()
    return path


def cmd_motion(args: argparse.Namespace) -> int:
    print_cli_hero(subtitle="motion")
    key = get_xai_api_key()
    if not key:
        logger.error("XAI_API_KEY is required for motion")
        return 2

    image = _resolve_path(args.image)
    if not image.exists():
        logger.error("Image not found: %s", image)
        return 1

    if args.out:
        out = _resolve_path(args.out)
    else:
        stem = image.stem
        name = "final.mp4" if stem.startswith("final") else f"{stem}.mp4"
        out = image.with_name(name)

    prompt = args.prompt or (
        "Subtle cinematic motion for a premium product ad. "
        "Keep the exact product, composition, and lighting. Soft camera drift, "
        "gentle neon flicker, shallow depth of field. No new text, logos, or props."
    )
    duration = args.duration if args.duration is not None else motion_duration_default()
    resolution = args.resolution or motion_video_resolution()

    logger.info("Motion from %s -> %s (%ss %s)", image, out, duration, resolution)
    result = xai_video.generate_motion(
        image,
        out,
        prompt=prompt,
        duration_seconds=duration,
        api_key=key,
        model=motion_video_model(),
        resolution=resolution,
        aspect_ratio=args.aspect_ratio,
    )
    if not result:
        logger.error("Motion failed or was skipped")
        return 2
    print(f"Motion: {result}")
    return 0


SMOKE_BRIEF = PROJECT_ROOT / "sample-briefs" / "jordan-hero-zoom.json"


def cmd_smoke(args: argparse.Namespace) -> int:
    """Local CLI smoke: same Jordan hero zoom brief as the UI featured sample.

    Hits the exercise checklist: 2 products, 3 ratios, reuse assets, message+CTA+legal
    on en-US / es-ES / zh-CN finals, report + compliance. quality=low for demo speed.
    """
    from datetime import datetime

    from app.brief_loader import load_brief

    print_cli_hero(subtitle="local CLI")
    print("  Sample: Jordan hero zoom  (same brief as UI Sample briefs)")
    print("  Products: Frozen Moments AJ4 + Shattered Backboard AJ1")
    print("  Ratios 1:1 / 9:16 / 16:9  |  framing=zoomed  |  quality=low")
    print("  Finals: message + CTA + legal  |  locales: en-US, es-ES, zh-CN")
    print("  Reuses sample product assets  |  report.json + compliance checks")
    print("  Writes each tile as it finishes (Library / Gallery refresh live).")
    print(f"  Brief: {SMOKE_BRIEF}")
    print()

    if not SMOKE_BRIEF.exists():
        logger.error("Smoke brief not found: %s", SMOKE_BRIEF)
        return 1

    brief_preview = load_brief(SMOKE_BRIEF)
    legal = (brief_preview.legal_disclaimer or "").strip()
    print("-" * 72)
    print("  DISCLAIMER")
    if legal:
        # Wrap long legal for terminal readability.
        words = legal.split()
        line = "  "
        for word in words:
            if len(line) + len(word) + 1 > 70:
                print(line)
                line = "  " + word
            else:
                line = (line + " " + word).rstrip() if line.strip() else "  " + word
        if line.strip():
            print(line)
    else:
        print("  Unofficial test sample. Not a real Jordan / Nike advertisement.")
    print("-" * 72)
    print()

    # Prefer faster edit fidelity for smoke; UI fidelity work can stay high.
    os.environ["OPENAI_IMAGE_INPUT_FIDELITY"] = "low"

    campaign_id = args.campaign_id or (
        f"jordan-hero-zoom-cli-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )

    run_args = argparse.Namespace(
        brief=str(SMOKE_BRIEF),
        with_motion=False,
        motion_duration=6,
        campaign_id=campaign_id,
        creatives_only=False,
        outputs="1:1,9:16,16:9",
        framing=brief_preview.framing or "zoomed",
        master_only=False,
        zoom_only=False,
        image_quality=args.image_quality or "low",
        allow_single_product=False,
        locales_override=list(brief_preview.localize_to or ["en-US", "es-ES", "zh-CN"]),
        coverage_note=(
            "Same brief as UI Jordan hero zoom: Frozen Moments + Shattered Backboard, "
            "3 ratios, message+CTA+legal, en-US/es-ES/zh-CN, assets reused, report+compliance"
        ),
        _skip_hero=True,
    )
    return cmd_run(run_args)


def cmd_run(args: argparse.Namespace) -> int:
    if not getattr(args, "_skip_hero", False):
        print_cli_hero(subtitle="campaign run")

    brief_path = Path(args.brief)
    if not brief_path.is_absolute():
        if not brief_path.exists():
            alt = PROJECT_ROOT / brief_path
            if alt.exists():
                brief_path = alt
    try:
        brief = load_brief(brief_path)
    except Exception as exc:
        logger.error("Validation error: %s", exc)
        return 1

    missing = missing_required_fields(
        brief,
        require_two_products=not (
            args.master_only
            or args.zoom_only
            or args.creatives_only
            or args.allow_single_product
        ),
    )
    if brief.products and (args.master_only or args.zoom_only):
        brief.products = brief.products[:1]
    if missing:
        logger.error("Missing required fields: %s", ", ".join(missing))
        return 1

    if not get_openai_api_key():
        logger.error("OPENAI_API_KEY is required")
        return 2

    for product in brief.products:
        if product.input_asset_path and not Path(product.input_asset_path).is_absolute():
            candidate = PROJECT_ROOT / product.input_asset_path
            if candidate.exists():
                product.input_asset_path = str(candidate)
        resolved_extras: list[str] = []
        for extra in product.input_asset_paths:
            path = Path(extra)
            if not path.is_absolute():
                candidate = PROJECT_ROOT / extra
                path = candidate if candidate.exists() else path
            if path.exists():
                resolved_extras.append(str(path))
            else:
                resolved_extras.append(extra)
        product.input_asset_paths = resolved_extras
    if brief.brand_notes.logo_path and not Path(brief.brand_notes.logo_path).is_absolute():
        logo = PROJECT_ROOT / brief.brand_notes.logo_path
        if logo.exists():
            brief.brand_notes.logo_path = str(logo)

    for attr in (
        "style_reference_paths",
        "likeness_reference_paths",
        "background_reference_paths",
    ):
        resolved: list[str] = []
        for raw in getattr(brief, attr) or []:
            path = Path(raw)
            if not path.is_absolute():
                candidate = PROJECT_ROOT / raw
                path = candidate if candidate.exists() else path
            resolved.append(str(path) if path.exists() else raw)
        setattr(brief, attr, resolved)

    outputs_override = _parse_outputs(args.outputs)
    framing_override = args.framing
    if args.master_only or args.zoom_only:
        outputs_override = ["1:1"]
        framing_override = framing_override or "both"

    outputs = outputs_override or list(brief.outputs) or ["1:1", "9:16", "16:9"]
    framing = framing_override or getattr(brief, "framing", None) or "both"
    locales_override = getattr(args, "locales_override", None)
    if locales_override:
        brief.localize_to = list(locales_override)
    locales = list(brief.localize_to or ["en-US"])
    outputs_by_product = getattr(args, "outputs_by_product", None)
    finalize_ratios_by_product = getattr(args, "finalize_ratios_by_product", None)
    bonus_locale = getattr(args, "bonus_locale", None)
    coverage_note = getattr(args, "coverage_note", None)

    progress = CliProgress()
    progress.quiet_app_logs()
    slug = args.campaign_id or slugify_name(brief.campaign_name)
    out_folder = campaign_dir(slug)
    progress.plan(
        campaign=brief.campaign_name or brief_path.name,
        products=[p.name for p in brief.products],
        outputs=outputs,
        framing=framing,
        locales=locales,
        creatives_only=bool(args.creatives_only),
        with_motion=bool(args.with_motion),
        image_quality=args.image_quality or "medium",
        outputs_by_product=outputs_by_product,
        finalize_ratios_by_product=finalize_ratios_by_product,
        bonus_locale=bonus_locale,
        coverage_note=coverage_note,
    )
    progress.note_live_folder(str(out_folder), campaign_id=slug)

    try:
        with image_quality_override(args.image_quality):
            report = run_campaign(
                brief,
                campaign_slug=slug,
                project_root=PROJECT_ROOT,
                with_motion=args.with_motion,
                motion_duration=args.motion_duration,
                creatives_only=args.creatives_only,
                master_only=args.master_only,
                zoom_only=args.zoom_only,
                outputs_override=outputs_override,
                framing_override=framing_override,
                on_event=progress.on_event,
                outputs_by_product=outputs_by_product,
                finalize_ratios_by_product=finalize_ratios_by_product,
                bonus_locale=bonus_locale,
            )
    except ValueError as exc:
        progress.fail(str(exc))
        logger.error("Validation error: %s", exc)
        return 1
    except Exception as exc:
        progress.fail(str(exc))
        logger.exception("Provider/API failure: %s", exc)
        return 2

    print(f"  Campaign folder: campaigns/{report.campaign_id}/")
    print(f"  Strategy: {report.totals.get('ratio_strategy')}")
    print(f"  Framing: {report.totals.get('framing')}")
    print(f"  Outputs: {report.totals.get('outputs')}")
    print(
        "  Sources: provided_image="
        f"{report.totals.get('from_provided')} "
        f"concept_generated={report.totals.get('concept_generated')}"
    )
    locales_seen = sorted(
        {c.locale for c in report.creatives if c.locale not in {"creative", "motion"}}
    )
    if locales_seen:
        print(f"  Locales on finals: {', '.join(locales_seen)}")
    compliance_rows = [c for c in report.creatives if c.compliance]
    if compliance_rows:
        ok = sum(1 for c in compliance_rows if all(c.compliance.values()))
        print(
            f"  Compliance: {ok}/{len(compliance_rows)} tiles passed "
            "(logo / colors / forbidden words / CTA)"
        )
    print()
    print("  Files:")
    for c in report.creatives:
        print(f"    [{c.source}] {c.product} {c.ratio} ({c.locale}) -> {c.path}")
        if c.motion_path:
            print(f"      motion -> {c.motion_path}")
        if c.compliance:
            flags = ", ".join(f"{k}={'ok' if v else 'flag'}" for k, v in c.compliance.items())
            print(f"      compliance: {flags}")
    print()
    print(f"  Report: campaigns/{report.campaign_id}/report.json")
    print()
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    from app.finalize import finalize_campaign, run_suggest_finalize
    from app.schemas import Brief, FinalizeChoices

    if not get_openai_api_key():
        logger.error("OPENAI_API_KEY is required")
        return 2

    cdir = PROJECT_ROOT / "campaigns" / args.campaign_id
    if not cdir.exists():
        logger.error("Campaign not found: %s", args.campaign_id)
        return 1

    if args.brief:
        brief_path = _resolve_path(args.brief)
        brief = Brief.model_validate_json(brief_path.read_text(encoding="utf-8"))
    else:
        camp = cdir / "campaign.json"
        if not camp.exists():
            logger.error("No campaign.json and no --brief given")
            return 1
        brief = Brief.model_validate_json(camp.read_text(encoding="utf-8"))

    try:
        if args.suggest_only:
            style = run_suggest_finalize(args.campaign_id, brief)
            print(json.dumps(style, indent=2, ensure_ascii=False))
            return 0
        report = finalize_campaign(
            args.campaign_id,
            FinalizeChoices(skip_suggest=args.skip_suggest),
            brief=brief,
            run_suggest=not args.skip_suggest,
        )
    except Exception as exc:
        logger.exception("Finalize failed: %s", exc)
        return 2

    print(f"Finals: {report.totals.get('finals')}")
    for c in report.creatives:
        if c.locale != "creative":
            print(f"  {c.product} {c.ratio} {c.locale} -> {c.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
