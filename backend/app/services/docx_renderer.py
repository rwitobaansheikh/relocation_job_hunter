"""Render ATS-friendly CVs and cover letters as Microsoft Word .docx files."""

import logging
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

logger = logging.getLogger(__name__)

_SECTION_TITLES = {
    "summary": "PROFESSIONAL SUMMARY",
    "skills": "KEY SKILLS",
    "experience": "PROFESSIONAL EXPERIENCE",
    "projects": "PROJECTS",
    "education": "EDUCATION",
}


def role_abbrev(job_title: str) -> str:
    words = re.findall(r"[A-Za-z]+", job_title or "")
    if not words:
        return "Role"
    if len(words) == 1:
        return words[0][:6]
    return "".join(word[0].upper() for word in words[:4])


def document_filename(full_name: str, job_title: str, label: str) -> str:
    """e.g. Baan-Sheikh-DE-CV.docx"""
    parts = [p for p in re.split(r"\s+", (full_name or "").strip()) if p]
    first = parts[0] if parts else "Candidate"
    last = parts[-1] if len(parts) > 1 else ""
    abbrev = role_abbrev(job_title)
    if last and last != first:
        base = f"{first}-{last}-{abbrev}-{label}"
    else:
        base = f"{first}-{abbrev}-{label}"
    cleaned = re.sub(r"[^\w\-.]", "", base.replace(" ", "-"))
    return f"{cleaned}.docx"


def _normalize_dates(text: str) -> str:
    return (text or "").replace("—", "-").replace("–", "-")


def _add_section_heading(doc: Document, title: str) -> None:
    paragraph = doc.add_paragraph()
    run = paragraph.add_run(title.upper())
    run.bold = True
    run.font.size = Pt(11)
    paragraph.paragraph_format.space_before = Pt(8)
    paragraph.paragraph_format.space_after = Pt(4)


def _plain_paragraphs_from_text(doc: Document, text: str) -> None:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    if not blocks and (text or "").strip():
        blocks = [line.strip() for line in text.splitlines() if line.strip()]
    for block in blocks:
        doc.add_paragraph(block)


def render_resume_docx(data: dict, out_path: str) -> bool:
    """Single-column ATS layout — no tables, no multi-column headers."""
    try:
        doc = Document()
        for section in doc.sections:
            section.left_margin = Inches(0.75)
            section.right_margin = Inches(0.75)
            section.top_margin = Inches(0.75)
            section.bottom_margin = Inches(0.75)

        name = (data.get("name") or "").strip()
        if name:
            name_p = doc.add_paragraph()
            name_run = name_p.add_run(name)
            name_run.bold = True
            name_run.font.size = Pt(14)
            name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        contact = data.get("contact") or {}
        contact_bits: list[str] = []
        for key in ("email", "phone", "linkedin", "github", "location"):
            value = (contact.get(key) or "").strip()
            if value:
                contact_bits.append(value)
        if contact_bits:
            contact_p = doc.add_paragraph(" | ".join(contact_bits))
            contact_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            contact_p.paragraph_format.space_after = Pt(6)

        for section in data.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_type = section.get("type") or ""
            heading = _SECTION_TITLES.get(section_type) or (section.get("title") or section_type).upper()
            _add_section_heading(doc, heading)

            if section_type == "summary":
                text = (section.get("text") or "").strip()
                if text:
                    doc.add_paragraph(text)

            elif section_type == "skills":
                for group in section.get("groups") or []:
                    if not isinstance(group, dict):
                        continue
                    label = (group.get("label") or "").strip()
                    value = (group.get("value") or "").strip()
                    line = f"{label}: {value}" if label else value
                    if line:
                        doc.add_paragraph(line)

            elif section_type in ("experience", "education"):
                for item in section.get("items") or []:
                    if not isinstance(item, dict):
                        continue
                    title_line = (item.get("subheading") or item.get("heading") or "").strip()
                    if title_line:
                        title_p = doc.add_paragraph()
                        title_run = title_p.add_run(title_line)
                        title_run.bold = True
                    organisation = (item.get("heading") or "").strip()
                    location = (item.get("location") or "").strip()
                    date = _normalize_dates(item.get("date") or "").strip()
                    meta_parts = [x for x in [organisation, location] if x]
                    meta = ", ".join(meta_parts)
                    if date:
                        meta = f"{meta} - {date}" if meta else date
                    if meta:
                        doc.add_paragraph(meta)
                    for bullet in item.get("bullets") or []:
                        if bullet:
                            doc.add_paragraph(str(bullet), style="List Bullet")

            elif section_type == "projects":
                for item in section.get("items") or []:
                    if not isinstance(item, dict):
                        continue
                    project_name = (item.get("heading") or item.get("subheading") or "Project").strip()
                    title_p = doc.add_paragraph()
                    title_run = title_p.add_run(project_name)
                    title_run.bold = True
                    date = _normalize_dates(item.get("date") or "").strip()
                    doc.add_paragraph(f"Independent project, {date}" if date else "Independent project")
                    tech = (item.get("tech") or "").strip()
                    if tech:
                        doc.add_paragraph(f"Technologies: {tech}")
                    for bullet in item.get("bullets") or []:
                        if bullet:
                            doc.add_paragraph(str(bullet), style="List Bullet")

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(out_path)
        return True
    except Exception as exc:
        logger.error("Resume DOCX render failed: %s", exc)
        return False


def render_cover_letter_docx(name: str, contact: dict, body_text: str, out_path: str) -> bool:
    try:
        doc = Document()
        for section in doc.sections:
            section.left_margin = Inches(0.75)
            section.right_margin = Inches(0.75)

        if name:
            header = doc.add_paragraph()
            header_run = header.add_run(name)
            header_run.bold = True

        contact_bits: list[str] = []
        for key in ("email", "phone", "linkedin", "location"):
            value = (contact.get(key) or "").strip()
            if value:
                contact_bits.append(value)
        if contact_bits:
            doc.add_paragraph(" | ".join(contact_bits))

        cleaned = re.sub(r"^```[a-zA-Z]*\s*\n(.*?)\n?```$", r"\1", (body_text or "").strip(), flags=re.DOTALL)
        _plain_paragraphs_from_text(doc, cleaned.strip())

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(out_path)
        return True
    except Exception as exc:
        logger.error("Cover letter DOCX render failed: %s", exc)
        return False
