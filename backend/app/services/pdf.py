"""Markdown -> PDF conversion for generated CVs and cover letters.

Uses `markdown` + `xhtml2pdf` (pure-Python, no system libraries required). The
imports are soft so the app keeps running (falling back to plain-text output)
even if these optional dependencies aren't installed yet.
"""

import logging
import re

logger = logging.getLogger(__name__)

try:
    import markdown as _markdown
    from xhtml2pdf import pisa

    _PDF_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _PDF_AVAILABLE = False


def _strip_code_fences(text: str) -> str:
    """Safety net: drop a surrounding ```...``` fence so the document doesn't
    render as one monospace code block."""
    stripped = (text or "").strip()
    fence = re.match(r"^```[a-zA-Z]*\s*\n(.*?)\n?```$", stripped, flags=re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return stripped


# Styling tuned for a clean, one-page document.
_CSS = """
@page { size: A4; margin: 1.5cm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10.5px; line-height: 1.35; color: #111; }
h1 { text-align: center; font-size: 20px; margin: 0 0 2px 0; }
h1 + p { text-align: center; color: #444; margin: 0 0 8px 0; font-size: 10px; }
h2 { font-size: 13px; border-bottom: 1px solid #999; margin: 10px 0 4px 0; padding-bottom: 2px; text-transform: uppercase; }
h3 { font-size: 11.5px; margin: 6px 0 2px 0; }
ul { margin: 2px 0 6px 16px; padding: 0; }
li { margin: 1px 0; }
p { margin: 3px 0; }
a { color: #1a4f8b; text-decoration: none; }
strong { color: #000; }
"""


def pdf_supported() -> bool:
    return _PDF_AVAILABLE


def markdown_to_pdf(markdown_text: str, out_path: str) -> bool:
    """Render markdown text to a PDF file. Returns True on success."""
    if not _PDF_AVAILABLE:
        return False
    try:
        cleaned = _strip_code_fences(markdown_text)
        body = _markdown.markdown(cleaned, extensions=["extra", "sane_lists", "nl2br"])
        html = (
            "<html><head><meta charset='utf-8'><style>"
            + _CSS
            + "</style></head><body>"
            + body
            + "</body></html>"
        )
        with open(out_path, "w+b") as dest:
            status = pisa.CreatePDF(src=html, dest=dest)
        return not status.err
    except Exception as exc:
        logger.error("Markdown->PDF conversion failed: %s", exc)
        return False
