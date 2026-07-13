"""Browse finished campaign creatives for the Samples gallery tab."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT, campaigns_root

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_MEDIA_EXTS = _IMAGE_EXTS | {".mp4"}
_RATIO_RE = re.compile(r"(1x1|9x16|16x9|1:1|9:16|16:9)", re.I)


def _norm_ratio(raw: str) -> str:
    text = (raw or "").strip().lower().replace("x", ":")
    if text.startswith("1:1"):
        return "1:1"
    if text.startswith("9:16"):
        return "9:16"
    if text.startswith("16:9"):
        return "16:9"
    return raw.strip() or "unknown"


def _rel_url(path: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(campaigns_root().resolve())
    except ValueError:
        try:
            rel = path.resolve().relative_to(PROJECT_ROOT.resolve())
            text = rel.as_posix()
            if text.startswith("campaigns/"):
                text = text[len("campaigns/") :]
            return f"/outputs/{text}"
        except ValueError:
            return None
    return f"/outputs/{rel.as_posix()}"


def _campaign_title(campaign_id: str, root: Path) -> str:
    for name in ("campaign.json", "intake/brief.json"):
        path = root / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        title = (data.get("campaign_name") or data.get("brand") or "").strip()
        if title:
            return title
    return campaign_id.replace("-", " ")


def _campaign_brand(root: Path) -> str:
    for name in ("campaign.json", "intake/brief.json"):
        path = root / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        brand = (data.get("brand") or "").strip()
        if brand:
            return brand
    return ""


def _from_report(campaign_id: str, root: Path) -> list[dict[str, Any]]:
    report_path = root / "report.json"
    if not report_path.is_file():
        return []
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    creatives = report.get("creatives") or []
    if not isinstance(creatives, list):
        return []
    title = _campaign_title(campaign_id, root)
    brand = _campaign_brand(root)
    items: list[dict[str, Any]] = []
    for c in creatives:
        if not isinstance(c, dict):
            continue
        rel = (c.get("path") or c.get("creative_path") or "").replace("\\", "/")
        if not rel:
            continue
        if rel.startswith("campaigns/"):
            rel = rel[len("campaigns/") :]
        file_path = campaigns_root() / rel
        if not file_path.is_file():
            # path may already be under campaign id
            alt = root / rel
            if alt.is_file():
                file_path = alt
            else:
                # Also try stripping leading campaign_id/
                if rel.startswith(f"{campaign_id}/"):
                    alt2 = root / rel[len(campaign_id) + 1 :]
                    if alt2.is_file():
                        file_path = alt2
                    else:
                        continue
                else:
                    continue
        url = _rel_url(file_path)
        if not url:
            continue
        ratio = _norm_ratio(str(c.get("ratio") or ""))
        product = str(c.get("product") or "creative")
        still_kind = "motion" if file_path.suffix.lower() == ".mp4" else "still"
        items.append(
            {
                "campaign_id": campaign_id,
                "campaign_name": title,
                "brand": brand,
                "product": product,
                "ratio": ratio,
                "kind": still_kind,
                "url": url,
                "filename": file_path.name,
            }
        )
        motion = c.get("motion_path")
        if motion:
            mrel = str(motion).replace("\\", "/")
            if mrel.startswith("campaigns/"):
                mrel = mrel[len("campaigns/") :]
            mpath = campaigns_root() / mrel
            if not mpath.is_file():
                alt_m = root / mrel
                if alt_m.is_file():
                    mpath = alt_m
                elif mrel.startswith(f"{campaign_id}/"):
                    alt_m2 = root / mrel[len(campaign_id) + 1 :]
                    if alt_m2.is_file():
                        mpath = alt_m2
            if mpath.is_file():
                murl = _rel_url(mpath)
                if murl:
                    items.append(
                        {
                            "campaign_id": campaign_id,
                            "campaign_name": title,
                            "brand": brand,
                            "product": product,
                            "ratio": ratio,
                            "kind": "motion",
                            "url": murl,
                            "filename": mpath.name,
                        }
                    )
            else:
                # Absolute Windows paths from older runs
                abs_try = Path(str(motion))
                if abs_try.is_file():
                    murl = _rel_url(abs_try)
                    if murl:
                        items.append(
                            {
                                "campaign_id": campaign_id,
                                "campaign_name": title,
                                "brand": brand,
                                "product": product,
                                "ratio": ratio,
                                "kind": "motion",
                                "url": murl,
                                "filename": abs_try.name,
                            }
                        )
    return items


def _from_outputs_scan(campaign_id: str, root: Path) -> list[dict[str, Any]]:
    outputs = root / "outputs"
    if not outputs.is_dir():
        return []
    title = _campaign_title(campaign_id, root)
    brand = _campaign_brand(root)
    items: list[dict[str, Any]] = []
    for path in sorted(outputs.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _MEDIA_EXTS:
            continue
        # Skip tiny thumbs / uploads leftovers if any sneak in
        if "uploads" in path.parts:
            continue
        url = _rel_url(path)
        if not url:
            continue
        rel_parts = path.relative_to(outputs).parts
        product = rel_parts[1] if len(rel_parts) >= 2 else (rel_parts[0] if rel_parts else "creative")
        ratio_raw = ""
        for part in rel_parts:
            if _RATIO_RE.search(part):
                ratio_raw = part
                break
        if not ratio_raw:
            m = _RATIO_RE.search(path.name)
            ratio_raw = m.group(0) if m else "unknown"
        kind = "motion" if path.suffix.lower() == ".mp4" else "still"
        items.append(
            {
                "campaign_id": campaign_id,
                "campaign_name": title,
                "brand": brand,
                "product": product.replace("-", " "),
                "ratio": _norm_ratio(ratio_raw),
                "kind": kind,
                "url": url,
                "filename": path.name,
            }
        )
    return items


def _item_key(item: dict[str, Any]) -> str:
    return str(item.get("url") or item.get("filename") or "").lower()


def _merge_gallery_items(
    primary: list[dict[str, Any]], extra: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Keep report rows, then add scanned files (especially orphan mp4s) not already listed."""
    seen = {_item_key(i) for i in primary if _item_key(i)}
    merged = list(primary)
    for item in extra:
        key = _item_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def list_gallery(
    *,
    campaign_id: str | None = None,
    ratio: str | None = None,
    brand: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    root = campaigns_root()
    all_creatives: list[dict[str, Any]] = []
    campaign_meta: dict[str, dict[str, Any]] = {}

    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        report_items = _from_report(child.name, child)
        scan_items = _from_outputs_scan(child.name, child)
        # Always merge: report may omit motion_path even when mp4s exist on disk.
        items = _merge_gallery_items(report_items, scan_items) if report_items else scan_items
        if not items:
            continue
        camp_brand = (
            next((i.get("brand") for i in items if i.get("brand")), None)
            or _campaign_brand(child)
        )
        # Folder-name fallback so motion-only smoke folders still filter by brand.
        if not camp_brand:
            lower = child.name.lower()
            if "cardobot" in lower or "card-o-bot" in lower:
                camp_brand = "Card-o-Bot"
            elif "jordan" in lower:
                camp_brand = "Jordan"
            elif "spitfire" in lower:
                camp_brand = "Spitfire Wheels"
        if camp_brand:
            for item in items:
                if not item.get("brand"):
                    item["brand"] = camp_brand
        camp_name = items[0].get("campaign_name") or _campaign_title(child.name, child)
        campaign_meta[child.name] = {
            "id": child.name,
            "name": camp_name,
            "brand": camp_brand,
        }
        all_creatives.extend(items)

    filter_ratios = sorted(
        {_norm_ratio(str(c.get("ratio") or "")) for c in all_creatives if c.get("ratio")}
    )
    filter_brands = sorted({str(c.get("brand") or "") for c in all_creatives if c.get("brand")})
    filter_kinds = sorted({str(c.get("kind") or "still") for c in all_creatives})

    creatives = all_creatives
    if campaign_id:
        creatives = [c for c in creatives if c.get("campaign_id") == campaign_id]
    if ratio:
        want = _norm_ratio(ratio)
        creatives = [c for c in creatives if _norm_ratio(str(c.get("ratio") or "")) == want]
    if brand:
        b = brand.strip().lower()
        creatives = [c for c in creatives if (c.get("brand") or "").lower() == b]
    if kind:
        k = kind.strip().lower()
        creatives = [c for c in creatives if str(c.get("kind") or "still").lower() == k]

    by_campaign: dict[str, list[dict[str, Any]]] = {}
    for c in creatives:
        by_campaign.setdefault(str(c.get("campaign_id")), []).append(c)

    campaigns: list[dict[str, Any]] = []
    for cid, items in by_campaign.items():
        meta = campaign_meta.get(cid) or {"id": cid, "name": cid, "brand": ""}
        campaigns.append(
            {
                **meta,
                "creative_count": len(items),
                "ratios": sorted({_norm_ratio(str(i.get("ratio") or "")) for i in items}),
                "products": sorted({str(i.get("product") or "") for i in items if i.get("product")}),
            }
        )
    campaigns.sort(key=lambda c: str(c.get("name") or "").lower())

    all_campaigns = [
        {
            **meta,
            "creative_count": sum(
                1 for c in all_creatives if c.get("campaign_id") == meta["id"]
            ),
        }
        for meta in sorted(campaign_meta.values(), key=lambda m: str(m.get("name") or "").lower())
    ]

    return {
        "campaigns": campaigns,
        "creatives": creatives,
        "filters": {
            "ratios": filter_ratios or ["1:1", "9:16", "16:9"],
            "brands": filter_brands,
            "campaigns": all_campaigns,
            "kinds": filter_kinds or ["still", "motion"],
        },
    }
