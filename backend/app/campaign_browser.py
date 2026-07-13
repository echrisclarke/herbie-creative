"""List and reopen previously generated local campaigns."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import campaigns_root
from app.gallery import _campaign_brand, _campaign_title, _from_outputs_scan, _from_report

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _mtime_iso(path: Path) -> str | None:
    try:
        ts = path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _count_output_media(root: Path) -> int:
    outputs = root / "outputs"
    if not outputs.is_dir():
        return 0
    exts = _IMAGE_EXTS | {".mp4"}
    return sum(
        1
        for p in outputs.rglob("*")
        if p.is_file() and p.suffix.lower() in exts and "uploads" not in p.parts
    )


def _count_output_images(root: Path) -> int:
    return _count_output_media(root)


def _rmtree_windows(path: Path) -> None:
    """Best-effort recursive delete that tolerates OneDrive / locked read handles."""
    import os
    import stat
    import time

    def _onerror(func, p, _exc_info):  # noqa: ANN001
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    last_err: Exception | None = None
    for attempt in range(4):
        try:
            if not path.exists():
                return
            shutil.rmtree(path, onerror=_onerror)
            if not path.exists():
                return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(0.2 * (attempt + 1))
    if path.exists():
        raise OSError(f"Could not delete campaign folder (file in use?): {path}") from last_err


def delete_campaign(campaign_id: str) -> dict[str, Any]:
    root = campaigns_root() / campaign_id
    if not root.is_dir():
        raise FileNotFoundError(f"Campaign not found: {campaign_id}")
    if campaign_id.startswith("_"):
        raise ValueError("Cannot delete system folders")
    _rmtree_windows(root)
    return {"ok": True, "deleted": campaign_id}


def delete_creative_files(items: list[dict[str, str]]) -> dict[str, Any]:
    """Delete specific creative media files and scrub them from report.json."""
    deleted: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    by_campaign: dict[str, list[Path]] = {}

    for raw in items:
        campaign_id = str(raw.get("campaign_id") or "").strip()
        path_text = str(raw.get("path") or "").strip()
        if not campaign_id or not path_text:
            continue
        if campaign_id.startswith("_"):
            raise ValueError(f"Cannot modify system folder: {campaign_id}")
        root = campaigns_root() / campaign_id
        if not root.is_dir():
            missing.append({"campaign_id": campaign_id, "path": path_text})
            continue
        resolved = _resolve_campaign_file(campaign_id, root, path_text)
        if resolved is None:
            # Also accept /outputs/... URLs from the gallery
            text = path_text.replace("\\", "/")
            if text.startswith("/outputs/"):
                text = text[len("/outputs/") :]
            if text.startswith("outputs/"):
                text = text[len("outputs/") :]
            resolved = _resolve_campaign_file(campaign_id, root, text)
        if resolved is None or not resolved.is_file():
            missing.append({"campaign_id": campaign_id, "path": path_text})
            continue
        # Safety: only delete under this campaign folder
        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"Path outside campaign: {path_text}") from exc
        by_campaign.setdefault(campaign_id, []).append(resolved)

    for campaign_id, files in by_campaign.items():
        root = campaigns_root() / campaign_id
        removed_rels: set[str] = set()
        for file_path in files:
            try:
                rel = _campaign_rel_path(campaign_id, file_path, root)
                file_path.unlink(missing_ok=True)
                deleted.append({"campaign_id": campaign_id, "path": rel})
                removed_rels.add(rel.replace("\\", "/").lower())
                # Also track bare relative forms for report matching
                if rel.startswith("campaigns/"):
                    removed_rels.add(rel[len("campaigns/") :].replace("\\", "/").lower())
            except OSError as exc:
                raise OSError(f"Could not delete {file_path}: {exc}") from exc
        _scrub_report_paths(campaign_id, root, removed_rels)

    return {
        "ok": True,
        "deleted": deleted,
        "missing": missing,
        "deleted_count": len(deleted),
    }


def _scrub_report_paths(campaign_id: str, root: Path, removed_rels: set[str]) -> None:
    """Remove or clear report.json rows that pointed at deleted files."""
    report_path = root / "report.json"
    if not report_path.is_file() or not removed_rels:
        return
    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(raw, dict):
        return
    creatives = raw.get("creatives")
    if not isinstance(creatives, list):
        return

    def _norm(p: str | None) -> str:
        text = str(p or "").replace("\\", "/").strip().lower()
        if text.startswith("campaigns/"):
            text = text[len("campaigns/") :]
        if text.startswith("/outputs/"):
            text = text[len("/outputs/") :]
        return text

    kept: list[Any] = []
    for row in creatives:
        if not isinstance(row, dict):
            continue
        row = dict(row)
        path_n = _norm(row.get("path"))
        creative_n = _norm(row.get("creative_path"))
        motion_n = _norm(row.get("motion_path"))

        if path_n and path_n in removed_rels:
            # Whole row was the deleted media (still or motion-only).
            if motion_n and motion_n not in removed_rels:
                # Keep as motion-only if mp4 remains
                row["path"] = row.get("motion_path")
                row["locale"] = "motion"
                row.pop("creative_path", None)
                kept.append(row)
            continue

        if creative_n and creative_n in removed_rels:
            row.pop("creative_path", None)

        if motion_n and motion_n in removed_rels:
            row["motion_path"] = None

        # Drop empty motion-only leftovers
        path_now = _norm(row.get("path"))
        if not path_now and not _norm(row.get("motion_path")):
            continue
        kept.append(row)

    raw["creatives"] = kept
    totals = raw.get("totals") if isinstance(raw.get("totals"), dict) else {}
    totals = dict(totals)
    totals["tiles"] = len(kept)
    raw["totals"] = totals
    report_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")


def delete_if_ephemeral(campaign_id: str | None) -> bool:
    if not campaign_id:
        return False
    root = campaigns_root() / campaign_id
    if not root.is_dir() or not is_ephemeral(root):
        return False
    _rmtree_windows(root)
    return True


def reveal_campaign_folder(campaign_id: str | None = None) -> dict[str, Any]:
    """Open the campaigns root or a specific campaign folder in the OS file manager."""
    import subprocess
    import sys

    root = campaigns_root()
    target = root / campaign_id if campaign_id else root
    if campaign_id and not target.is_dir():
        raise FileNotFoundError(f"Campaign not found: {campaign_id}")
    if not target.is_dir():
        raise FileNotFoundError(f"Folder not found: {target}")

    path = str(target.resolve())
    if sys.platform.startswith("win"):
        _reveal_windows_folder(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])  # noqa: S603
    else:
        subprocess.Popen(["xdg-open", path])  # noqa: S603
    return {"ok": True, "path": path}


def _reveal_windows_folder(path: str) -> None:
    """Open a folder in Explorer and request it come to the foreground."""
    import subprocess
    import threading

    # ShellExecute "explore" + SW_SHOWNORMAL usually activates the window.
    # Plain `explorer path` often opens behind the browser.
    opened = False
    try:
        import ctypes

        SW_SHOWNORMAL = 1
        rc = int(
            ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
                None, "explore", path, None, None, SW_SHOWNORMAL
            )
        )
        opened = rc > 32
    except Exception:
        opened = False

    if not opened:
        # `start` activates the new window; first quoted arg is the window title.
        subprocess.Popen(  # noqa: S602
            f'cmd /c start "" "{path}"',
            shell=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    folder_name = Path(path).name or path

    def _nudge() -> None:
        import time

        try:
            time.sleep(0.4)
            _focus_windows_explorer(folder_name)
        except Exception:
            pass

    threading.Thread(target=_nudge, daemon=True).start()


def _focus_windows_explorer(folder_name: str) -> None:
    """Best-effort: restore/foreground visible windows titled like the folder."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    SW_RESTORE = 9
    ASFW_ANY = -1
    matches: list[int] = []

    try:
        user32.AllowSetForegroundWindow(ASFW_ANY)
    except Exception:
        pass

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or ""
        if (
            title == folder_name
            or title.startswith(f"{folder_name} -")
            or title.startswith(f"{folder_name} ")
        ):
            matches.append(int(hwnd))
        return True

    user32.EnumWindows(_enum, 0)
    for hwnd in matches:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)


def _meta_path(root: Path) -> Path:
    return root / "meta.json"


def _read_meta(root: Path) -> dict[str, Any]:
    path = _meta_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_meta(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    path = _meta_path(root)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def is_draft(root: Path) -> bool:
    return (_read_meta(root).get("status") or "").strip().lower() == "draft"


def is_ephemeral(root: Path) -> bool:
    """Never generated and not explicitly saved as draft."""
    if is_draft(root):
        return False
    if (root / "report.json").is_file():
        return False
    if _count_output_images(root) > 0:
        return False
    return True


def save_draft(campaign_id: str) -> dict[str, Any]:
    root = campaigns_root() / campaign_id
    if not root.is_dir():
        raise FileNotFoundError(f"Campaign not found: {campaign_id}")
    meta = _read_meta(root)
    meta["status"] = "draft"
    meta["saved_at"] = datetime.now(tz=timezone.utc).isoformat()
    _write_meta(root, meta)
    return {"ok": True, "campaign_id": campaign_id, "status": "draft", "meta": meta}


def mark_campaign_completed(campaign_id: str) -> None:
    root = campaigns_root() / campaign_id
    if not root.is_dir():
        return
    meta = _read_meta(root)
    meta["status"] = "completed"
    meta["completed_at"] = datetime.now(tz=timezone.utc).isoformat()
    _write_meta(root, meta)


def _thumb_url(campaign_id: str, root: Path) -> str | None:
    items = _from_report(campaign_id, root) or _from_outputs_scan(campaign_id, root)
    for item in items:
        url = item.get("url")
        if url and not str(url).endswith(".mp4"):
            return str(url)
    return None


def list_past_campaigns() -> dict[str, Any]:
    root = campaigns_root()
    campaigns: list[dict[str, Any]] = []

    for child in root.iterdir():
        if not child.is_dir() or child.name.startswith("_"):
            continue
        has_brief = (child / "campaign.json").is_file() or (child / "intake" / "brief.json").is_file()
        has_report = (child / "report.json").is_file()
        media_count = _count_output_media(child)
        draft = is_draft(child)

        # Live directory scan: only show folders that still exist with content or draft/brief.
        if not draft and not has_report and media_count == 0 and not has_brief:
            continue
        if not draft and not has_report and media_count == 0:
            # Brief-only never-generated campaigns stay hidden unless drafted.
            continue

        if draft and media_count == 0 and not has_report:
            stage = "draft"
        elif has_report or media_count > 0:
            stage = "results" if has_report else "finalize"
        elif has_brief:
            stage = "review"
        else:
            stage = "empty"

        stamp_path = child / "report.json"
        if not stamp_path.is_file():
            stamp_path = _meta_path(child) if _meta_path(child).is_file() else child / "campaign.json"
        if not stamp_path.is_file():
            stamp_path = child

        campaigns.append(
            {
                "id": child.name,
                "name": _campaign_title(child.name, child),
                "brand": _campaign_brand(child),
                "stage": stage,
                "is_draft": draft and stage == "draft",
                "has_brief": has_brief,
                "has_report": has_report,
                "creative_count": media_count,
                "modified_at": _mtime_iso(stamp_path),
                "thumb_url": _thumb_url(child.name, child),
                "folder_path": str(child.resolve()),
            }
        )

    campaigns.sort(key=lambda c: c.get("modified_at") or "", reverse=True)
    return {"campaigns": campaigns}


def _campaign_rel_path(campaign_id: str, file_path: Path, root: Path) -> str:
    try:
        rel = file_path.resolve().relative_to(campaigns_root().resolve()).as_posix()
    except ValueError:
        try:
            rel = file_path.resolve().relative_to(root.resolve()).as_posix()
            rel = f"{campaign_id}/{rel}"
        except ValueError:
            return file_path.as_posix().replace("\\", "/")
    return rel if rel.startswith("campaigns/") else f"campaigns/{rel}"


def _resolve_campaign_file(campaign_id: str, root: Path, rel: str | None) -> Path | None:
    """Resolve a report-relative path to an existing file, or None if missing."""
    if not rel:
        return None
    text = str(rel).replace("\\", "/").strip()
    if not text:
        return None
    # Absolute path from older runs
    abs_try = Path(text)
    if abs_try.is_file():
        return abs_try.resolve()
    if text.startswith("campaigns/"):
        text = text[len("campaigns/") :]
    candidates = [
        campaigns_root() / text,
        root / text,
    ]
    if text.startswith(f"{campaign_id}/"):
        candidates.append(root / text[len(campaign_id) + 1 :])
    for cand in candidates:
        try:
            if cand.is_file():
                return cand.resolve()
        except OSError:
            continue
    return None


def _scan_item_to_creative(campaign_id: str, item: dict[str, Any]) -> dict[str, Any] | None:
    url = str(item.get("url") or "")
    if not url.startswith("/outputs/"):
        return None
    rel = url[len("/outputs/") :]
    path = rel if rel.startswith("campaigns/") else f"campaigns/{rel}"
    kind = str(item.get("kind") or "still")
    is_motion = kind == "motion" or path.lower().endswith(".mp4")
    return {
        "product": item.get("product") or "creative",
        "ratio": item.get("ratio") or "1:1",
        "path": path,
        "locale": "motion" if is_motion else "creative",
        "source": "reopened",
        "image_provider": "openai",
        "fallback_triggered": False,
        "motion_path": path if is_motion else None,
        "compliance": {},
    }


def _sync_creatives_with_disk(
    campaign_id: str, root: Path, creatives: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Drop report rows whose files are gone; add on-disk media not listed in the report."""
    kept: list[dict[str, Any]] = []
    seen_files: set[Path] = set()

    for row in creatives:
        if not isinstance(row, dict):
            continue
        row = dict(row)
        path_file = _resolve_campaign_file(
            campaign_id, root, str(row.get("path") or "") or None
        )
        creative_file = _resolve_campaign_file(
            campaign_id, root, str(row.get("creative_path") or "") or None
        )
        motion_file = _resolve_campaign_file(
            campaign_id, root, str(row.get("motion_path") or "") or None
        )

        if path_file is None and creative_file is not None:
            path_file = creative_file
            row["path"] = _campaign_rel_path(campaign_id, creative_file, root)

        if path_file is None and motion_file is not None:
            # Motion-only row (still deleted, mp4 remains)
            row["path"] = _campaign_rel_path(campaign_id, motion_file, root)
            row["motion_path"] = row["path"]
            row["locale"] = "motion"
            path_file = motion_file

        if path_file is None:
            continue

        row["path"] = _campaign_rel_path(campaign_id, path_file, root)
        if creative_file is not None:
            row["creative_path"] = _campaign_rel_path(campaign_id, creative_file, root)
        elif "creative_path" in row and not _resolve_campaign_file(
            campaign_id, root, str(row.get("creative_path") or "")
        ):
            row.pop("creative_path", None)

        if motion_file is not None:
            row["motion_path"] = _campaign_rel_path(campaign_id, motion_file, root)
            seen_files.add(motion_file)
        else:
            row["motion_path"] = None

        seen_files.add(path_file)
        kept.append(row)

    # Add stills/videos present on disk but missing from report.json
    for item in _from_outputs_scan(campaign_id, root):
        url = str(item.get("url") or "")
        if not url.startswith("/outputs/"):
            continue
        rel = url[len("/outputs/") :]
        disk = _resolve_campaign_file(campaign_id, root, rel)
        if disk is None or disk in seen_files:
            continue
        creative = _scan_item_to_creative(campaign_id, item)
        if not creative:
            continue
        seen_files.add(disk)
        kept.append(creative)

    return kept


def _attach_disk_motion(
    campaign_id: str, root: Path, creatives: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Link on-disk mp4s onto still rows (and add orphan motion tiles)."""
    outputs = root / "outputs"
    if not outputs.is_dir():
        return creatives

    mp4s = [
        p
        for p in outputs.rglob("*.mp4")
        if p.is_file() and "uploads" not in p.parts
    ]
    if not mp4s:
        return creatives

    used: set[Path] = set()
    out: list[dict[str, Any]] = []

    for row in creatives:
        row = dict(row)
        existing = row.get("motion_path")
        if existing:
            resolved_existing = _resolve_campaign_file(
                campaign_id, root, str(existing) or None
            )
            if resolved_existing is not None:
                used.add(resolved_existing.resolve())
                row["motion_path"] = _campaign_rel_path(
                    campaign_id, resolved_existing, root
                )
                out.append(row)
                continue
            # Stale path: clear and try to re-attach from this still's folder only.
            row["motion_path"] = None

        still = str(row.get("path") or row.get("creative_path") or "").replace("\\", "/")
        still_name = Path(still).name if still else ""
        still_stem = Path(still_name).stem if still_name else ""
        still_dir: Path | None = None
        if still:
            rel = still.removeprefix("campaigns/")
            for candidate in (campaigns_root() / rel, root / rel, root / Path(rel).name):
                if candidate.is_file():
                    still_dir = candidate.parent
                    break
                nested = root / Path(*Path(rel).parts[1:])
                if nested.is_file():
                    still_dir = nested.parent
                    break

        attached: Path | None = None
        if still_dir and still_dir.is_dir():
            preferred: list[Path] = []
            if still_stem:
                preferred.append(still_dir / f"{still_stem}.mp4")
            preferred.extend(
                [
                    still_dir / "creative.mp4",
                    still_dir / "final.mp4",
                ]
            )
            preferred.extend(sorted(still_dir.glob("*.mp4")))
            for cand in preferred:
                if cand.is_file() and cand.resolve() not in used:
                    attached = cand
                    break

        # Do not steal an mp4 from another product/ratio via a loose ratio match.
        # Orphan mp4s are added as their own tiles below.

        if attached is not None:
            used.add(attached.resolve())
            row["motion_path"] = _campaign_rel_path(campaign_id, attached, root)
        out.append(row)

    # Orphan mp4s become their own playable Results tiles
    for mp4 in mp4s:
        if mp4.resolve() in used:
            continue
        rel = _campaign_rel_path(campaign_id, mp4, root)
        ratio = "1:1"
        for part in mp4.parts:
            low = part.lower().replace("x", ":")
            if low in {"1:1", "9:16", "16:9"} or part.lower() in {"1x1", "9x16", "16x9"}:
                ratio = part.lower().replace("x", ":")
                if ratio.count(":") == 1:
                    pass
                break
        product = mp4.parent.parent.name if mp4.parent.parent != outputs else mp4.stem
        out.append(
            {
                "product": product.replace("-", " "),
                "ratio": ratio.replace("x", ":") if "x" in ratio else ratio,
                "path": rel,
                "locale": "motion",
                "source": "reopened",
                "image_provider": "openai",
                "fallback_triggered": False,
                "motion_path": rel,
                "compliance": {},
            }
        )
        used.add(mp4.resolve())

    return out


def _normalize_report(campaign_id: str, raw: dict[str, Any], root: Path) -> dict[str, Any]:
    creatives = raw.get("creatives") if isinstance(raw.get("creatives"), list) else []
    creatives = [c for c in creatives if isinstance(c, dict)]

    # Always reconcile with the folder: drop missing files, add new ones on disk.
    creatives = _sync_creatives_with_disk(campaign_id, root, creatives)
    creatives = _attach_disk_motion(campaign_id, root, list(creatives))

    # After motion attach, drop any still whose path vanished and has no playable media
    cleaned: list[dict[str, Any]] = []
    for row in creatives:
        path_file = _resolve_campaign_file(campaign_id, root, str(row.get("path") or ""))
        motion_file = _resolve_campaign_file(
            campaign_id, root, str(row.get("motion_path") or "")
        )
        if path_file is None and motion_file is None:
            continue
        if path_file is None and motion_file is not None:
            row = dict(row)
            row["path"] = _campaign_rel_path(campaign_id, motion_file, root)
            row["motion_path"] = row["path"]
            row["locale"] = "motion"
        cleaned.append(row)
    creatives = cleaned

    totals = raw.get("totals") if isinstance(raw.get("totals"), dict) else {}
    totals = dict(totals)
    totals["tiles"] = len(creatives)
    totals.setdefault("from_provided", 0)
    totals.setdefault("concept_generated", sum(
        1 for c in creatives if str(c.get("source") or "") == "concept_generated"
    ))

    return {
        "campaign_id": raw.get("campaign_id") or campaign_id,
        "started_at": raw.get("started_at") or "",
        "finished_at": raw.get("finished_at") or "",
        "creatives": creatives,
        "totals": totals,
        "missing_fields": raw.get("missing_fields") or [],
    }


def get_campaign_report(campaign_id: str) -> dict[str, Any] | None:
    """Load report.json (or synthesize from outputs) with on-disk mp4s attached."""
    root = campaigns_root() / campaign_id
    if not root.is_dir():
        return None
    report_path = root / "report.json"
    if report_path.is_file():
        try:
            raw = json.loads(report_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return _normalize_report(campaign_id, raw, root)
        except (OSError, json.JSONDecodeError):
            pass
    if _count_output_images(root) > 0 or any(
        (root / "outputs").rglob("*.mp4") if (root / "outputs").is_dir() else []
    ):
        return _normalize_report(campaign_id, {}, root)
    return None


def open_past_campaign(campaign_id: str) -> dict[str, Any]:
    """Load a previous campaign for Results / Finalize / Review."""
    from app.fastapi_intake import load_campaign_brief, parse_campaign

    root = campaigns_root() / campaign_id
    if not root.is_dir():
        raise FileNotFoundError(f"Campaign not found: {campaign_id}")

    brief = None
    asset_manifest = None
    missing_fields: list[str] = []
    try:
        parsed = parse_campaign(campaign_id)
        brief = parsed.get("brief")
        asset_manifest = parsed.get("asset_manifest")
        missing_fields = parsed.get("missing_fields") or []
    except Exception:
        try:
            brief = load_campaign_brief(campaign_id).model_dump()
        except Exception:
            brief = None

    report = get_campaign_report(campaign_id)

    draft = is_draft(root)
    if report and report.get("creatives"):
        stage = "results"
    elif report or _count_output_images(root) > 0:
        stage = "finalize"
    elif draft:
        stage = "draft"
    elif brief:
        stage = "review"
    else:
        stage = "empty"

    tiles = (report or {}).get("creatives") or []

    return {
        "campaign_id": campaign_id,
        "name": _campaign_title(campaign_id, root),
        "brand": _campaign_brand(root),
        "stage": stage,
        "is_draft": draft and stage == "draft",
        "brief": brief,
        "asset_manifest": asset_manifest,
        "missing_fields": missing_fields,
        "report": report,
        "tiles": tiles,
    }
