from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT, get_openai_api_key
from app.providers.openai_image import OpenAIImageGenerator
from app.schemas import Brief, Product, ProductMode
from app.sse import bus
from app.storage.paths import campaign_dir, slugify_name

logger = logging.getLogger(__name__)

STATUS_FILE = "product_seeds.json"


def _status_path(campaign_id: str) -> Path:
    return campaign_dir(campaign_id) / STATUS_FILE


def load_product_seeds_status(campaign_id: str) -> dict[str, Any]:
    path = _status_path(campaign_id)
    if not path.exists():
        return {
            "status": "idle",
            "needed": False,
            "items": [],
            "error": None,
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "status": "failed",
            "needed": True,
            "items": [],
            "error": "Could not read product seed status.",
        }


def write_product_seeds_status(campaign_id: str, payload: dict[str, Any]) -> None:
    path = _status_path(campaign_id)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _path_exists(raw: str | None) -> bool:
    if not raw:
        return False
    p = Path(raw)
    if p.exists():
        return True
    candidate = PROJECT_ROOT / raw
    return candidate.exists()


def products_needing_seeds(brief: Brief) -> list[Product]:
    """Products with no on-disk hero image yet."""
    return [p for p in brief.products if not _path_exists(p.input_asset_path)]


def init_product_seeds_status(campaign_id: str, brief: Brief) -> dict[str, Any]:
    needed = products_needing_seeds(brief)
    if not needed:
        payload = {
            "status": "ready",
            "needed": False,
            "items": [],
            "error": None,
        }
        write_product_seeds_status(campaign_id, payload)
        return payload

    payload = {
        "status": "pending",
        "needed": True,
        "items": [
            {
                "product_name": p.name,
                "status": "pending",
                "path": None,
                "error": None,
            }
            for p in needed
        ],
        "error": None,
    }
    write_product_seeds_status(campaign_id, payload)
    return payload


def build_product_seed_prompt(
    brief: Brief, product: Product, *, with_likeness: bool = False
) -> str:
    from app.product_fields import product_direction

    tags = ", ".join(brief.visual_style_tags) if brief.visual_style_tags else "clean product photography"
    colors = ", ".join(brief.brand_notes.colors) if brief.brand_notes.colors else ""
    direction = product_direction(brief, product)
    if with_likeness:
        parts = [
            f"Advertising still of the character from the attached likeness reference(s), for {product.name}.",
            f"Brand: {brief.brand or 'the brand'}.",
            f"Category: {product.category or 'product'}.",
            f"Role: {product.product_role.value}.",
            f"Creative direction: {direction}." if direction else "",
            f"Visual style: {tags}.",
            f"Brand colors: {colors}." if colors else "",
            f"Asset hint: {product.asset_hint}." if product.asset_hint else "",
            f"Notes: {product.notes}." if product.notes else "",
            "Keep the character identity faithful to the likeness reference: face, proportions, costume.",
            "Show the product clearly when the brief calls for it.",
            "No text, no typography, no letters, no numbers, no watermarks, no logos baked into the image,",
            "no captions, no brand wordmarks on the photo itself.",
            "Not an ad layout. Not a social post mock. Square composition, high production value.",
        ]
        return " ".join(p for p in parts if p)

    parts = [
        f"Studio product photograph of {product.name}.",
        f"Brand: {brief.brand or 'the brand'}.",
        f"Category: {product.category or 'product'}.",
        f"Role: {product.product_role.value}.",
        f"Creative direction: {direction}." if direction else "",
        f"Visual style: {tags}.",
        f"Brand colors: {colors}." if colors else "",
        f"Asset hint: {product.asset_hint}." if product.asset_hint else "",
        f"Notes: {product.notes}." if product.notes else "",
        "Single product hero shot on a simple complementary background.",
        "Show the real physical product clearly. Accurate materials, silhouette, and details.",
        "No text, no typography, no letters, no numbers, no watermarks, no logos baked into the image,",
        "no captions, no packaging labels with readable words, no brand wordmarks on the photo itself.",
        "Not an ad layout. Not a social post mock. Pure product photography only.",
        "Square composition, centered, high production value, soft studio lighting.",
    ]
    return " ".join(p for p in parts if p)


def _product_wants_likeness(product: Product) -> bool:
    blob = " ".join(
        [
            product.name,
            product.asset_hint or "",
            product.notes or "",
            product.product_role.value,
        ]
    ).lower()
    return any(
        k in blob
        for k in (
            "likeness",
            "character",
            "wearing",
            "actor",
            "person",
            "portrait",
            "face",
            "semi",
            "baba",
            "bao",
        )
    )


def _load_image_bytes(paths: list[str], *, limit: int = 2) -> list[bytes]:
    from app.asset_manifest import resolve_path

    out: list[bytes] = []
    for raw in paths or []:
        if len(out) >= limit:
            break
        resolved = resolve_path(raw, PROJECT_ROOT)
        if resolved and resolved.exists():
            out.append(resolved.read_bytes())
    return out


def run_product_seeds_job(campaign_id: str, loop: asyncio.AbstractEventLoop) -> None:
    from app.fastapi_intake import load_campaign_brief, save_campaign_brief
    from app.providers.openai_editor import OpenAIImageEditor

    try:
        if not get_openai_api_key():
            payload = load_product_seeds_status(campaign_id)
            payload["status"] = "failed"
            payload["error"] = "OpenAI API key required to generate product photos."
            for item in payload.get("items") or []:
                if item.get("status") == "pending":
                    item["status"] = "failed"
                    item["error"] = payload["error"]
            write_product_seeds_status(campaign_id, payload)
            bus.publish_threadsafe(
                loop,
                campaign_id,
                "product_seeds.failed",
                {"error": payload["error"]},
            )
            return

        brief = load_campaign_brief(campaign_id)
        needed = products_needing_seeds(brief)
        if not needed:
            payload = {
                "status": "ready",
                "needed": False,
                "items": [],
                "error": None,
            }
            write_product_seeds_status(campaign_id, payload)
            bus.publish_threadsafe(
                loop, campaign_id, "product_seeds.ready", {"needed": False}
            )
            return

        status = init_product_seeds_status(campaign_id, brief)
        bus.publish_threadsafe(
            loop,
            campaign_id,
            "product_seeds.started",
            {"count": len(needed)},
        )

        product_dir = campaign_dir(campaign_id) / "uploads" / "product"
        product_dir.mkdir(parents=True, exist_ok=True)
        image_gen = OpenAIImageGenerator()
        image_editor: OpenAIImageEditor | None = None

        for product in needed:
            # Re-load in case Review uploaded an image while we were working
            brief = load_campaign_brief(campaign_id)
            live = next((p for p in brief.products if p.name == product.name), None)
            if live is None:
                continue
            if _path_exists(live.input_asset_path):
                for item in status["items"]:
                    if item["product_name"] == product.name:
                        item["status"] = "ready"
                        item["path"] = live.input_asset_path
                write_product_seeds_status(campaign_id, status)
                continue

            bus.publish_threadsafe(
                loop,
                campaign_id,
                "product_seed.started",
                {"product": product.name},
            )
            try:
                likeness_blobs = _load_image_bytes(
                    list(brief.likeness_reference_paths or []), limit=2
                )
                use_likeness = bool(likeness_blobs) and _product_wants_likeness(live)
                prompt = build_product_seed_prompt(
                    brief, live, with_likeness=use_likeness
                )
                if use_likeness:
                    if image_editor is None:
                        image_editor = OpenAIImageEditor()
                    png, _ = image_editor.adapt(
                        likeness_blobs[0],
                        1024,
                        1024,
                        prompt=prompt,
                        reference_images=likeness_blobs[1:],
                        ratio="1:1",
                    )
                else:
                    png = image_gen.generate(prompt, ratio="1:1")
                filename = f"{slugify_name(live.name)}-seed.png"
                dest = product_dir / filename
                dest.write_bytes(png)
                try:
                    rel = str(dest.relative_to(PROJECT_ROOT)).replace("\\", "/")
                except ValueError:
                    rel = str(dest)

                brief = load_campaign_brief(campaign_id)
                for p in brief.products:
                    if p.name == live.name and not _path_exists(p.input_asset_path):
                        p.input_asset_path = rel
                        # Seed is a real product photo for Review and Generate.
                        if p.product_mode == ProductMode.GENERATE_CONCEPT:
                            p.product_mode = ProductMode.USE_PROVIDED
                        break
                save_campaign_brief(campaign_id, brief)

                for item in status["items"]:
                    if item["product_name"] == product.name:
                        item["status"] = "ready"
                        item["path"] = rel
                        item["error"] = None
                write_product_seeds_status(campaign_id, status)
                bus.publish_threadsafe(
                    loop,
                    campaign_id,
                    "product_seed.completed",
                    {"product": product.name, "path": rel},
                )
            except Exception as exc:
                logger.exception("Product seed failed for %s", product.name)
                for item in status["items"]:
                    if item["product_name"] == product.name:
                        item["status"] = "failed"
                        item["error"] = str(exc)
                status["status"] = "failed"
                status["error"] = str(exc)
                write_product_seeds_status(campaign_id, status)
                bus.publish_threadsafe(
                    loop,
                    campaign_id,
                    "product_seed.failed",
                    {"product": product.name, "error": str(exc)},
                )
                bus.publish_threadsafe(
                    loop,
                    campaign_id,
                    "product_seeds.failed",
                    {"error": str(exc)},
                )
                return

        status["status"] = "ready"
        status["error"] = None
        write_product_seeds_status(campaign_id, status)
        # Reload brief so clients get attached paths
        brief = load_campaign_brief(campaign_id)
        bus.publish_threadsafe(
            loop,
            campaign_id,
            "product_seeds.ready",
            {
                "needed": True,
                "brief": brief.model_dump(),
            },
        )
    except Exception as exc:
        logger.exception("Product seeds job failed: %s", exc)
        payload = load_product_seeds_status(campaign_id)
        payload["status"] = "failed"
        payload["error"] = str(exc)
        write_product_seeds_status(campaign_id, payload)
        bus.publish_threadsafe(
            loop, campaign_id, "product_seeds.failed", {"error": str(exc)}
        )


def product_seeds_block_approve(campaign_id: str) -> str | None:
    """Return a blocker message if seeds are still required, else None."""
    from app.fastapi_intake import load_campaign_brief

    try:
        brief = load_campaign_brief(campaign_id)
    except FileNotFoundError:
        return None

    still_needed = products_needing_seeds(brief)
    status = load_product_seeds_status(campaign_id)

    if not still_needed:
        if status.get("needed") and status.get("status") != "ready":
            write_product_seeds_status(
                campaign_id,
                {
                    "status": "ready",
                    "needed": False,
                    "items": status.get("items") or [],
                    "error": None,
                },
            )
        return None

    state = status.get("status")
    if state == "pending" or (status.get("needed") and state not in {"ready", "failed"}):
        return "Product photos are still generating. Wait until they appear in Review."
    if state == "failed":
        return status.get("error") or "Product photo generation failed. Retry or upload photos."
    # Seeds were needed but status says ready while paths are still missing
    if still_needed:
        return "Each product needs a photo before you can approve. Wait for generation or upload one."
    return None
