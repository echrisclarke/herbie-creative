from __future__ import annotations

import asyncio
import logging

from app.config import PROJECT_ROOT, image_quality_override
from app.fastapi_intake import load_campaign_brief
from app.pipeline import run_campaign
from app.schemas import GenerateRequest
from app.sse import bus
from app.tenant import tenant_context

logger = logging.getLogger(__name__)


def run_generate_job(
    campaign_id: str,
    body: GenerateRequest,
    loop: asyncio.AbstractEventLoop,
    *,
    user_id: str | None = None,
    user_email: str | None = None,
    api_keys: dict[str, str] | None = None,
) -> None:
    with tenant_context(user_id=user_id, email=user_email, api_keys=api_keys):
        try:
            brief = load_campaign_brief(campaign_id)

            def on_event(event: str, data: dict) -> None:
                bus.publish_threadsafe(loop, campaign_id, event, data)

            # Christian: UI Generate is stills-only. Motion is Results → POST /motion.
            # body.motion is deprecated on this endpoint (accepted, ignored on purpose).
            if body.outputs:
                brief.outputs = body.outputs
            if body.framing:
                brief.framing = body.framing
            with image_quality_override(body.image_quality):
                run_campaign(
                    brief,
                    campaign_slug=campaign_id,
                    project_root=PROJECT_ROOT,
                    # Hardcoded: UI animates on Results. CLI still has --with-motion.
                    with_motion=False,
                    creatives_only=body.creatives_only,
                    outputs_override=body.outputs,
                    framing_override=body.framing,
                    source_image_paths=body.source_paths or None,
                    on_event=on_event,
                )
        except Exception as exc:
            logger.exception("Generate job failed: %s", exc)
            bus.publish_threadsafe(
                loop, campaign_id, "run.failed", {"error": str(exc)}
            )
