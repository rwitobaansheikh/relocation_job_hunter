"""Render structured CV / cover letter data into polished PDFs via WeasyPrint.

The CV is produced as structured JSON by the AI (see document_generator) and
rendered through a Jinja HTML template whose CSS emulates the provided LaTeX
resume layout (centered small-caps name, ruled section headers, left/right
entry rows, tight one-page geometry).
"""

import logging
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.pdf import html_to_pdf, pdf_supported

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def _display_url(url: str) -> str:
    """Strip scheme/www for a compact, human-friendly link label."""
    label = (url or "").strip()
    for prefix in ("https://", "http://", "www."):
        if label.lower().startswith(prefix):
            label = label[len(prefix):]
    return label.rstrip("/")


def _contact_links(contact: dict) -> list[str]:
    """Build the safe HTML fragments for the centered contact line."""
    links: list[str] = []
    email = (contact.get("email") or "").strip()
    if email:
        links.append(f'<a href="mailto:{email}">{email}</a>')
    linkedin = (contact.get("linkedin") or "").strip()
    if linkedin:
        url = linkedin if linkedin.startswith("http") else f"https://{linkedin}"
        links.append(f'<a href="{url}">{_display_url(linkedin)}</a>')
    github = (contact.get("github") or "").strip()
    if github:
        url = github if github.startswith("http") else f"https://{github}"
        links.append(f'<a href="{url}">{_display_url(github)}</a>')
    location = (contact.get("location") or "").strip()
    if location:
        links.append(location)
    return links


def render_resume(data: dict, out_path: str) -> bool:
    """Render a structured resume dict to a PDF. Returns True on success."""
    if not pdf_supported():
        return False
    try:
        contact = data.get("contact") or {}
        html = _env().get_template("resume.html").render(
            name=data.get("name") or "",
            contact=contact,
            contact_links=_contact_links(contact),
            sections=data.get("sections") or [],
        )
        return html_to_pdf(html, out_path)
    except Exception as exc:
        logger.error("Resume render failed: %s", exc)
        return False


def render_cover_letter(name: str, contact: dict, body_html: str, out_path: str) -> bool:
    """Render a cover letter (header + HTML body) to a PDF. Returns True on success."""
    if not pdf_supported():
        return False
    try:
        html = _env().get_template("cover_letter.html").render(
            name=name or "",
            contact=contact or {},
            contact_links=_contact_links(contact or {}),
            body_html=body_html or "",
        )
        return html_to_pdf(html, out_path)
    except Exception as exc:
        logger.error("Cover letter render failed: %s", exc)
        return False
