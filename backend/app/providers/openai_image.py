from __future__ import annotations

import base64
import logging
import time

from openai import OpenAI

from app.config import (
    get_openai_api_key,
    openai_image_api,
    openai_image_model,
    openai_image_output_compression,
    openai_image_output_format,
    openai_image_quality,
)
from app.providers.openai_editor import api_size_for_ratio
from app.providers.openai_responses_image import generate_via_responses

logger = logging.getLogger(__name__)


class OpenAIImageGenerator:
    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or get_openai_api_key()
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required")
        self.client = OpenAI(api_key=key)

    def generate(self, prompt: str, size: str = "1024x1024", *, ratio: str | None = None) -> bytes:
        api_size = api_size_for_ratio(ratio) if ratio else size
        mode = openai_image_api()
        last_error: Exception | None = None

        if mode in {"auto", "responses"}:
            try:
                out = generate_via_responses(
                    prompt, size=api_size, client=self.client
                )
                logger.info(
                    "Image generate via Responses (%s / %s / %s)",
                    openai_image_model(),
                    openai_image_quality(),
                    openai_image_output_format(),
                )
                return out
            except Exception as exc:
                last_error = exc
                if mode == "responses":
                    raise RuntimeError(f"OpenAI Responses image generation failed: {exc}") from exc
                logger.warning(
                    "Responses image generate failed, trying Images API: %s", exc
                )

        for attempt in range(2):
            try:
                gen_model = openai_image_model()
                if gen_model.lower() == "auto":
                    gen_model = "gpt-image-2"
                out_fmt = openai_image_output_format()
                gen_kwargs: dict = {
                    "model": gen_model,
                    "prompt": prompt,
                    "size": api_size,
                    "quality": openai_image_quality(),
                    "output_format": out_fmt,
                }
                if out_fmt in {"jpeg", "webp"}:
                    gen_kwargs["output_compression"] = openai_image_output_compression()
                result = self.client.images.generate(**gen_kwargs)
                item = result.data[0]
                b64 = getattr(item, "b64_json", None)
                if b64:
                    logger.info(
                        "Image generate via Images API (%s / %s / %s)",
                        openai_image_model(),
                        openai_image_quality(),
                        out_fmt,
                    )
                    return base64.b64decode(b64)
                url = getattr(item, "url", None)
                if url:
                    import httpx

                    resp = httpx.get(url, timeout=120)
                    resp.raise_for_status()
                    return resp.content
                raise RuntimeError("OpenAI image response missing bytes")
            except Exception as exc:
                last_error = exc
                logger.warning("Image generate attempt %s failed: %s", attempt + 1, exc)
                if attempt == 0:
                    time.sleep(1.5)
        raise RuntimeError(f"OpenAI image generation failed: {last_error}")
