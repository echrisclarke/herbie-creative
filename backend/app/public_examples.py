"""Curated public example creatives shipped under frontend/*/examples/."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_MEDIA_EXTS = _IMAGE_EXTS | {".mp4"}
_RATIO_RE = re.compile(r"^(1x1|9x16|16x9|1:1|9:16|16:9)$", re.I)


def examples_root() -> Path | None:
    for candidate in (
        PROJECT_ROOT / "frontend" / "dist" / "examples",
        PROJECT_ROOT / "frontend" / "public" / "examples",
    ):
        if candidate.is_dir():
            return candidate
    return None


def _norm_ratio(raw: str) -> str:
    text = (raw or "").strip().lower().replace("x", ":")
    if text.startswith("1:1"):
        return "1:1"
    if text.startswith("9:16"):
        return "9:16"
    if text.startswith("16:9"):
        return "16:9"
    return raw.strip() or "unknown"


def _load_manifest(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "manifest.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in data.get("campaigns") or []:
        if isinstance(item, dict) and item.get("id"):
            out[str(item["id"])] = item
    return out


def list_public_examples() -> dict[str, Any]:
    root = examples_root()
    if root is None:
        return {
            "campaigns": [],
            "creatives": [],
            "filters": {"ratios": [], "brands": [], "campaigns": [], "kinds": []},
            "public": True,
        }

    manifest = _load_manifest(root)
    creatives: list[dict[str, Any]] = []
    campaign_meta: dict[str, dict[str, Any]] = {}

    for camp_dir in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not camp_dir.is_dir() or camp_dir.name.startswith(".") or camp_dir.name == "jordan-ratio-crops":
            continue
        cid = camp_dir.name
        meta = manifest.get(cid) or {
            "id": cid,
            "title": cid.replace("-", " ").title(),
            "brand": "",
            "description": "",
        }
        campaign_meta[cid] = {
            "id": cid,
            "name": meta.get("title") or cid,
            "brand": meta.get("brand") or "",
            "description": meta.get("description") or "",
            "public_example": True,
        }
        for path in sorted(camp_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _MEDIA_EXTS:
                continue
            parts = path.relative_to(camp_dir).parts
            ratio = "unknown"
            product = parts[0] if parts else "creative"
            for part in parts:
                if _RATIO_RE.match(part):
                    ratio = _norm_ratio(part)
                    break
            kind = "motion" if path.suffix.lower() == ".mp4" else "still"
            rel = path.relative_to(root).as_posix()
            creatives.append(
                {
                    "campaign_id": cid,
                    "campaign_name": campaign_meta[cid]["name"],
                    "brand": campaign_meta[cid]["brand"],
                    "product": product,
                    "ratio": ratio,
                    "kind": kind,
                    "locale": "example",
                    "url": f"/examples/{rel}",
                    "public_example": True,
                }
            )

    campaigns = []
    for cid, meta in campaign_meta.items():
        items = [c for c in creatives if c["campaign_id"] == cid]
        if not items:
            continue
        campaigns.append(
            {
                **meta,
                "creative_count": len(items),
                "ratios": sorted({c["ratio"] for c in items}),
                "products": sorted({c["product"] for c in items if c.get("product")}),
            }
        )

    return {
        "campaigns": campaigns,
        "creatives": creatives,
        "filters": {
            "ratios": sorted({c["ratio"] for c in creatives}),
            "brands": sorted({c["brand"] for c in creatives if c.get("brand")}),
            "campaigns": campaigns,
            "kinds": sorted({c["kind"] for c in creatives}),
        },
        "public": True,
    }
