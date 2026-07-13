"""Extract campaign brief text from uploaded documents (including PDF)."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TEXT_SUFFIXES = {".txt", ".md", ".json", ".yaml", ".yml"}
PDF_SUFFIX = ".pdf"
BRIEF_SUFFIXES = TEXT_SUFFIXES | {PDF_SUFFIX}


def read_document_text(path: Path) -> str:
    """Return plain text from a brief document. PDFs may call OpenAI when needed."""
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == PDF_SUFFIX:
        return _read_pdf_text(path)
    raise ValueError(f"Unsupported brief file type: {suffix or path.name}")


def _read_pdf_text(path: Path) -> str:
    extracted = _extract_pdf_with_pypdf(path)
    if len(extracted.strip()) >= 80:
        return extracted.strip()
    # Scanned / image-heavy PDFs: ask ChatGPT to read the file.
    try:
        from app.providers.openai_writer import OpenAIWriter

        writer = OpenAIWriter()
        ai_text = writer.extract_text_from_pdf(path)
        if ai_text.strip():
            return ai_text.strip()
    except Exception:
        logger.exception("OpenAI PDF read failed for %s", path)
    if extracted.strip():
        return extracted.strip()
    raise ValueError(
        "Could not read text from this PDF. Try a text-based PDF or paste the brief."
    )


def _extract_pdf_with_pypdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required to read PDF briefs") from exc
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            logger.exception("pypdf page extract failed")
    return "\n\n".join(chunks).strip()
