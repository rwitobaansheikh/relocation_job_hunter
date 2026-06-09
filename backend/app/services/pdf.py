"""HTML/Markdown -> PDF conversion for generated CVs and cover letters.

Uses WeasyPrint, which supports real CSS (floats, web fonts, precise page
geometry) so the rendered documents match the designed template rather than
collapsing into a "wall of text". Imports are soft so the app keeps running
(falling back to plain-text output) even if the optional native stack isn't
installed yet.
"""

import logging
import re

logger = logging.getLogger(__name__)

try:
    import markdown as _markdown
    from weasyprint import HTML as _WeasyHTML

    _PDF_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency / missing native libs
    _PDF_AVAILABLE = False


def _strip_code_fences(text: str) -> str:
    """Safety net: drop a surrounding ```...``` fence so the document doesn't
    render as one monospace code block."""
    stripped = (text or "").strip()
    fence = re.match(r"^```[a-zA-Z]*\s*\n(.*?)\n?```$", stripped, flags=re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return stripped


# Minimal styling for the markdown fallback path (used when we render the
# originally uploaded text rather than a structured document).
_MARKDOWN_CSS = """
@page { size: A4; margin: 1.6cm; }
body { font-family: "DejaVu Serif", "Times New Roman", Georgia, serif; font-size: 10.5pt; line-height: 1.4; color: #111; }
h1 { text-align: center; font-size: 20pt; margin: 0 0 2pt 0; }
h1 + p { text-align: center; color: #444; margin: 0 0 8pt 0; font-size: 10pt; }
h2 { font-size: 13pt; border-bottom: 1px solid #999; margin: 12pt 0 4pt 0; padding-bottom: 2pt; }
h3 { font-size: 11.5pt; margin: 8pt 0 2pt 0; }
ul { margin: 2pt 0 6pt 16pt; padding: 0; }
li { margin: 1pt 0; }
p { margin: 4pt 0; }
a { color: #1a4f8b; text-decoration: none; }
strong { color: #000; }
"""


def pdf_supported() -> bool:
    return _PDF_AVAILABLE


def html_to_pdf(html: str, out_path: str) -> bool:
    """Render a complete HTML document string to a PDF file. Returns True on
    success. This is the primary path for structured CVs/cover letters."""
    if not _PDF_AVAILABLE:
        return False
    try:
        _WeasyHTML(string=html).write_pdf(out_path)
        return True
    except Exception as exc:
        logger.error("HTML->PDF conversion failed: %s", exc)
        return False


def markdown_to_pdf(markdown_text: str, out_path: str) -> bool:
    """Render markdown text to a PDF file. Returns True on success. Used as a
    fallback when we only have free-form text (e.g. an uploaded original)."""
    if not _PDF_AVAILABLE:
        return False
    try:
        cleaned = _strip_code_fences(markdown_text)
        body = _markdown.markdown(cleaned, extensions=["extra", "sane_lists", "nl2br"])
        html = (
            "<html><head><meta charset='utf-8'><style>"
            + _MARKDOWN_CSS
            + "</style></head><body>"
            + body
            + "</body></html>"
        )
        return html_to_pdf(html, out_path)
    except Exception as exc:
        logger.error("Markdown->PDF conversion failed: %s", exc)
        return False
