from __future__ import annotations

import json
from pathlib import Path

from app.schemas import Report


def write_report(campaign_dir: Path, report: Report) -> None:
    campaign_dir.mkdir(parents=True, exist_ok=True)
    json_path = campaign_dir / "report.json"
    md_path = campaign_dir / "report.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(_to_markdown(report), encoding="utf-8")


def write_live_report(
    campaign_dir: Path,
    *,
    campaign_id: str,
    started_at: str,
    creatives: list,
    totals: dict | None = None,
) -> None:
    """Write a partial report so Library / Gallery can refresh mid-run."""
    report = Report(
        campaign_id=campaign_id,
        started_at=started_at,
        finished_at="",
        storage_backend="local",
        creatives=list(creatives),
        totals={
            "tiles": len(creatives),
            "partial": True,
            **(totals or {}),
        },
    )
    write_report(campaign_dir, report)


def _to_markdown(report: Report) -> str:
    lines = [
        f"# Report: {report.campaign_id}",
        "",
        f"- Started: {report.started_at}",
        f"- Finished: {report.finished_at}",
        f"- Storage: {report.storage_backend}",
        f"- Totals: {json.dumps(report.totals)}",
        "",
        "## Creatives",
        "",
    ]
    for c in report.creatives:
        lines.append(
            f"- **{c.product}** `{c.ratio}` `{c.locale}` — source=`{c.source}` "
            f"provider=`{c.image_provider}` fallback=`{c.fallback_triggered}` "
            f"path=`{c.path}`"
        )
        if c.creative_path:
            lines.append(f"  - creative (no text): `{c.creative_path}`")
        if c.message:
            lines.append(f"  - message: {c.message}")
        if c.compliance:
            lines.append(f"  - compliance: {c.compliance}")
        if c.motion_path:
            lines.append(f"  - motion: `{c.motion_path}`")
    lines.append("")
    return "\n".join(lines)
