from __future__ import annotations

import json
import logging
from pathlib import Path

from openai import OpenAI

from app.config import get_openai_api_key
from app.schemas import Brief, BrandNotes, Product, ProductMode, ProductRole

logger = logging.getLogger(__name__)


def _is_english_locale(locale: str) -> bool:
    loc = (locale or "").strip().lower()
    if not loc:
        return True
    if loc in {"en", "en-us", "en-gb", "en-au", "en-ca", "english"}:
        return True
    return loc.startswith("english ") or loc.startswith("en-")


# Keep in sync with frontend/src/lib/languages.ts aliases.
_LANGUAGE_ALIASES: dict[str, str] = {
    "en": "English",
    "en-us": "English",
    "en-gb": "English",
    "en-au": "English",
    "en-ca": "English",
    "english": "English",
    "es": "Spanish",
    "es-es": "Spanish",
    "es-mx": "Spanish",
    "es-us": "Spanish",
    "es-ar": "Spanish",
    "spanish": "Spanish",
    "zh": "Chinese (Mandarin)",
    "zh-cn": "Chinese (Mandarin)",
    "zh-hans": "Chinese (Mandarin)",
    "zh-sg": "Chinese (Mandarin)",
    "chinese (mandarin)": "Chinese (Mandarin)",
    "zh-hk": "Chinese (Cantonese)",
    "zh-tw": "Chinese (Cantonese)",
    "yue": "Chinese (Cantonese)",
    "fr": "French",
    "fr-fr": "French",
    "fr-ca": "French",
    "de": "German",
    "de-de": "German",
    "pt-br": "Portuguese (Brazil)",
    "pt": "Portuguese (Portugal)",
    "pt-pt": "Portuguese (Portugal)",
    "ja": "Japanese",
    "ja-jp": "Japanese",
    "ko": "Korean",
    "ko-kr": "Korean",
    "hi": "Hindi",
    "hi-in": "Hindi",
    "ar": "Arabic",
    "ru": "Russian",
}


def normalize_language_id(raw: str) -> str:
    """Map BCP-47 / alias codes to the display language ids the UI uses."""
    trimmed = (raw or "").strip()
    if not trimmed:
        return "English"
    mapped = _LANGUAGE_ALIASES.get(trimmed.lower())
    if mapped:
        return mapped
    return trimmed


def copy_looks_untranslated(candidate: str, source: str) -> bool:
    """True when candidate is empty or still essentially the English source."""
    import difflib

    a = (candidate or "").strip()
    b = (source or "").strip()
    if not a:
        return True
    if not b:
        return False
    if a.lower() == b.lower():
        return True
    # Non-Latin scripts (Bengali, CJK, Arabic, etc.) are clearly translated.
    if any(ord(ch) > 0x024F for ch in a):
        return False
    ratio = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return ratio >= 0.72


def fill_localized_copy(
    brief: Brief,
    locales: dict | None = None,
    *,
    language_list: list[str] | None = None,
    force: bool = False,
    product: Product | None = None,
) -> dict[str, dict[str, str]]:
    """Ensure every language has real target-language message/CTA.

    Vision suggest often returns English for every key. Pipeline-style
    localize_pair is the reliable path for Pillow composer overlays.
    When force=True, re-adapt non-source locales from the current brief
    message/CTA (used when the source language was edited in Finalize).
    """
    writer = OpenAIWriter()
    existing = locales or {}
    wanted_raw = language_list if language_list is not None else (brief.localize_to or ["English"])
    wanted = [normalize_language_id(x) for x in wanted_raw]
    # De-dupe after alias fold (en-US + English → one English slot).
    seen: set[str] = set()
    wanted_unique: list[str] = []
    for loc in wanted:
        key = loc.lower()
        if key in seen:
            continue
        seen.add(key)
        wanted_unique.append(loc)
    wanted = wanted_unique
    out: dict[str, dict[str, str]] = {}
    source_msg = (brief.message or "").strip()
    source_cta = (brief.cta or "").strip()
    source_sup = (brief.supporting_copy or "").strip()
    for loc in wanted:
        prev = existing.get(loc) or existing.get(normalize_language_id(loc)) or {}
        if isinstance(prev, dict):
            msg = str(prev.get("message") or "").strip()
            cta = str(prev.get("cta") or "").strip()
            supporting = str(prev.get("supporting") or "").strip()
        else:
            msg, cta, supporting = "", "", ""

        if _is_english_locale(loc):
            # Approved brief / Finalize source wins over vision inventing a new English line.
            out[loc] = {
                "message": source_msg or msg,
                "cta": source_cta or cta,
                "supporting": source_sup or supporting,
            }
            continue

        # Keep a real translation; rewrite when empty, still English, or forced.
        if (
            not force
            and msg
            and cta
            and not copy_looks_untranslated(msg, source_msg)
            and not copy_looks_untranslated(cta, source_cta)
        ):
            out[loc] = {
                "message": msg,
                "cta": cta,
                "supporting": supporting or source_sup,
            }
            continue

        msg_l, cta_l = writer.localize_pair(
            source_msg, source_cta, loc, brief=brief, product=product
        )
        if copy_looks_untranslated(msg_l, source_msg):
            logger.warning("localize_pair still English for %s; retrying harder", loc)
            msg_l, cta_l = writer.localize_pair(
                source_msg,
                source_cta,
                loc,
                brief=brief,
                product=product,
                strict=True,
            )
        supporting_l = supporting
        if force or not supporting:
            if source_sup:
                supporting_l, _ = writer.localize_pair(
                    source_sup,
                    source_cta or "Go",
                    loc,
                    brief=brief,
                    product=product,
                )
            else:
                supporting_l = ""
        out[loc] = {"message": msg_l, "cta": cta_l, "supporting": supporting_l}
    return out


PARSE_SYSTEM = """You extract structured campaign briefs for a creative automation pipeline.
Return ONLY valid JSON matching this shape:
{
  "campaign_name": string,
  "brand": string,
  "market": string,
  "audience": string,
  "message": string,
  "cta": string,
  "creative_direction": string,
  "visual_style_tags": string[],
  "motion_notes": string,
  "products": [{
    "name": string,
    "category": string,
    "product_mode": "use-provided" | "generate-concept",
    "product_role": "product_hero" | "feature" | "lifestyle_angle" | "service_angle" | "drop_announcement",
    "asset_hint": string,
    "message": string,
    "cta": string,
    "creative_direction": string,
    "input_asset_path": null,
    "landing_url": null,
    "notes": string
  }],
  "brand_notes": {
    "tone": string,
    "colors": string[],
    "font_names": string[],
    "font_alternates": string[],
    "logo_required": false,
    "logo_path": null,
    "logo_placement": "top-left",
    "forbidden_words": string[]
  },
  "localize_to": ["en-US"],
  "outputs": ["1:1", "9:16", "16:9"],
  "framing": "both"
}
Rules:
- Need at least 2 products when the brief mentions multiple products; invent a second concept product if only one is named.
- Prefer product_mode generate-concept when no product photo is supplied in the brief paths.
  Use use-provided only when input_asset_path (or clear packshot expectation with a path) is present.
  Lifestyle / drop / service angles should be generate-concept.
- When products are distinct SKUs/stories, give each its own message, cta, and creative_direction.
  Do not reuse one product's headline or scene for another.
- Suggest Google Fonts family names in font_names[0] that fit the brief; put 2-3 alternates in font_alternates if the brief names a non-Google font.
- Do not invent brand-specific code paths; only fill data fields.
"""


class OpenAIWriter:
    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or get_openai_api_key()
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required")
        self.client = OpenAI(api_key=key)

    def parse_brief(self, text: str) -> Brief:
        response = self.client.chat.completions.create(
            model="gpt-4.1",
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": PARSE_SYSTEM},
                {"role": "user", "content": text},
            ],
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return Brief.model_validate(data)

    def extract_text_from_pdf(self, path: Path) -> str:
        """Ask ChatGPT to read a PDF and return the campaign brief text."""
        pdf_path = Path(path)
        with pdf_path.open("rb") as handle:
            uploaded = self.client.files.create(file=handle, purpose="user_data")
        try:
            # Prefer Responses API with native PDF input when available.
            try:
                response = self.client.responses.create(
                    model="gpt-4.1",
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_file", "file_id": uploaded.id},
                                {
                                    "type": "input_text",
                                    "text": (
                                        "Read this PDF campaign brief completely. "
                                        "Return ONLY the extracted plain text of the brief "
                                        "(all campaign details, products, messaging, direction). "
                                        "Do not summarize. Do not add commentary."
                                    ),
                                },
                            ],
                        }
                    ],
                )
                text = getattr(response, "output_text", None) or ""
                if not text and getattr(response, "output", None):
                    parts: list[str] = []
                    for item in response.output:
                        for block in getattr(item, "content", None) or []:
                            if getattr(block, "type", "") in {"output_text", "text"}:
                                parts.append(getattr(block, "text", "") or "")
                    text = "\n".join(parts)
                if text.strip():
                    return text.strip()
            except Exception:
                logger.exception("responses PDF extract failed; trying chat fallback")

            from app.document_text import _extract_pdf_with_pypdf

            partial = _extract_pdf_with_pypdf(pdf_path)
            prompt = (
                "The following text was extracted from a campaign brief PDF "
                "(may be incomplete). Reconstruct the full usable brief text "
                "as plain text only, no commentary:\n\n"
                f"{partial or '(no extractable text — describe that the PDF could not be read)'}"
            )
            response = self.client.chat.completions.create(
                model="gpt-4.1",
                temperature=0.1,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You recover campaign brief text from PDF extracts. "
                            "Return plain brief text only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            return (response.choices[0].message.content or "").strip()
        finally:
            try:
                self.client.files.delete(uploaded.id)
            except Exception:
                pass

    def generate_copy(self, brief: Brief, product: Product) -> str:
        from app.product_fields import product_cta, product_direction, product_message

        msg = product_message(brief, product)
        cta = product_cta(brief, product)
        direction = product_direction(brief, product)
        prompt = (
            f"Campaign: {brief.campaign_name}\n"
            f"Brand: {brief.brand}\n"
            f"Audience: {brief.audience}\n"
            f"Message: {msg}\n"
            f"CTA: {cta}\n"
            f"Creative direction: {direction}\n"
            f"Product: {product.name} ({product.category})\n"
            "Return a short polished social ad line (max 12 words) that keeps "
            "THIS product's message intent (not another product in the campaign)."
        )
        response = self.client.chat.completions.create(
            model="gpt-4.1",
            temperature=0.4,
            messages=[
                {
                    "role": "system",
                    "content": "You write concise social ad copy. Return only the line, no quotes.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return (response.choices[0].message.content or msg).strip()

    def suggest_campaign_copy(self, brief: Brief, product: Product) -> dict[str, str]:
        """Draft headline, CTA, supporting, optional legal from the brief."""
        from app.product_fields import product_cta, product_direction, product_message

        msg = product_message(brief, product)
        cta = product_cta(brief, product)
        direction = product_direction(brief, product)
        prompt = (
            f"Campaign: {brief.campaign_name}\n"
            f"Brand: {brief.brand}\n"
            f"Audience: {brief.audience}\n"
            f"Creative direction: {direction}\n"
            f"Tone: {brief.brand_notes.tone}\n"
            f"Current message: {msg}\n"
            f"Current CTA: {cta}\n"
            f"Product: {product.name} ({product.category})\n"
            "Return ONLY JSON: "
            '{"message":"headline max 10 words","cta":"short CTA",'
            '"supporting_copy":"optional one line or empty",'
            '"legal_disclaimer":"optional short legal or empty"}'
        )
        response = self.client.chat.completions.create(
            model="gpt-4.1",
            temperature=0.5,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write social ad copy. Preserve campaign concept/metaphor. "
                        "Return valid JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        raw = (response.choices[0].message.content or "{}").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"message": msg, "cta": cta}
        return {
            "message": str(data.get("message") or msg or ""),
            "cta": str(data.get("cta") or cta or ""),
            "supporting_copy": str(data.get("supporting_copy") or ""),
            "legal_disclaimer": str(data.get("legal_disclaimer") or ""),
        }

    def localize(
        self,
        text: str,
        locale: str,
        *,
        brief: Brief | None = None,
        field: str = "message",
    ) -> str:
        """Adapt copy for a locale. Preserves campaign concept; not literal translate."""
        text = (text or "").strip()
        if not text:
            return ""
        if _is_english_locale(locale):
            return text

        context_bits = []
        if brief is not None:
            products = ", ".join(p.name for p in brief.products) or "(none)"
            context_bits = [
                f"Campaign: {brief.campaign_name}",
                f"Brand: {brief.brand}",
                f"Products: {products}",
                f"Approved English message: {brief.message}",
                f"Approved English CTA: {brief.cta}",
                f"Creative direction: {brief.creative_direction}",
                f"Tone: {brief.brand_notes.tone}",
                f"Field being adapted: {field}",
            ]
        context = "\n".join(context_bits)

        response = self.client.chat.completions.create(
            model="gpt-4.1",
            temperature=0.35,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You adapt short social-ad copy into this language/locale: {locale}.\n"
                        "The target may be any natural language or constructed language "
                        "(e.g. Klingon, Quenya, Sindarin). Write fluently IN that language.\n"
                        "CRITICAL: Do NOT return English. If the locale is Bengali, Hindi, "
                        "Arabic, Chinese, etc., use that language's native script. "
                        "For Elvish (Quenya/Sindarin) or Klingon, write in that language "
                        "(Latin transliteration is OK for constructed languages).\n"
                        "Preserve the campaign CONCEPT and product naming idea "
                        "(metaphor, freeze/capture-time ideas, drop names, etc.).\n"
                        "Do NOT literal-translate English word order if that drops "
                        "the concept. Prefer natural local ad language that a native "
                        "speaker (or fluent speaker of that constructed language) would run.\n"
                        "Keep it punchy and overlay-short. Return only the line, no quotes."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"{context}\n\nSource line to adapt:\n{text}"
                        if context
                        else text
                    ),
                },
            ],
        )
        return (response.choices[0].message.content or text).strip()

    def localize_pair(
        self,
        message: str,
        cta: str,
        locale: str,
        brief: Brief,
        *,
        product: Product | None = None,
        strict: bool = False,
    ) -> tuple[str, str]:
        """Adapt message+CTA together so both locales keep the same concept."""
        if _is_english_locale(locale):
            return (message or "").strip(), (cta or "").strip()

        from app.product_fields import product_direction

        focus_name = product.name if product is not None else ""
        focus_direction = (
            product_direction(brief, product) if product is not None else brief.creative_direction
        )
        payload = {
            "locale": locale,
            "campaign_name": brief.campaign_name,
            "brand": brief.brand,
            "product": focus_name or None,
            "creative_direction": focus_direction,
            "tone": brief.brand_notes.tone,
            "source_message": message,
            "source_cta": cta,
        }
        strict_extra = ""
        if strict:
            strict_extra = (
                "\nYour previous attempt was still English. This is unacceptable. "
                f"Write message and cta ONLY in {locale}. "
                "If that language has a native script, use it (e.g. Bengali → বাংলা)."
            )
        product_rule = (
            f"This copy is ONLY for product '{focus_name}'. "
            "Do not mention or borrow lines/names from other products in the campaign.\n"
            if focus_name
            else ""
        )
        response = self.client.chat.completions.create(
            model="gpt-4.1",
            temperature=0.35,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Adapt social-ad message and CTA into this language/locale: {locale}.\n"
                        "Write the output IN that language. Do NOT leave it in English.\n"
                        "Script rules:\n"
                        "- Bengali, Hindi, Tamil, Arabic, Chinese, Japanese, Korean, etc.: "
                        "use the native script for that language.\n"
                        "- Elvish (Quenya / Sindarin), Klingon: write in that constructed "
                        "language (Latin transliteration OK).\n"
                        f"{product_rule}"
                        "Preserve the SOURCE LINE's concept and metaphor only "
                        "(adapt what is in source_message / source_cta). "
                        "Do not invent sibling-product names or campaign metaphors "
                        "that are not in the source lines.\n"
                        "Natural market ad copy, not awkward literal translation.\n"
                        "Return ONLY JSON: {\"message\": \"...\", \"cta\": \"...\"}"
                        + strict_extra
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        try:
            data = json.loads(content)
            msg = str(data.get("message") or message).strip()
            cta_out = str(data.get("cta") or cta).strip()
            return msg, cta_out
        except json.JSONDecodeError:
            return (
                self.localize(message, locale, brief=brief, field="message"),
                self.localize(cta, locale, brief=brief, field="cta") if cta else "",
            )


def build_image_prompt(brief: Brief, product: Product) -> str:
    from app.product_fields import (
        product_background_paths,
        product_direction,
        product_style_paths,
    )

    tags = ", ".join(brief.visual_style_tags) if brief.visual_style_tags else "cinematic advertising"
    colors = ", ".join(brief.brand_notes.colors) if brief.brand_notes.colors else ""
    direction = product_direction(brief, product)
    style_n = len(product_style_paths(brief, product))
    bg_n = len(product_background_paths(brief, product))
    parts = [
        f"Professional social advertising still for {brief.brand or 'the brand'}.",
        f"Campaign: {brief.campaign_name}.",
        f"Product: {product.name} ({product.category or 'product'}).",
        f"Role: {product.product_role.value}. Mode: {product.product_mode.value}.",
        f"Audience: {brief.audience}." if brief.audience else "",
        f"Creative direction: {direction}." if direction else "",
        f"Visual style: {tags}.",
        f"Tone: {brief.brand_notes.tone}." if brief.brand_notes.tone else "",
        f"Brand colors: {colors}." if colors else "",
        f"Asset hint: {product.asset_hint}." if product.asset_hint else "",
        f"Notes: {product.notes}." if product.notes else "",
        (
            f"Likeness references attached ({len(brief.likeness_reference_paths)})."
            if brief.likeness_reference_paths
            else ""
        ),
        f"Style references attached ({style_n})." if style_n else "",
        f"Background references attached ({bg_n})." if bg_n else "",
        "Cinematic lighting, art-directed, high production value. Not a flat packshot unless direction says so.",
        "Leave clean space in the lower third for text overlay. Avoid baking large headline text into the image.",
    ]
    return " ".join(p for p in parts if p)
