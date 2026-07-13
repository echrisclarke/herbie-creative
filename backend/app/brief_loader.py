from __future__ import annotations

import json
from pathlib import Path

import yaml

from app.schemas import Brief


def load_brief(path: str | Path) -> Brief:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Brief not found: {file_path}")
    text = file_path.read_text(encoding="utf-8")
    return parse_brief_text(text, suffix=file_path.suffix.lower())


def parse_brief_text(text: str, suffix: str = ".json") -> Brief:
    data = _load_structured(text, suffix)
    if data is None:
        raise ValueError(
            "Could not parse brief as JSON or YAML. "
            "Use a structured file or run through the parse API for natural language."
        )
    return Brief.model_validate(data)


def try_parse_structured(text: str) -> Brief | None:
    for suffix in (".json", ".yaml"):
        data = _load_structured(text, suffix)
        if data is None:
            continue
        try:
            return Brief.model_validate(data)
        except Exception:
            continue
    return None


def _load_structured(text: str, suffix: str) -> dict | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        if suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(stripped)
        else:
            data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except Exception:
        if suffix == ".json":
            try:
                data = yaml.safe_load(stripped)
                if isinstance(data, dict):
                    return data
            except Exception:
                return None
    return None


def missing_required_fields(
    brief: Brief, *, require_two_products: bool = False
) -> list[str]:
    """Minimal blockers for Generate. Assignment smoke can require 2+ products via flag."""
    missing: list[str] = []
    if not (brief.campaign_name or "").strip():
        missing.append("campaign name")
    if not brief.products:
        missing.append("at least one product")
    elif require_two_products and len(brief.products) < 2:
        missing.append("at least two products (assignment smoke)")
    if not brief.outputs:
        missing.append("at least one output ratio")
    return missing
