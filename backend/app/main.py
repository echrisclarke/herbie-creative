from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import (
    PROJECT_ROOT,
    campaigns_base,
    get_google_fonts_api_key,
    get_openai_api_key,
    get_xai_api_key,
    hosted_mode,
    secret_key,
)
from app.root_path import RootPathMiddleware, root_path
from app.fastapi_fonts import list_google_fonts
from app.fastapi_intake import (
    approve_campaign,
    create_campaign,
    parse_campaign,
    save_campaign_brief,
)
from app.fastapi_jobs import run_generate_job
from app.gallery import list_gallery
from app.campaign_browser import (
    delete_campaign,
    delete_creative_files,
    delete_if_ephemeral,
    get_campaign_report,
    list_past_campaigns,
    open_past_campaign,
    reveal_campaign_folder,
    save_draft,
)
from app.schemas import Brief, FinalizeChoices, GenerateRequest, LocalizeCopyRequest, MotionRequest
from app.sse import bus
from app.storage.paths import campaign_dir
from app.tenant import current_api_keys, current_user_email, current_user_id, reset_tenant, set_tenant
from app.user_secrets import settings_snapshot, update_keys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI(title="Herbie Creative Campaign Pipeline", version="0.1.0")

_ROOT_PATH = root_path()

outputs_root = campaigns_base()
outputs_root.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_root)), name="outputs")

# Seed brand/product files (logo.png, refs) live under sample-assets/, not campaigns/.
# Finalize preview / LogoPicker need these over HTTP; Apply already resolves via PROJECT_ROOT.
_sample_assets = PROJECT_ROOT / "sample-assets"
if _sample_assets.is_dir():
    app.mount(
        "/sample-assets",
        StaticFiles(directory=str(_sample_assets)),
        name="sample-assets",
    )

_PUBLIC_PREFIXES = (
    "/assets/",
    "/brand/",
    "/sample-assets/",
    "/examples/",
    "/docs",
    "/openapi.json",
    "/redoc",
)


def _app_path(path: str) -> str:
    """Normalize request path after /pipeline prefix (middleware may see either form)."""
    prefix = _ROOT_PATH
    if prefix and (path == prefix or path.startswith(prefix + "/")):
        stripped = path[len(prefix) :] or "/"
        return stripped
    return path or "/"


def _requires_auth(path: str) -> bool:
    path = _app_path(path)
    if path in {
        "/health",
        "/auth/login",
        "/auth/signup",
        "/auth/me",
        "/favicon.ico",
        "/public-gallery",
    }:
        return False
    if path.startswith(_PUBLIC_PREFIXES):
        return False
    protected_prefixes = (
        "/settings/",
        "/gallery",
        "/campaigns",
        "/creatives",
        "/samples",
        "/tools/",
        "/fonts/",
        "/events",
        "/outputs/",
        "/auth/logout",
        "/auth/users",
    )
    if path.startswith(protected_prefixes) or path in {
        "/gallery",
        "/samples",
        "/auth/logout",
    }:
        return True
    return False


def _job_tenant_kwargs() -> dict:
    return {
        "user_id": current_user_id(),
        "user_email": current_user_email(),
        "api_keys": current_api_keys(),
    }


class TenantAuthMiddleware(BaseHTTPMiddleware):
    """Signed-in accounts only for pipeline, library, and settings."""

    async def dispatch(self, request: Request, call_next):
        path = _app_path(request.url.path)
        if not hosted_mode() or not _requires_auth(path):
            return await call_next(request)

        from app.auth_store import get_user_by_id, init_db, load_user_keys
        from app.trial import trial_status

        init_db()
        uid = request.session.get("user_id")
        if uid:
            user = get_user_by_id(str(uid))
            if not user:
                request.session.clear()
                return JSONResponse({"detail": "Sign in required"}, status_code=401)
            keys = load_user_keys(user.id)
            tokens = set_tenant(user_id=user.id, email=user.email, api_keys=keys)
            try:
                request.state.trial = trial_status(user.id)
                return await call_next(request)
            finally:
                reset_tenant(tokens)

        return JSONResponse(
            {
                "detail": "Sign up to continue. Free trial generates save to your account.",
                "requires_signup": True,
            },
            status_code=401,
        )


# Innermost → outermost: Tenant needs Session; RootPath strips /pipeline first.
app.add_middleware(TenantAuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=secret_key(),
    session_cookie="herbie_session",
    same_site="lax",
    https_only=hosted_mode(),
    max_age=60 * 60 * 24 * 14,
    path=_ROOT_PATH or "/",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if _ROOT_PATH:
    app.add_middleware(RootPathMiddleware, prefix=_ROOT_PATH)


@app.on_event("startup")
def _startup_hosted() -> None:
    if not hosted_mode():
        return
    from app.auth_store import bootstrap_admin_from_env, init_db

    init_db()
    created = bootstrap_admin_from_env()
    if created:
        logger.info("Bootstrap admin created: %s", created.get("email"))
    else:
        logger.info(
            "Hosted mode ready (set BOOTSTRAP_ADMIN_EMAIL/PASSWORD to create the first admin)"
        )


@app.get("/health")
def health(request: Request) -> dict:
    openai_ok = bool(get_openai_api_key())
    xai_ok = bool(get_xai_api_key())
    google_ok = bool(get_google_fonts_api_key())
    trial_info = None
    auth_required = False
    if hosted_mode():
        from app.auth_store import init_db, load_user_keys
        from app.trial import trial_status

        init_db()
        uid = request.session.get("user_id")
        if uid:
            keys = load_user_keys(str(uid))
            trial_info = trial_status(str(uid))
            openai_ok = bool(
                keys.get("openai_api_key") or trial_info.get("openai_ready")
            )
            xai_ok = bool(keys.get("xai_api_key"))
            google_ok = bool(keys.get("google_fonts_api_key")) or google_ok
            auth_required = False
        else:
            trial_info = trial_status(None)
            openai_ok = False
            xai_ok = False
            # Browse landing/library without forcing login; pipeline/generate asks to sign up.
            auth_required = False
    return {
        "ok": True,
        "service": "Herbie Creative Campaign Pipeline",
        "hosted": hosted_mode(),
        "desktop_tools": not hosted_mode(),
        "motion_available": xai_ok,
        "openai_configured": openai_ok,
        "google_fonts_catalog": google_ok,
        "trial": trial_info,
        "auth_required": auth_required,
    }


@app.post("/auth/login")
async def auth_login(request: Request, body: dict) -> dict:
    from app.auth_store import authenticate, init_db

    if not hosted_mode():
        return {"ok": True, "hosted": False, "user": None}
    init_db()
    email = str(body.get("email") or "").strip()
    password = str(body.get("password") or "")
    user = authenticate(email, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    request.session["user_id"] = user.id
    request.session["email"] = user.email
    return {
        "ok": True,
        "hosted": True,
        "user": {"id": user.id, "email": user.email, "is_admin": user.is_admin},
    }


@app.post("/auth/signup")
async def auth_signup(request: Request, body: dict) -> dict:
    """Public account creation. New users are never created as admins."""
    from app.auth_store import create_user, init_db

    if not hosted_mode():
        raise HTTPException(status_code=400, detail="Sign up is only available online")
    init_db()
    email = str(body.get("email") or "").strip()
    password = str(body.get("password") or "")
    try:
        user = create_user(email, password, is_admin=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request.session["user_id"] = user.id
    request.session["email"] = user.email
    return {
        "ok": True,
        "hosted": True,
        "user": {"id": user.id, "email": user.email, "is_admin": user.is_admin},
    }


@app.post("/auth/logout")
async def auth_logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@app.get("/auth/me")
async def auth_me(request: Request) -> dict:
    if not hosted_mode():
        return {"hosted": False, "user": None}
    from app.auth_store import get_user_by_id, init_db

    init_db()
    uid = request.session.get("user_id")
    if not uid:
        return {"hosted": True, "user": None}
    user = get_user_by_id(str(uid))
    if not user:
        request.session.clear()
        return {"hosted": True, "user": None}
    return {
        "hosted": True,
        "user": {"id": user.id, "email": user.email, "is_admin": user.is_admin},
    }


@app.post("/auth/users")
async def auth_create_user(request: Request, body: dict) -> dict:
    """Invite-only: admins create accounts for others."""
    from app.auth_store import create_user, get_user_by_id, init_db

    if not hosted_mode():
        raise HTTPException(status_code=400, detail="Only available in hosted mode")
    init_db()
    uid = request.session.get("user_id")
    admin = get_user_by_id(str(uid)) if uid else None
    if not admin or not admin.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        user = create_user(
            str(body.get("email") or ""),
            str(body.get("password") or ""),
            is_admin=bool(body.get("is_admin")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "user": {"id": user.id, "email": user.email, "is_admin": user.is_admin},
    }


@app.get("/settings/keys")
def get_settings_keys(reveal: bool = False) -> dict:
    return settings_snapshot(reveal=reveal)


@app.put("/settings/keys")
def put_settings_keys(body: dict) -> dict:
    try:
        return update_keys(
            openai_api_key=body.get("openai_api_key"),
            xai_api_key=body.get("xai_api_key"),
            google_fonts_api_key=body.get("google_fonts_api_key"),
            clear_openai=bool(body.get("clear_openai")),
            clear_xai=bool(body.get("clear_xai")),
            clear_google_fonts=bool(body.get("clear_google_fonts")),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not write key storage: {exc}",
        ) from exc


@app.get("/public-gallery")
def public_gallery() -> dict:
    """Curated demo creatives (no account). Private user library stays behind auth."""
    from app.public_examples import list_public_examples

    return list_public_examples()


@app.get("/gallery")
def gallery(
    campaign_id: str | None = None,
    ratio: str | None = None,
    brand: str | None = None,
    kind: str | None = None,
) -> dict:
    private = list_gallery(campaign_id=campaign_id, ratio=ratio, brand=brand, kind=kind)
    # Signed-in library also shows the shipped public examples at the top.
    from app.public_examples import list_public_examples

    public = list_public_examples()
    if not campaign_id and not brand and not kind:
        creatives = list(public.get("creatives") or []) + list(private.get("creatives") or [])
        campaigns = list(public.get("campaigns") or []) + list(private.get("campaigns") or [])
        filters = private.get("filters") or {}
        pub_filters = public.get("filters") or {}
        return {
            **private,
            "campaigns": campaigns,
            "creatives": creatives,
            "filters": {
                "ratios": sorted(
                    set(filters.get("ratios") or []) | set(pub_filters.get("ratios") or [])
                ),
                "brands": sorted(
                    set(filters.get("brands") or []) | set(pub_filters.get("brands") or [])
                ),
                "campaigns": list(pub_filters.get("campaigns") or [])
                + list(filters.get("campaigns") or []),
                "kinds": sorted(
                    set(filters.get("kinds") or []) | set(pub_filters.get("kinds") or [])
                ),
            },
        }
    return private


@app.get("/campaigns")
def list_campaigns_endpoint() -> dict:
    return list_past_campaigns()


@app.get("/campaigns/{campaign_id}/open")
def open_campaign_endpoint(campaign_id: str) -> dict:
    try:
        return open_past_campaign(campaign_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/campaigns/{campaign_id}/draft")
def save_draft_endpoint(campaign_id: str) -> dict:
    try:
        return save_draft(campaign_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/campaigns/reveal-root")
def reveal_campaigns_root_endpoint() -> dict:
    if hosted_mode():
        raise HTTPException(status_code=404, detail="Not available in hosted mode")
    try:
        return reveal_campaign_folder(None)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/campaigns/{campaign_id}")
def delete_campaign_endpoint(campaign_id: str) -> dict:
    try:
        return delete_campaign(campaign_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/campaigns/{campaign_id}/reveal")
def reveal_campaign_endpoint(campaign_id: str) -> dict:
    if hosted_mode():
        raise HTTPException(status_code=404, detail="Not available in hosted mode")
    try:
        return reveal_campaign_folder(campaign_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/creatives/delete")
def delete_creatives_endpoint(body: dict) -> dict:
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="items must be a non-empty list")
    try:
        return delete_creative_files(
            [
                {
                    "campaign_id": str(i.get("campaign_id") or ""),
                    "path": str(i.get("path") or ""),
                }
                for i in items
                if isinstance(i, dict)
            ]
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/campaigns/cleanup-ephemeral")
def cleanup_ephemeral_endpoint(body: dict | None = None) -> dict:
    """Delete a never-generated non-draft campaign (used on restart / new intake)."""
    cid = (body or {}).get("campaign_id") if isinstance(body, dict) else None
    deleted = delete_if_ephemeral(str(cid) if cid else None)
    return {"ok": True, "deleted": deleted, "campaign_id": cid}


@app.get("/samples")
def list_samples() -> dict:
    from app.samples import list_sample_catalog

    return {"samples": list_sample_catalog()}


@app.post("/tools/run-assignment-cli")
def run_assignment_cli() -> dict:
    """Spawns a real OS terminal running the CLI smoke (not in-browser)."""
    if hosted_mode():
        raise HTTPException(status_code=404, detail="Not available in hosted mode")
    from app.assignment_launch import launch_assignment_terminal

    result = launch_assignment_terminal()
    if not result.get("ok"):
        # UI needs command/cwd; FastAPI detail may be a dict, not only a string.
        raise HTTPException(status_code=500, detail=result)
    return result


@app.post("/campaigns/from-sample/{sample_id}")
async def create_from_sample(sample_id: str) -> dict:
    from app.samples import create_campaign_from_sample

    try:
        return create_campaign_from_sample(sample_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/campaigns")
async def create_campaign_endpoint(
    brief_text: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    roles: list[str] = Form(default=[]),
) -> dict:
    try:
        cid = await create_campaign(brief_text, files, roles=roles)
        return {"campaign_id": cid}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/campaigns/{campaign_id}/parse")
async def parse_campaign_endpoint(
    campaign_id: str, background: BackgroundTasks
) -> dict:
    from app.trial import is_guest_id

    try:
        result = parse_campaign(campaign_id)
        # Guest trial: skip auto product-seed image jobs (extra host-key spend).
        if result.get("product_seeds_pending") and not is_guest_id(current_user_id()):
            from app.product_seeds import run_product_seeds_job

            loop = asyncio.get_running_loop()
            background.add_task(
                run_product_seeds_job, campaign_id, loop, **_job_tenant_kwargs()
            )
        elif result.get("product_seeds_pending") and is_guest_id(current_user_id()):
            result = {**result, "product_seeds_pending": False, "guest_seeds_skipped": True}
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/campaigns/{campaign_id}/product-seeds")
def get_product_seeds_status(campaign_id: str) -> dict:
    from app.fastapi_intake import load_campaign_brief
    from app.product_seeds import load_product_seeds_status

    status = load_product_seeds_status(campaign_id)
    brief = None
    try:
        brief = load_campaign_brief(campaign_id).model_dump()
    except FileNotFoundError:
        pass
    return {**status, "brief": brief}


@app.post("/campaigns/{campaign_id}/product-seeds/retry")
async def retry_product_seeds(
    campaign_id: str, background: BackgroundTasks
) -> dict:
    from app.fastapi_intake import load_campaign_brief
    from app.product_seeds import init_product_seeds_status, run_product_seeds_job

    try:
        brief = load_campaign_brief(campaign_id)
        seeds = init_product_seeds_status(campaign_id, brief)
        if seeds.get("status") == "pending":
            loop = asyncio.get_running_loop()
            background.add_task(
                run_product_seeds_job, campaign_id, loop, **_job_tenant_kwargs()
            )
        return seeds
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/campaigns/{campaign_id}/approve")
async def approve_campaign_endpoint(campaign_id: str, brief: Brief) -> dict:
    try:
        approve_campaign(campaign_id, brief)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/campaigns/{campaign_id}")
async def save_campaign_endpoint(campaign_id: str, brief: Brief) -> dict:
    try:
        save_campaign_brief(campaign_id, brief)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/campaigns/{campaign_id}/assets")
async def upload_assets(
    campaign_id: str,
    files: list[UploadFile] = File(default=[]),
    roles: list[str] = Form(default=[]),
) -> dict:
    from app.fastapi_intake import remap_uploaded_assets, save_role_uploads

    try:
        saved = await save_role_uploads(campaign_id, files, roles)
        remapped = remap_uploaded_assets(campaign_id)
        return {"saved": saved, **remapped}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/campaigns/{campaign_id}/generate")
async def generate_campaign(
    campaign_id: str,
    body: GenerateRequest,
    background: BackgroundTasks,
) -> dict:
    from app.fastapi_intake import load_campaign_brief
    from app.trial import (
        apply_trial_generate_guards,
        consume_trial_run_if_needed,
        host_openai_key,
        require_generate_access,
        trial_status,
    )

    try:
        require_generate_access()
    except ValueError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    product_count = 1
    try:
        brief = load_campaign_brief(campaign_id)
        product_count = max(1, len(brief.products or []))
    except Exception:
        pass

    body, estimated_stills = apply_trial_generate_guards(
        body, product_count=product_count
    )

    job_kwargs = _job_tenant_kwargs()
    status = trial_status()
    keys = dict(job_kwargs.get("api_keys") or {})
    # Snapshot host trial keys into the job so a consume mid-request cannot race the worker.
    if status.get("can_use_host_openai") and not keys.get("openai_api_key"):
        host_key = host_openai_key()
        if host_key:
            keys["openai_api_key"] = host_key
        job_kwargs["api_keys"] = keys
    used_trial = consume_trial_run_if_needed(estimated_stills=estimated_stills)

    job_id = f"{campaign_id}-job"
    loop = asyncio.get_running_loop()
    background.add_task(
        run_generate_job, campaign_id, body, loop, **job_kwargs
    )
    return {
        "job_id": job_id,
        "trial_run_consumed": used_trial,
        "trial_stills_budget": estimated_stills,
        "trial": trial_status(),
    }


@app.post("/campaigns/{campaign_id}/suggest-finalize")
def suggest_finalize_endpoint(campaign_id: str) -> dict:
    from app.finalize import run_suggest_finalize
    from app.fastapi_intake import load_campaign_brief

    try:
        brief = load_campaign_brief(campaign_id)
        style = run_suggest_finalize(campaign_id, brief)
        return {"ok": True, "suggest": style}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("suggest-finalize failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/campaigns/{campaign_id}/finalize-suggest")
def get_finalize_suggest(campaign_id: str) -> dict:
    from app.finalize import load_suggest

    style = load_suggest(campaign_id)
    if style is None:
        raise HTTPException(status_code=404, detail="No finalize suggest yet")
    return {"suggest": style}


@app.post("/campaigns/{campaign_id}/finalize")
def finalize_endpoint(campaign_id: str, body: FinalizeChoices | None = None) -> dict:
    from app.finalize import finalize_campaign
    from app.fastapi_intake import load_campaign_brief

    try:
        brief = load_campaign_brief(campaign_id)
        choices = body or FinalizeChoices()
        report = finalize_campaign(
            campaign_id,
            choices,
            brief=brief,
            run_suggest=choices.run_suggest,
        )
        return {"ok": True, "report": report.model_dump()}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("finalize failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/campaigns/{campaign_id}/localize-copy")
def localize_copy_endpoint(campaign_id: str, body: LocalizeCopyRequest) -> dict:
    """Re-adapt non-source locales after the source language copy changes."""
    from app.fastapi_intake import load_campaign_brief
    from app.providers.openai_writer import fill_localized_copy, normalize_language_id

    try:
        brief = load_campaign_brief(campaign_id)
        locales = [normalize_language_id(x) for x in (body.locales or []) if x]
        # De-dupe while preserving order (en-US and English both → English).
        seen: set[str] = set()
        deduped: list[str] = []
        for loc in locales:
            key = loc.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(loc)
        locales = deduped
        if not locales:
            locales = [
                normalize_language_id(x) for x in (brief.localize_to or ["English"]) if x
            ] or ["English"]
        locked = {normalize_language_id(str(x)) for x in (body.locked_locales or [])}
        seed_brief = brief.model_copy(
            update={
                "message": body.message or brief.message,
                "cta": body.cta or brief.cta,
                "supporting_copy": body.supporting_text
                if body.supporting is not None
                else brief.supporting_copy,
            }
        )
        existing_raw = body.existing or {}
        existing: dict[str, dict] = {}
        for loc, pair in existing_raw.items():
            id_ = normalize_language_id(loc)
            if hasattr(pair, "model_dump"):
                existing[id_] = pair.model_dump()
            else:
                existing[id_] = dict(pair)

        seed: dict[str, dict] = {}
        source = locales[0]
        for loc in locales:
            if loc in locked and loc != source:
                seed[loc] = existing.get(loc) or {
                    "message": "",
                    "cta": "",
                    "supporting": "",
                }
            elif loc == source:
                seed[loc] = {
                    "message": body.message,
                    "cta": body.cta,
                    "supporting": body.supporting_text,
                }
            else:
                # Force a fresh translation; do not keep English stubs.
                seed[loc] = {"message": "", "cta": "", "supporting": ""}

        filled = fill_localized_copy(
            seed_brief,
            seed,
            language_list=locales,
            force=True,
        )
        for loc in locales:
            if loc in locked and loc != source:
                prev = existing.get(loc) or {}
                filled[loc] = {
                    "message": str(prev.get("message") or ""),
                    "cta": str(prev.get("cta") or ""),
                    "supporting": str(prev.get("supporting") or ""),
                }
            elif loc == source:
                filled[loc] = {
                    "message": body.message,
                    "cta": body.cta,
                    "supporting": body.supporting_text,
                }
        return {"ok": True, "locales": filled}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("localize-copy failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/campaigns/{campaign_id}/suggest-copy")
def suggest_copy_endpoint(campaign_id: str) -> dict:
    from app.fastapi_intake import load_campaign_brief, save_campaign_brief
    from app.providers.openai_writer import OpenAIWriter

    try:
        brief = load_campaign_brief(campaign_id)
        writer = OpenAIWriter()
        product = brief.products[0] if brief.products else None
        if product is None:
            raise HTTPException(status_code=400, detail="Brief has no products")
        draft = writer.suggest_campaign_copy(brief, product)
        if draft.get("message"):
            brief.message = draft["message"]
            # Only fill empty product lines. User Review edits must not be wiped.
            if not (product.message or "").strip():
                product.message = draft["message"]
        if draft.get("cta"):
            brief.cta = draft["cta"]
            if not (product.cta or "").strip():
                product.cta = draft["cta"]
        if draft.get("supporting_copy") is not None:
            if not (brief.supporting_copy or "").strip():
                brief.supporting_copy = draft["supporting_copy"]
        if draft.get("legal_disclaimer") is not None:
            if not (brief.legal_disclaimer or "").strip():
                brief.legal_disclaimer = draft["legal_disclaimer"]
        save_campaign_brief(campaign_id, brief)
        return {"ok": True, "brief": brief.model_dump(), "draft": draft}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("suggest-copy failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _aspect_ratio_for_image(image: Path) -> str | None:
    """Pick the closest of 1:1 / 16:9 / 9:16 from the still's pixel size.

    xAI image-to-video accepts an aspect_ratio hint; without it, odd crops
    (especially 9:16) were more likely to fail or look wrong.
    """
    try:
        from PIL import Image

        with Image.open(image) as im:
            w, h = im.size
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    ratio = w / h
    candidates = {
        "1:1": 1.0,
        "16:9": 16 / 9,
        "9:16": 9 / 16,
    }
    best = min(candidates.items(), key=lambda item: abs(item[1] - ratio))
    return best[0]


@app.post("/campaigns/{campaign_id}/motion")
def create_motion(campaign_id: str, body: MotionRequest) -> dict:
    """Animate one existing still (Results / Library). This is the UI motion path."""
    from app.config import (
        motion_video_model,
        motion_video_resolution,
    )
    from app.fastapi_intake import load_campaign_brief
    from app.providers import xai_video
    from app.trial import require_motion_access

    try:
        require_motion_access()
    except ValueError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    key = get_xai_api_key()
    if not key:
        raise HTTPException(status_code=400, detail="XAI_API_KEY is required for motion")

    cdir = campaign_dir(campaign_id)
    if not cdir.exists():
        raise HTTPException(status_code=404, detail="campaign not found")

    raw = str(body.creative_path or "").replace("\\", "/").lstrip("/")
    for prefix in (f"campaigns/{campaign_id}/", f"{campaign_id}/"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    rel = Path(raw)
    if rel.is_absolute() or ".." in rel.parts:
        raise HTTPException(status_code=400, detail="creative_path must be relative to campaign")
    image = (cdir / rel).resolve()
    try:
        image.relative_to(cdir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="creative_path outside campaign") from exc
    if not image.exists():
        raise HTTPException(status_code=404, detail=f"creative not found: {rel.as_posix()}")

    out_name = Path(body.output_name or "creative.mp4").name
    if not out_name.lower().endswith(".mp4"):
        out_name = f"{out_name}.mp4"
    out = image.with_name(out_name)
    prompt = (body.prompt or "").strip()
    if not prompt:
        try:
            brief = load_campaign_brief(campaign_id)
            prompt = (
                (brief.motion_notes or "").strip()
                or (brief.creative_direction or "").strip()
                or (brief.message or "").strip()
            )
        except Exception:
            prompt = ""
    if not prompt:
        prompt = (
            "Subtle cinematic motion for a premium product ad. "
            "Keep the exact product, composition, and lighting. Soft camera drift. No new text."
        )
    extra = (body.prompt_extra or "").strip()
    if extra:
        prompt = f"{prompt}\n\n{extra}"
    result, reason = xai_video.generate_motion_with_reason(
        image,
        out,
        prompt=prompt,
        duration_seconds=body.duration_seconds,
        api_key=key,
        model=motion_video_model(),
        resolution=body.resolution or motion_video_resolution(),
        aspect_ratio=_aspect_ratio_for_image(image),
    )
    if not result:
        raise HTTPException(
            status_code=502,
            detail=reason or "Motion generation failed or was skipped",
        )
    try:
        rel_out = str(result.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        try:
            rel_out = f"campaigns/{campaign_id}/" + str(result.relative_to(cdir)).replace(
                "\\", "/"
            )
        except ValueError:
            rel_out = str(result).replace("\\", "/")

    # Point ONLY this still's report row at the new mp4.
    # Matching by basename alone used to rewrite every creative.png row across
    # ratios/products and made older motions disappear from Results.
    report_path = cdir / "report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            image_resolved = image.resolve()
            image_rel = str(image.relative_to(cdir)).replace("\\", "/").lower()
            image_campaign_rel = f"campaigns/{campaign_id}/{image_rel}".lower()
            for row in report.get("creatives") or []:
                if not isinstance(row, dict):
                    continue
                matched = False
                for key in ("path", "creative_path"):
                    raw_path = str(row.get(key) or "").replace("\\", "/").strip()
                    if not raw_path:
                        continue
                    low = raw_path.lower().lstrip("/")
                    for prefix in (f"campaigns/{campaign_id}/", f"{campaign_id}/"):
                        if low.startswith(prefix):
                            low = low[len(prefix) :]
                            break
                    if low == image_rel or raw_path.lower() == image_campaign_rel:
                        matched = True
                        break
                    try:
                        candidate = (cdir / low).resolve()
                        if candidate == image_resolved:
                            matched = True
                            break
                    except OSError:
                        pass
                if matched:
                    row["motion_path"] = rel_out
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Failed to update report with motion_path")

    return {"ok": True, "motion_path": rel_out}


@app.get("/campaigns/{campaign_id}/events")
async def campaign_events(campaign_id: str) -> EventSourceResponse:
    queue = bus.subscribe(campaign_id)

    async def gen():
        try:
            yield {
                "event": "connected",
                "data": json.dumps({"campaign_id": campaign_id}),
            }
            while True:
                payload = await queue.get()
                yield {
                    "event": payload["event"],
                    "data": json.dumps(payload["data"]),
                }
        finally:
            bus.unsubscribe(campaign_id, queue)

    return EventSourceResponse(gen())


@app.get("/campaigns/{campaign_id}/report.json")
def get_report_json(campaign_id: str) -> dict:
    # Merges on-disk mp4s into the report so Results can play motion without a rewrite.
    report = get_campaign_report(campaign_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report.json not found")
    return report


@app.get("/campaigns/{campaign_id}/report.md")
def get_report_md(campaign_id: str) -> FileResponse:
    path = campaigns_root() / campaign_id / "report.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="report.md not found")
    return FileResponse(path)


@app.get("/fonts/google")
def google_fonts(query: str = "") -> dict:
    return {"fonts": list_google_fonts(query)}


def _mount_frontend() -> None:
    # Same origin as the API so reviewers only open http://127.0.0.1:8000.
    dist = PROJECT_ROOT / "frontend" / "dist"
    if not dist.is_dir() or not (dist / "index.html").exists():
        @app.get("/")
        def root_api_only() -> dict:
            return {
                "service": "creative-automation",
                "docs": "/docs",
                "hint": "UI not built yet. Run Open-App.bat or: cd frontend && npm run build",
            }
        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="frontend-assets")

    index = dist / "index.html"

    @app.get("/")
    def spa_index() -> FileResponse:
        return FileResponse(index)

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        # Do not steal API / static output routes (registered earlier).
        candidate = dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


_mount_frontend()
