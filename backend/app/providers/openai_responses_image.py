from __future__ import annotations

import base64
import logging
from typing import Any

from openai import OpenAI

from app.config import (
    get_openai_api_key,
    openai_image_input_detail,
    openai_image_input_fidelity,
    openai_image_model,
    openai_image_output_compression,
    openai_image_output_format,
    openai_image_quality,
    openai_image_supports_input_fidelity,
    openai_responses_model,
)

logger = logging.getLogger(__name__)


def _data_url(image_bytes: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"


def _image_tool(
    *,
    action: str | None,
    size: str,
    mask_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Build the image_generation tool.

    Matches the Images/Vision gift-basket pattern: type + quality/size, optional
    model pin. action=auto (or omitted) lets the model choose generate vs edit
    when references are in context; force edit only when a mask is present.
    """
    model = openai_image_model()
    # Masks need alpha; jpeg/webp cannot carry a transparent mask workflow.
    out_fmt = "png" if mask_bytes else openai_image_output_format()
    tool: dict[str, Any] = {
        "type": "image_generation",
        "quality": openai_image_quality(),
        "size": size,
        "output_format": out_fmt,
    }
    if out_fmt in {"jpeg", "webp"}:
        tool["output_compression"] = openai_image_output_compression()
    if action:
        tool["action"] = action
    # "auto" omits model so Responses uses its current GPT Image default.
    if model.lower() != "auto":
        tool["model"] = model
    # gpt-image-2 always runs high fidelity; param is rejected for that family.
    if (
        model.lower() != "auto"
        and openai_image_supports_input_fidelity(model)
        and (action in {None, "edit", "auto"} or mask_bytes)
    ):
        tool["input_fidelity"] = openai_image_input_fidelity()
    if mask_bytes:
        tool["input_image_mask"] = {"image_url": _data_url(mask_bytes)}
    return tool


def _extract_image_b64(response: Any) -> str:
    calls = [
        item
        for item in (getattr(response, "output", None) or [])
        if getattr(item, "type", None) == "image_generation_call"
    ]
    for item in calls:
        result = getattr(item, "result", None)
        if result:
            return result
        status = getattr(item, "status", None)
        raise RuntimeError(
            f"image_generation_call finished without result (status={status})"
        )
    text = getattr(response, "output_text", None) or ""
    raise RuntimeError(
        "Responses API returned no image_generation_call result"
        + (f": {text[:300]}" if text else "")
    )


def generate_via_responses(
    prompt: str,
    *,
    size: str = "1024x1024",
    client: OpenAI | None = None,
) -> bytes:
    api = client or OpenAI(api_key=get_openai_api_key())
    response = api.responses.create(
        model=openai_responses_model(),
        input=prompt,
        tools=[_image_tool(action="generate", size=size)],
        tool_choice={"type": "image_generation"},
    )
    return base64.b64decode(_extract_image_b64(response))


def edit_via_responses(
    prompt: str,
    images: list[bytes],
    *,
    size: str = "1024x1024",
    mask_bytes: bytes | None = None,
    client: OpenAI | None = None,
) -> bytes:
    """Reference / edit path matching the gift-basket Responses example.

    Content = prompt text + one or more input_image parts (data URLs).
    With a mask, force action=edit and attach input_image_mask.
    Without a mask, leave action=auto so the tool can generate from refs.
    """
    if not images:
        raise ValueError("edit_via_responses requires at least one image")
    api = client or OpenAI(api_key=get_openai_api_key())
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    detail = openai_image_input_detail()
    for img in images:
        part: dict[str, Any] = {
            "type": "input_image",
            "image_url": _data_url(img),
        }
        # Gift-basket sample often omits detail; we set it so gpt-5.6 keeps pixels.
        if detail:
            part["detail"] = detail
        content.append(part)

    action = "edit" if mask_bytes else "auto"
    response = api.responses.create(
        model=openai_responses_model(),
        input=[{"role": "user", "content": content}],
        tools=[_image_tool(action=action, size=size, mask_bytes=mask_bytes)],
        tool_choice={"type": "image_generation"},
    )
    return base64.b64decode(_extract_image_b64(response))
