"""xAI Image-to-Video (Grok Imagine).

HTTP is the default so motion works on every machine we care about, including
Windows ARM where grpcio (pulled by xai-sdk) has no wheels. The SDK path is a
fallback when those packages actually install.
"""
from __future__ import annotations

import base64
import logging
import mimetypes
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

XAI_BASE = "https://api.x.ai/v1"
# Docs: https://docs.x.ai/developers/model-capabilities/video/image-to-video
DEFAULT_MODEL = "grok-imagine-video-1.5"
DEFAULT_RESOLUTION = "720p"
POLL_INTERVAL_SEC = 5.0
POLL_TIMEOUT_SEC = 600.0


def _data_uri_for_image(image_path: Path) -> str:
    raw = image_path.read_bytes()
    mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
    if mime not in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
        mime = "image/png"
    if mime == "image/jpg":
        mime = "image/jpeg"
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _download_url(url: str, output_path: Path) -> Path | None:
    with httpx.Client(timeout=httpx.Timeout(60.0, read=180.0)) as client:
        dl = client.get(url)
        if dl.status_code >= 400 or not dl.content:
            logger.warning("Motion download failed (%s)", dl.status_code)
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(dl.content)
        logger.info("Motion saved %s (%s bytes)", output_path, len(dl.content))
        return output_path


def _generate_via_sdk(
    *,
    api_key: str,
    prompt: str,
    image_url: str,
    model_name: str,
    duration: int,
    resolution: str,
    aspect_ratio: str | None,
    output_path: Path,
) -> Path | None:
    """Optional path when xai-sdk + grpcio are installed (not available on Windows ARM)."""
    try:
        import xai_sdk
    except Exception:
        return None

    try:
        client = xai_sdk.Client(api_key=api_key)
        kwargs: dict = {
            "prompt": prompt,
            "model": model_name,
            "image_url": image_url,
            "duration": duration,
            "resolution": resolution if resolution in {"480p", "720p"} else "720p",
        }
        if aspect_ratio:
            kwargs["aspect_ratio"] = aspect_ratio
        response = client.video.generate(**kwargs)
        url = getattr(response, "url", None)
        if not url:
            logger.warning("xai-sdk motion returned no url")
            return None
        logger.info("Motion via xai-sdk model=%s duration=%ss", model_name, duration)
        return _download_url(str(url), output_path)
    except Exception as exc:
        logger.warning("xai-sdk motion failed, trying HTTP: %s", exc)
        return None


def _generate_via_http(
    *,
    api_key: str,
    prompt: str,
    image_url: str,
    model_name: str,
    duration: int,
    resolution: str,
    aspect_ratio: str | None,
    output_path: Path,
) -> tuple[Path | None, str | None]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": model_name,
        "prompt": prompt,
        "image": {"url": image_url},
        "duration": duration,
        "resolution": resolution,
    }
    if aspect_ratio:
        payload["aspect_ratio"] = aspect_ratio

    with httpx.Client(timeout=httpx.Timeout(60.0, read=120.0)) as client:
        start = client.post(
            f"{XAI_BASE}/videos/generations",
            headers=headers,
            json=payload,
        )
        if start.status_code >= 400:
            detail = (start.text or "")[:400]
            logger.warning("Motion start failed (%s): %s", start.status_code, detail)
            return None, f"xAI start failed ({start.status_code}): {detail or 'no details'}"
        request_id = (start.json() or {}).get("request_id")
        if not request_id:
            logger.warning("Motion start missing request_id: %s", start.text[:500])
            return None, "xAI motion start missing request_id"

        logger.info(
            "Motion started (HTTP) request_id=%s model=%s duration=%ss",
            request_id,
            model_name,
            duration,
        )
        deadline = time.monotonic() + POLL_TIMEOUT_SEC
        video_url: str | None = None
        while time.monotonic() < deadline:
            poll = client.get(
                f"{XAI_BASE}/videos/{request_id}",
                headers={"Authorization": headers["Authorization"]},
            )
            if poll.status_code >= 400 and poll.status_code != 202:
                detail = (poll.text or "")[:400]
                logger.warning("Motion poll failed (%s): %s", poll.status_code, detail)
                return None, f"xAI poll failed ({poll.status_code}): {detail or 'no details'}"
            if poll.status_code == 202:
                time.sleep(POLL_INTERVAL_SEC)
                continue
            data = poll.json() or {}
            status = str(data.get("status") or "").lower()
            if status == "done":
                video = data.get("video") or {}
                video_url = video.get("url")
                break
            if status in {"failed", "expired"}:
                logger.warning("Motion %s: %s", status, str(data)[:500])
                return None, f"xAI motion {status}: {str(data)[:300]}"
            time.sleep(POLL_INTERVAL_SEC)
        else:
            logger.warning("Motion timed out waiting for request_id=%s", request_id)
            return None, "xAI motion timed out (waited 10 minutes)"

        if not video_url:
            logger.warning("Motion done but no video URL")
            return None, "xAI motion finished without a video URL"
        saved = _download_url(video_url, output_path)
        if not saved:
            return None, "Failed to download motion video from xAI"
        return saved, None


def generate_motion(
    image_path: Path,
    output_path: Path,
    prompt: str,
    duration_seconds: int = 6,
    api_key: str | None = None,
    *,
    model: str | None = None,
    resolution: str | None = None,
    aspect_ratio: str | None = None,
) -> Path | None:
    """Animate a finished still into an MP4. Returns output path or None on skip/fail."""
    path, _err = generate_motion_with_reason(
        image_path,
        output_path,
        prompt,
        duration_seconds,
        api_key,
        model=model,
        resolution=resolution,
        aspect_ratio=aspect_ratio,
    )
    return path


def generate_motion_with_reason(
    image_path: Path,
    output_path: Path,
    prompt: str,
    duration_seconds: int = 6,
    api_key: str | None = None,
    *,
    model: str | None = None,
    resolution: str | None = None,
    aspect_ratio: str | None = None,
) -> tuple[Path | None, str | None]:
    """Same as generate_motion, but returns a short reason when it fails.

    Use this from the Results API so the UI can show the real xAI error.
    Pipeline / CLI can keep calling generate_motion and just log.
    """
    if not api_key:
        logger.info("Motion skipped: no XAI_API_KEY")
        return None, "XAI_API_KEY is missing"
    if not image_path.exists():
        logger.warning("Motion skipped: image not found (%s)", image_path)
        return None, f"Image not found: {image_path.name}"

    duration = max(1, min(int(duration_seconds or 6), 15))
    model_name = (model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    res = (resolution or DEFAULT_RESOLUTION).strip() or DEFAULT_RESOLUTION
    text = (prompt or "").strip() or (
        "Subtle cinematic motion. Keep the product and composition. Soft camera drift."
    )
    image_url = _data_uri_for_image(image_path)

    try:
        # Prefer HTTP so we do not depend on grpcio / xai-sdk (missing on Windows ARM).
        via_http, http_err = _generate_via_http(
            api_key=api_key,
            prompt=text,
            image_url=image_url,
            model_name=model_name,
            duration=duration,
            resolution=res,
            aspect_ratio=aspect_ratio,
            output_path=output_path,
        )
        if via_http is not None:
            return via_http, None
        via_sdk = _generate_via_sdk(
            api_key=api_key,
            prompt=text,
            image_url=image_url,
            model_name=model_name,
            duration=duration,
            resolution=res,
            aspect_ratio=aspect_ratio,
            output_path=output_path,
        )
        if via_sdk is not None:
            return via_sdk, None
        return None, http_err or "Motion generation failed (HTTP and SDK)"
    except Exception as exc:
        logger.warning("Motion skipped due to error: %s", exc)
        return None, str(exc)
