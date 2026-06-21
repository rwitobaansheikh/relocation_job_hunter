"""Render CVs and cover letters as Word .docx matching the LaTeX-style resume template."""

import logging
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

logger = logging.getLogger(__name__)

_FONT = "Times New Roman"
_RIGHT_TAB = Inches(7.15)

_DEFAULT_SECTION_TITLES = {
    "summary": "Professional Summary",
    "education": "Education",
    "experience": "Work Experience",
    "projects": "Technical Projects",
    "skills": "Technical Skills",
}


def role_abbrev(job_title: str) -> str:
    words = re.findall(r"[A-Za-z]+", job_title or "")
    if not words:
        return "Role"
    if len(words) == 1:
        return words[0][:6]
    return "".join(word[0].upper() for word in words[:4])


def document_filename(full_name: str, job_title: str, label: str) -> str:
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


def cv_layout_prompt_reference() -> str:
    """Layout spec for the LLM — mirrors uploads/profile_*_cv.pdf and resume.html."""
    return """
VISUAL LAYOUT (the Word renderer reproduces this exactly — structure JSON to match):

HEADER (centred):
- Line 1: candidate full name (large, bold).
- Line 2: phone | email | linkedin | github — pipe-separated, no "https://", no location on this line.

SECTION ORDER (always use this order in the "sections" array):
1. summary — title "Professional Summary"
2. education — title "Education"
3. experience — title "Work Experience"
4. projects — title "Technical Projects"
5. skills — title "Technical Skills" (always last)

SECTION HEADERS: mixed-case title with a horizontal rule underneath (e.g. "Work Experience", not ALL CAPS).

PROFESSIONAL SUMMARY: one justified paragraph (3-4 sentences), no bullets.

EDUCATION & WORK EXPERIENCE entries (each item):
- Row 1: heading = institution or "Company (Client)" (bold) … date on the right (e.g. "Jan 2025" or "April 2022 - Aug 2023").
- Row 2: subheading = degree or job title (italic) … location on the right (e.g. "Bath, UK").
- Then 1-3 bullet lines prefixed with an en-dash in the rendered doc (store bullet text without the dash).

TECHNICAL PROJECTS entries (each item):
- Row 1: heading = project name (bold) + "|" + tech stack (italic, comma-separated) … year on the right.
- 2-4 impact bullets (store without leading dash).
- links: array of {"label": "Source Code", "url": "..."} — labels like "Source Code", "Live Project", "Technical Report", joined with "|" in the footer line. Copy URLs only from ORIGINAL PROJECT LINKS.

TECHNICAL SKILLS: groups with short bold category labels and comma-separated values, e.g.
  AI/ML: PyTorch, TensorFlow, …
  Cloud/DevOps: AWS, GCP, Docker, …

DATE FORMAT: use plain hyphens in ranges (April 2022 - Aug 2023). Month abbreviations: Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec.

Do NOT use tables, text boxes, or multi-column section layout. Single reading order top-to-bottom.
"""


def _normalize_dates(text: str) -> str:
    return (text or "").replace("—", "-").replace("–", "-")


def _display_url(url: str) -> str:
    label = (url or "").strip()
    for prefix in ("https://", "http://", "www."):
        if label.lower().startswith(prefix):
            label = label[len(prefix):]
    return label.rstrip("/")


def _set_run_font(run, size_pt: float = 10, bold: bool = False, italic: bool = False) -> None:
    run.font.name = _FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), _FONT)
    run.font.size = Pt(size_pt)
    run.bold = bold
    run.italic = italic


def _add_bottom_border(paragraph) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "000000")
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def _configure_page(doc: Document) -> None:
    for section in doc.sections:
        section.left_margin = Inches(0.55)
        section.right_margin = Inches(0.55)
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.5)


def _add_two_column_line(
    doc: Document,
    left: str,
    right: str = "",
    left_bold: bool = False,
    left_italic: bool = False,
    right_italic: bool = True,
    size_pt: float = 10,
    space_after: float = 0,
) -> None:
    paragraph = doc.add_paragraph()
    fmt = paragraph.paragraph_format
    fmt.tab_stops.add_tab_stop(_RIGHT_TAB, WD_TAB_ALIGNMENT.RIGHT)
    if space_after:
        fmt.space_after = Pt(space_after)

    left_run = paragraph.add_run(left or "")
    _set_run_font(left_run, size_pt=size_pt, bold=left_bold, italic=left_italic)

    if right:
        paragraph.add_run("\t")
        right_run = paragraph.add_run(right)
        _set_run_font(right_run, size_pt=size_pt, italic=right_italic)


def _add_section_heading(doc: Document, title: str) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(7)
    paragraph.paragraph_format.space_after = Pt(3)
    run = paragraph.add_run(title)
    _set_run_font(run, size_pt=12.5, bold=False)
    _add_bottom_border(paragraph)


def _add_dash_bullet(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(1)
    paragraph.paragraph_format.left_indent = Inches(0.15)
    run = paragraph.add_run(f"–{text.strip()}")
    _set_run_font(run, size_pt=10)


def _add_hyperlink(paragraph, text: str, url: str) -> None:
    if not url:
        paragraph.add_run(text)
        return
    part = paragraph.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    new_run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")
    colour = OxmlElement("w:color")
    colour.set(qn("w:val"), "0563C1")
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    r_pr.append(colour)
    r_pr.append(underline)
    new_run.append(r_pr)
    text_elem = OxmlElement("w:t")
    text_elem.text = text
    new_run.append(text_elem)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def _plain_paragraphs_from_text(doc: Document, text: str) -> None:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    if not blocks and (text or "").strip():
        blocks = [line.strip() for line in text.splitlines() if line.strip()]
    for block in blocks:
        paragraph = doc.add_paragraph(block)
        for run in paragraph.runs:
            _set_run_font(run)


def render_resume_docx(data: dict, out_path: str) -> bool:
    """Render structured resume JSON to Word — matches resume.html / profile CV layout."""
    try:
        doc = Document()
        _configure_page(doc)

        name = (data.get("name") or "").strip()
        if name:
            name_p = doc.add_paragraph()
            name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            name_run = name_p.add_run(name)
            _set_run_font(name_run, size_pt=22, bold=True)

        contact = data.get("contact") or {}
        contact_bits: list[str] = []
        for key in ("phone", "email", "linkedin", "github"):
            raw = (contact.get(key) or "").strip()
            if not raw:
                continue
            if key in ("linkedin", "github"):
                contact_bits.append(_display_url(raw))
            else:
                contact_bits.append(raw)
        if contact_bits:
            contact_p = doc.add_paragraph("|".join(contact_bits))
            contact_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            contact_p.paragraph_format.space_after = Pt(4)
            for run in contact_p.runs:
                _set_run_font(run, size_pt=9.5)

        for section in data.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_type = section.get("type") or ""
            title = (section.get("title") or "").strip() or _DEFAULT_SECTION_TITLES.get(
                section_type, section_type
            )
            _add_section_heading(doc, title)

            if section_type == "summary":
                text = (section.get("text") or "").strip()
                if text:
                    summary_p = doc.add_paragraph(text)
                    summary_p.paragraph_format.space_after = Pt(2)
                    for run in summary_p.runs:
                        _set_run_font(run)

            elif section_type == "skills":
                for group in section.get("groups") or []:
                    if not isinstance(group, dict):
                        continue
                    label = (group.get("label") or "").strip()
                    value = (group.get("value") or "").strip()
                    if not label and not value:
                        continue
                    line_p = doc.add_paragraph()
                    line_p.paragraph_format.space_after = Pt(1)
                    if label:
                        label_run = line_p.add_run(f"{label}: ")
                        _set_run_font(label_run, bold=True)
                    if value:
                        value_run = line_p.add_run(value)
                        _set_run_font(value_run)

            elif section_type in ("experience", "education"):
                for item in section.get("items") or []:
                    if not isinstance(item, dict):
                        continue
                    heading = (item.get("heading") or "").strip()
                    subheading = (item.get("subheading") or "").strip()
                    location = (item.get("location") or "").strip()
                    date = _normalize_dates(item.get("date") or "").strip()

                    if heading or date:
                        _add_two_column_line(
                            doc,
                            heading,
                            date,
                            left_bold=True,
                            right_italic=True,
                            space_after=0,
                        )
                    if subheading or location:
                        _add_two_column_line(
                            doc,
                            subheading,
                            location,
                            left_italic=True,
                            right_italic=True,
                            size_pt=9.5,
                            space_after=2,
                        )
                    for bullet in item.get("bullets") or []:
                        if bullet:
                            _add_dash_bullet(doc, str(bullet))

            elif section_type == "projects":
                for item in section.get("items") or []:
                    if not isinstance(item, dict):
                        continue
                    project_name = (item.get("heading") or "").strip()
                    tech = (item.get("tech") or "").strip()
                    date = _normalize_dates(item.get("date") or "").strip()

                    project_p = doc.add_paragraph()
                    project_p.paragraph_format.tab_stops.add_tab_stop(
                        _RIGHT_TAB, WD_TAB_ALIGNMENT.RIGHT
                    )
                    project_p.paragraph_format.space_after = Pt(1)
                    if project_name:
                        name_run = project_p.add_run(project_name)
                        _set_run_font(name_run, bold=True)
                    if tech:
                        tech_run = project_p.add_run(f"|{tech}")
                        _set_run_font(tech_run, italic=True)
                    if date:
                        project_p.add_run("\t")
                        date_run = project_p.add_run(date)
                        _set_run_font(date_run, italic=True, size_pt=9.5)

                    for bullet in item.get("bullets") or []:
                        if bullet:
                            _add_dash_bullet(doc, str(bullet))

                    links = item.get("links") or []
                    if links:
                        links_p = doc.add_paragraph()
                        links_p.paragraph_format.space_after = Pt(4)
                        for idx, link in enumerate(links):
                            if not isinstance(link, dict):
                                continue
                            label = (link.get("label") or "Link").strip()
                            url = (link.get("url") or "").strip()
                            if idx > 0:
                                sep_run = links_p.add_run("|")
                                _set_run_font(sep_run, size_pt=9.5)
                            _add_hyperlink(links_p, label, url)

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(out_path)
        return True
    except Exception as exc:
        logger.error("Resume DOCX render failed: %s", exc)
        return False


def render_cover_letter_docx(name: str, contact: dict, body_text: str, out_path: str) -> bool:
    try:
        doc = Document()
        _configure_page(doc)

        if name:
            header = doc.add_paragraph()
            header_run = header.add_run(name)
            _set_run_font(header_run, size_pt=14, bold=True)

        contact_bits: list[str] = []
        for key in ("email", "phone", "linkedin", "location"):
            value = (contact.get(key) or "").strip()
            if value:
                contact_bits.append(value)
        if contact_bits:
            contact_p = doc.add_paragraph(" | ".join(contact_bits))
            for run in contact_p.runs:
                _set_run_font(run)

        cleaned = re.sub(
            r"^```[a-zA-Z]*\s*\n(.*?)\n?```$",
            r"\1",
            (body_text or "").strip(),
            flags=re.DOTALL,
        )
        _plain_paragraphs_from_text(doc, cleaned.strip())

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(out_path)
        return True
    except Exception as exc:
        logger.error("Cover letter DOCX render failed: %s", exc)
        return False
