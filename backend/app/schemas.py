from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ProductMode(str, Enum):
    USE_PROVIDED = "use-provided"
    GENERATE_CONCEPT = "generate-concept"


class ProductRole(str, Enum):
    PRODUCT_HERO = "product_hero"
    FEATURE = "feature"
    LIFESTYLE_ANGLE = "lifestyle_angle"
    SERVICE_ANGLE = "service_angle"
    DROP_ANNOUNCEMENT = "drop_announcement"


class Product(BaseModel):
    name: str
    category: str = ""
    product_mode: ProductMode = ProductMode.USE_PROVIDED
    product_role: ProductRole = ProductRole.PRODUCT_HERO
    asset_hint: str = ""
    input_asset_path: str | None = None
    # Extra reference images for multi-image compositing (e.g. card backs).
    # First image is always input_asset_path (hero); these follow in order.
    input_asset_paths: list[str] = Field(default_factory=list)
    landing_url: str | None = None
    notes: str = ""
    # Optional per-product overrides. Empty = fall back to campaign brief fields.
    # Lets multi-product campaigns use different headlines, CTAs, and scenes.
    message: str = ""
    cta: str = ""
    supporting_copy: str = ""
    creative_direction: str = ""
    style_reference_paths: list[str] = Field(default_factory=list)
    background_reference_paths: list[str] = Field(default_factory=list)


class BrandNotes(BaseModel):
    tone: str = ""
    colors: list[str] = Field(default_factory=list)
    font_names: list[str] = Field(default_factory=list)
    font_alternates: list[str] = Field(default_factory=list)
    logo_required: bool = False
    logo_path: str | None = None
    # All uploaded logo candidates; logo_path is the one used on finals.
    logo_paths: list[str] = Field(default_factory=list)
    # When no logo file: optional description used to generate a mark at Finalize.
    logo_description: str | None = None
    logo_placement: Literal["top-left", "top-right", "bottom-left", "bottom-right"] = (
        "top-left"
    )
    # Caption/headline+CTA band. "none" skips campaign text overlays (logo can remain).
    text_placement: Literal[
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
    ] = "bottom-center"
    # Legal footer only (always bottom of frame). Horizontal align only.
    legal_placement: Literal["left", "center", "right"] = "left"
    # Hex for Pillow logo tint, or "original" to paste as-is. Null = white if logo is flat black.
    logo_color: str | None = None
    # 0.0–1.0 drop shadow under the logo. Null = off.
    logo_shadow_opacity: float | None = None
    # 0.0–1.0 overall logo alpha. Null = fully opaque.
    logo_opacity: float | None = None
    # Size multiplier vs default logo height (~0.09 of canvas). Null = 1.0.
    logo_scale: float | None = None
    # Hex for message/headline overlay. Null = white.
    text_color: str | None = None
    # Soft gradient behind type. Prefer leaving unset so Finalize vision suggest decides.
    # User/Finalize can override after looking at creatives.
    text_scrim: bool | None = None
    # 0.0–1.0 strength of scrim when on. Null = composer default (~0.65).
    text_scrim_opacity: float | None = None
    # 0.0–1.0 strength of type drop shadow. Null = composer default (~0.6).
    text_shadow_opacity: float | None = None
    forbidden_words: list[str] = Field(default_factory=list)
    font_file_path: str | None = None


class SlotRenderChoices(BaseModel):
    """Per-slot render for hybrid mode. Legal is never AI-integrated."""

    logo: Literal["pillow", "skip"] = "pillow"
    headline: Literal["pillow", "ai", "skip"] = "pillow"
    supporting: Literal["pillow", "ai", "skip"] = "skip"
    cta: Literal["pillow", "skip"] = "pillow"
    legal: Literal["pillow", "skip"] = "skip"


class Brief(BaseModel):
    campaign_name: str
    brand: str = ""
    market: str = "US"
    audience: str = ""
    message: str = ""
    cta: str = ""
    supporting_copy: str = ""
    legal_disclaimer: str = ""
    creative_direction: str = ""
    visual_style_tags: list[str] = Field(default_factory=list)
    motion_notes: str = ""
    products: list[Product] = Field(default_factory=list)
    brand_notes: BrandNotes = Field(default_factory=BrandNotes)
    # Soft cap applied in pipeline (MAX_LOCALES). Optional in Review; set in Finalize.
    localize_to: list[str] = Field(default_factory=list)
    # Optional Review/Finalize cache of per-language overlay copy (message/cta/supporting).
    locales_copy: dict[str, LocaleCopy] = Field(default_factory=dict)
    # One, some, or all of 1:1 / 9:16 / 16:9. Order is generation chain order.
    outputs: list[str] = Field(default_factory=lambda: ["1:1", "9:16", "16:9"])
    # Framing for the first selected ratio: close-up, zoomed-out, or both presets.
    # Brief language (macro, ultra close-up, etc.) can further steer via asset_hint.
    framing: Literal["close-up", "zoomed", "both"] = "both"
    # later = decide in Finalize; none = no campaign text; composer/ai/hybrid as usual.
    # "pillow" kept as alias for composer.
    text_render_mode: Literal["composer", "ai", "hybrid", "pillow", "none", "later"] = "later"
    slot_render: SlotRenderChoices = Field(default_factory=SlotRenderChoices)
    # Campaign-level reference images (role-tagged uploads). Optional.
    style_reference_paths: list[str] = Field(default_factory=list)
    likeness_reference_paths: list[str] = Field(default_factory=list)
    background_reference_paths: list[str] = Field(default_factory=list)


MAX_LOCALES = 5


class AssetStatus(BaseModel):
    product_name: str
    product_mode: ProductMode
    has_image: bool
    path: str | None = None
    paths: list[str] = Field(default_factory=list)
    missing_message: str | None = None


class AssetManifest(BaseModel):
    products: list[AssetStatus] = Field(default_factory=list)
    logo_path: str | None = None
    ready: bool = False
    blockers: list[str] = Field(default_factory=list)


class MotionOptions(BaseModel):
    # Christian: deprecated wire shape on Generate. Kept so older clients do not
    # break validation. UI ignores this; motion is Results-only (POST /motion).
    enabled: bool = False
    duration_seconds: int = 6
    # Deprecated with enabled: nothing currently filters motion by ratio.
    ratios: list[str] = Field(default_factory=list)


class MotionRequest(BaseModel):
    """Body for POST /campaigns/{id}/motion (Results / Library animate)."""

    creative_path: str
    prompt: str | None = None
    # Extra direction appended after prompt (likeness / refs notes from Motion step).
    prompt_extra: str | None = None
    duration_seconds: int = 6
    resolution: str | None = None
    output_name: str = "creative.mp4"


class GenerateRequest(BaseModel):
    # Christian: deprecated. Accepted for back-compat; fastapi_jobs never reads it.
    motion: MotionOptions = Field(default_factory=MotionOptions)
    # medium is the practical default for demos (cost vs quality).
    image_quality: Literal["low", "medium", "high"] = "medium"
    outputs: list[str] | None = None
    framing: Literal["close-up", "zoomed", "both"] | None = None
    # Schema default True matches the UI. pipeline.run_campaign defaults False for CLI
    # full runs that compose finals in one pass. Easy to mix up when reading both files.
    creatives_only: bool = True
    # Existing stills to lock look when "Generate more" reframes other ratios.
    source_paths: list[str] = Field(default_factory=list)


class LocaleCopy(BaseModel):
    message: str = ""
    cta: str = ""
    supporting: str = ""


class FinalizeChoices(BaseModel):
    """User choices for Phase 2 Finalize (after creatives exist)."""

    locales: list[str] | None = None
    locales_copy: dict[str, LocaleCopy] | None = None
    logo_color: str | None = None
    logo_shadow_opacity: float | None = None
    logo_opacity: float | None = None
    logo_scale: float | None = None
    text_color: str | None = None
    cta_accent: str | None = None
    logo_placement: Literal["top-left", "top-right", "bottom-left", "bottom-right"] | None = (
        None
    )
    text_placement: (
        Literal[
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
            "auto",
        ]
        | None
    ) = None
    # Optional per-aspect-ratio caption placement (keys like "1:1", "9:16", "16:9").
    text_placement_by_ratio: dict[str, str] | None = None
    # Legal footer horizontal align (always bottom of frame).
    legal_placement: Literal["left", "center", "right"] | None = None
    font_names: list[str] | None = None
    text_scrim: bool | None = None
    text_scrim_opacity: float | None = None
    text_shadow_opacity: float | None = None
    use_logo: bool = True
    # When use_logo and no uploaded file: generate a mark from this description.
    logo_description: str | None = None
    # Per-slot render: composer = Pillow, ai = scene-integrated type, skip = omit.
    caption_mode: Literal["composer", "ai", "skip"] = "composer"
    subcaption_mode: Literal["composer", "ai", "skip"] = "skip"
    # Exact or seed copy (blank + suggest = AI writes; blank + ai mode = invent from brief).
    caption_text: str | None = None
    caption_style: str | None = None
    caption_fit: str | None = None
    subcaption_text: str | None = None
    subcaption_style: str | None = None
    subcaption_fit: str | None = None
    # Let vision suggest pick text_placement when true / when placement is "auto".
    ai_decide_placement: bool = False
    text_render_mode: Literal["composer", "ai", "hybrid", "pillow", "none", "later"] | None = (
        None
    )
    skip_suggest: bool = False
    run_suggest: bool = False
    # English source copy keyed by product name. When set, that product's finals
    # use this instead of campaign caption / brief.message (other products unchanged).
    product_copy: dict[str, LocaleCopy] | None = None


class LocalizeCopyRequest(BaseModel):
    """Re-adapt Finalize locale copy from a source-language edit."""

    message: str = ""
    cta: str = ""
    # Clients often send null when sub-caption is empty; accept and coerce.
    supporting: str | None = ""
    locales: list[str] = Field(default_factory=list)
    locked_locales: list[str] = Field(default_factory=list)
    existing: dict[str, LocaleCopy] | None = None

    @property
    def supporting_text(self) -> str:
        return self.supporting or ""


class CreativeResult(BaseModel):
    product: str
    ratio: str
    path: str
    locale: str = "en-US"
    creative_path: str | None = None  # no-text hero / resized variation
    source: Literal["provided_image", "concept_generated"]
    image_provider: str
    text_provider: str = "openai"
    fallback_triggered: bool = False
    motion_path: str | None = None
    timings_ms: dict[str, int] = Field(default_factory=dict)
    compliance: dict[str, bool] = Field(default_factory=dict)
    message: str = ""
    cta: str = ""


class Report(BaseModel):
    campaign_id: str
    started_at: str
    finished_at: str
    storage_backend: str = "local"
    creatives: list[CreativeResult] = Field(default_factory=list)
    totals: dict = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)


RATIO_SIZES: dict[str, tuple[int, int]] = {
    "1:1": (1080, 1080),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

RATIO_FOLDER: dict[str, str] = {
    "1:1": "1x1",
    "9:16": "9x16",
    "16:9": "16x9",
}
