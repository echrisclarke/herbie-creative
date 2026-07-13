from __future__ import annotations

import base64
import logging
from io import BytesIO

from openai import OpenAI
from PIL import Image

from app.config import (
    get_openai_api_key,
    openai_image_api,
    openai_image_input_fidelity,
    openai_image_model,
    openai_image_output_compression,
    openai_image_output_format,
    openai_image_quality,
    openai_image_supports_input_fidelity,
)
from app.providers.openai_responses_image import edit_via_responses
from app.providers.pillow_editor import crop_pad_to_size

logger = logging.getLogger(__name__)

# GPT image edits accept multiple images; keep a practical cap for ads.
MAX_REFERENCE_IMAGES = 8

# Standard GPT image sizes (not arbitrary 1080 canvases)
API_SIZE_BY_RATIO: dict[str, str] = {
    "1:1": "1024x1024",
    "9:16": "1024x1536",
    "16:9": "1536x1024",
}

# Keep source detail; chat uploads are not aggressively downsampled to 1536.
MAX_INPUT_SIDE = 4096


def api_size_for_ratio(ratio: str) -> str:
    return API_SIZE_BY_RATIO.get(ratio, "1024x1024")


def parse_api_size(api_size: str) -> tuple[int, int]:
    w, h = api_size.lower().split("x")
    return int(w), int(h)


class OpenAIImageEditor:
    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or get_openai_api_key()
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required")
        self.client = OpenAI(api_key=key)

    def adapt(
        self,
        image_bytes: bytes,
        width: int,
        height: int,
        prompt: str | None = None,
        reference_images: list[bytes] | None = None,
        *,
        ratio: str | None = None,
        preserve_scene: bool = False,
        mask_bytes: bytes | None = None,
    ) -> tuple[bytes, bool]:
        """Return (png_bytes, fallback_triggered).

        Prefer Responses image_generation (ChatGPT path), then Images /edits.
        """
        refs = list(reference_images or [])
        api_size = api_size_for_ratio(ratio) if ratio else "1024x1024"
        if ratio is None:
            if width == height:
                api_size = "1024x1024"
            elif height > width:
                api_size = "1024x1536"
            else:
                api_size = "1536x1024"
        api_w, api_h = parse_api_size(api_size)

        base_prompt = prompt or (
            "Transform this product photo into a polished social advertising still. "
            "Keep the product recognizable and hero-focused. Place it in a cinematic, "
            "art-directed environment that fits a premium campaign. Leave a clean lower "
            "third for text overlay. Do not bake large headlines into the image."
        )
        if preserve_scene and not mask_bytes:
            base_prompt = (
                f"{base_prompt} Keep the same subject, materials, and logos."
            )
        if mask_bytes:
            base_prompt = (
                f"{base_prompt} Fill only masked/transparent margins."
            )
        if refs and not mask_bytes:
            base_prompt = (
                f"{base_prompt} Extra images are product refs for materials and logos."
            )

        mode = openai_image_api()
        hero_png = self._normalize_png(image_bytes)
        ref_pngs = [self._normalize_png(r) for r in refs[: MAX_REFERENCE_IMAGES - 1]]
        mask_png = None
        if mask_bytes:
            hero_png = self._resize_png(image_bytes, api_w, api_h, keep_alpha=True)
            mask_png = self._resize_png(mask_bytes, api_w, api_h, keep_alpha=True)
            ref_pngs = []

        if mode in {"auto", "responses"}:
            try:
                adapted = edit_via_responses(
                    base_prompt,
                    [hero_png, *ref_pngs],
                    size=api_size,
                    mask_bytes=mask_png,
                    client=self.client,
                )
                logger.info(
                    "Image edit via Responses (%s / %s / %s)",
                    openai_image_model(),
                    openai_image_quality(),
                    "png" if mask_png else openai_image_output_format(),
                )
                return crop_pad_to_size(adapted, width, height), False
            except Exception as exc:
                if mode == "responses":
                    logger.warning("Responses image edit failed: %s", exc)
                    return crop_pad_to_size(image_bytes, width, height), True
                logger.warning(
                    "Responses image edit failed, trying Images API: %s", exc
                )

        if mode in {"auto", "images"}:
            try:
                adapted = self._edit_via_images_api(
                    base_prompt,
                    hero_png,
                    ref_pngs,
                    api_size=api_size,
                    mask_png=mask_png,
                )
                logger.info(
                    "Image edit via Images API (%s / %s)",
                    openai_image_model(),
                    openai_image_quality(),
                )
                return crop_pad_to_size(adapted, width, height), False
            except Exception as exc:
                logger.warning("OpenAI image edit failed, using Pillow crop/pad: %s", exc)

        return crop_pad_to_size(image_bytes, width, height), True

    def _edit_via_images_api(
        self,
        prompt: str,
        hero_png: bytes,
        ref_pngs: list[bytes],
        *,
        api_size: str,
        mask_png: bytes | None,
    ) -> bytes:
        model = openai_image_model()
        if model.lower() == "auto":
            model = "gpt-image-2"
        out_fmt = "png" if mask_png else openai_image_output_format()
        kwargs: dict = {
            "model": model,
            "prompt": prompt,
            "size": api_size,
            "quality": openai_image_quality(),
            "output_format": out_fmt,
        }
        if out_fmt in {"jpeg", "webp"}:
            kwargs["output_compression"] = openai_image_output_compression()
        if openai_image_supports_input_fidelity(model):
            kwargs["input_fidelity"] = openai_image_input_fidelity()

        if mask_png:
            kwargs["image"] = ("hero.png", hero_png, "image/png")
            kwargs["mask"] = ("mask.png", mask_png, "image/png")
        else:
            files = [("hero.png", hero_png, "image/png")]
            for i, ref in enumerate(ref_pngs):
                files.append((f"ref-{i + 1}.png", ref, "image/png"))
            kwargs["image"] = files if len(files) > 1 else files[0]

        result = self.client.images.edit(**kwargs)
        item = result.data[0]
        b64 = getattr(item, "b64_json", None)
        if not b64:
            raise RuntimeError("Images edit response missing b64_json")
        return base64.b64decode(b64)

    def _normalize_png(self, image_bytes: bytes) -> bytes:
        return self._resize_png(image_bytes, keep_alpha=False)

    def _resize_png(
        self,
        image_bytes: bytes,
        width: int | None = None,
        height: int | None = None,
        *,
        keep_alpha: bool = False,
    ) -> bytes:
        img = Image.open(BytesIO(image_bytes))
        img = img.convert("RGBA")
        if not keep_alpha:
            # Flatten translucent pads so they don't become black RGB
            if img.getextrema()[3][0] < 255:
                bg = Image.new("RGB", img.size, (245, 245, 245))
                bg.paste(img, mask=img.split()[-1])
                img = bg.convert("RGBA")
            else:
                img = img.convert("RGB").convert("RGBA")

        if width and height:
            img = img.resize((width, height), Image.Resampling.LANCZOS)
        elif max(img.size) > MAX_INPUT_SIDE:
            img.thumbnail((MAX_INPUT_SIDE, MAX_INPUT_SIDE), Image.Resampling.LANCZOS)

        out = BytesIO()
        if keep_alpha:
            img.save(out, format="PNG")
        else:
            img.convert("RGB").save(out, format="PNG")
        return out.getvalue()
