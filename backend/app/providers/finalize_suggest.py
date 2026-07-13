"""Vision + brief-aware finalize suggestions (colors, placement, localized copy).

Brand-agnostic. Same path for every campaign. Concept-preserving localization:
adapt meaning to the brief/product, do not literal-translate English word salad.
"""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

from openai import OpenAI

from app.config import get_openai_api_key
from app.schemas import Brief

logger = logging.getLogger(__name__)

SUGGEST_SYSTEM = """You are an art director finishing social ads.
Overlays are applied later with Pillow (not baked into the photo).

You receive:
1) Campaign brief JSON (brand, product names, per-product message/CTA/creative_direction when set, tone, locales)
When products have different messages or scenes, keep suggestions concept-true to each product; do not blend copy across products.
2) One or more no-text creative stills

Return ONLY valid JSON:
{
  "logo_color": "#FFFFFF",
  "text_color": "#FFFFFF",
  "cta_accent": "#E8E4DC",
  "logo_placement": "top-left",
  "text_placement": "bottom-center",
  "font_names": ["family that fits"],
  "text_scrim": false,
  "text_scrim_opacity": 0.0,
  "text_shadow_opacity": 0.55,
  "styling_notes": "short note explaining overlay choices from the stills",
  "locales": {
    "en-US": { "message": "...", "cta": "..." },
    "es-ES": { "message": "...", "cta": "..." }
  }
}

Include every language/locale listed in brief.localize_to (keys must match exactly).
Values may be English language names (e.g. "Spanish", "Chinese (Mandarin)", "Klingon")
or BCP-47 codes. Write natural copy in that language (constructed languages OK).

Overlay / opacity rules (look at the stills; decide per campaign):
- text_placement: one of bottom-left, bottom-center, bottom-right, middle-left,
  middle-center, middle-right, top-left, top-center, top-right, or none.
  Prefer bottom-center for 1:1 and 9:16. Prefer top-right for 16:9 (horizontal)
  unless the still has a clearer open band elsewhere. Use none
  only when the creative should stay text-free (logo-only).
- text_scrim: soft dark gradient behind type. true only if white/light type would struggle on the lower third without help.
- text_scrim_opacity: 0.0–1.0. Use 0 when scrim is off. Prefer light values (0.25–0.55) when needed; avoid heavy black bars on clean studio shots.
- text_shadow_opacity: 0.0–1.0 soft drop shadow on type. Often enough alone on mid-grey grounds (0.4–0.7) with text_scrim false.
- Prefer NO scrim on clean mid-grey / concrete studio when type + shadow already reads.
- Prefer a light scrim when the type area is bright, busy, patterned, or high-contrast.
- Colors must read on the actual stills (flat dark logos usually need light tint on mid/dark grounds).

Copy rules (critical):
- locales keys MUST match brief.localize_to exactly (e.g. "Bengali", "Elvish (Quenya)").
- For each non-English locale, message and cta MUST be written IN that language
  (Bengali → Bengali script; Elvish → Quenya/Sindarin wording; never leave English).
- Preserve the campaign CONCEPT and product naming idea, not English word order.
- If the product/campaign is built on a metaphor (e.g. "Frozen Moments" = freezing time / capturing a peak instant), EVERY locale must carry that same metaphor in natural local ad language.
- Do NOT produce vague premium lines that drop the concept ("an instant / eternal movement" with no freeze/capture idea).
- Prefer adapting the approved English message/CTA intent; you may sharpen English slightly for overlay length.
- Spanish / Chinese / other: natural market ad copy, not awkward literal translation.
- Keep headlines short enough for 1:1 / 9:16 / 16:9 overlays.
- Tone matches brand_notes.tone when present.
- For game / collectible / Card-o-Bot style briefs: write like a fun game-ad teaser. Intrigue first. Do NOT explain the product. Avoid on-the-nose lines like "your deck made in the app." Borrow energy from arcade, collectible drops, and cyberpunk game marketing without naming other brands. Short mystery headline + short CTA (often a URL or enter vibe). Pixel/arcade voice is fine when fonts are pixel.
"""


def suggest_finalize(
    brief: Brief,
    creative_paths: list[Path],
    *,
    logo_path: Path | None = None,
    model: str = "gpt-5.6",
) -> dict:
    key = get_openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required")
    client = OpenAI(api_key=key)

    brief_payload = {
        "campaign_name": brief.campaign_name,
        "brand": brief.brand,
        "audience": brief.audience,
        "message": brief.message,
        "cta": brief.cta,
        "creative_direction": brief.creative_direction,
        "visual_style_tags": brief.visual_style_tags,
        "products": [
            {
                "name": p.name,
                "category": p.category,
                "product_role": p.product_role.value,
                "notes": p.notes,
                "asset_hint": p.asset_hint,
                "message": p.message or brief.message,
                "cta": p.cta or brief.cta,
                "creative_direction": p.creative_direction or brief.creative_direction,
            }
            for p in brief.products
        ],
        "tone": brief.brand_notes.tone,
        "colors": brief.brand_notes.colors,
        "font_names": brief.brand_notes.font_names,
        "localize_to": brief.localize_to,
    }

    content: list[dict] = [
        {
            "type": "input_text",
            "text": (
                "Brief JSON:\n"
                + json.dumps(brief_payload, ensure_ascii=False, indent=2)
                + "\n\nRecommend overlay styling and concept-true localized copy."
            ),
        }
    ]
    for path in creative_paths:
        if path.exists():
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{_b64(path)}",
                    "detail": "high",
                }
            )
    if logo_path and logo_path.exists():
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{_b64(logo_path)}",
                "detail": "low",
            }
        )
        content.append(
            {
                "type": "input_text",
                "text": "Last image is the logo asset (often flat black + alpha). Suggest logo_color so it reads on the creatives.",
            }
        )

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": SUGGEST_SYSTEM},
            {"role": "user", "content": content},
        ],
    )
    text = (resp.output_text or "").strip()
    data = _parse_json(text)
    data = _normalize_locales(data, brief.localize_to)
    # Vision models often leave every locale in English. Dedicated localize_pair
    # is what the creatives pipeline uses; reuse it for Pillow finalize copy.
    try:
        from app.providers.openai_writer import fill_localized_copy

        data["locales"] = fill_localized_copy(brief, data.get("locales"))
    except Exception:
        logger.exception("fill_localized_copy failed; keeping suggest locales")
    return data


def _b64(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode("ascii")


def _parse_json(text: str) -> dict:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()
    return json.loads(raw)


def _normalize_locales(data: dict, localize_to: list[str]) -> dict:
    """Accept either locales{} or legacy message_en / message_es fields."""
    locales = dict(data.get("locales") or {})
    legacy_map = {
        "en-US": ("message_en", "cta_en"),
        "es-ES": ("message_es", "cta_es"),
        "zh-CN": ("message_zh", "cta_zh"),
    }
    for loc, (mk, ck) in legacy_map.items():
        if loc not in locales and data.get(mk):
            locales[loc] = {
                "message": data.get(mk, ""),
                "cta": data.get(ck, ""),
            }
    wanted = [x for x in (localize_to or ["English"]) if x] or ["English"]
    for loc in wanted:
        if loc not in locales:
            logger.warning("suggest_finalize missing locale %s", loc)
            locales[loc] = {"message": "", "cta": ""}
    data["locales"] = {loc: locales[loc] for loc in wanted if loc in locales}
    return data
