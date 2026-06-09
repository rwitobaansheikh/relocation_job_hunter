"""Extract hyperlinks from uploaded CVs and restore them on tailored resumes.

PDF text extraction drops clickable URLs (only labels like "Source Code" survive).
We read PDF link annotations (and URLs embedded in text) and map them back to
each project by reading order + fuzzy project-name matching.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_URL_IN_TEXT_RE = re.compile(
    r"https?://[^\s<>\[\]()\"'|,]+|(?:mailto:)[^\s|]+|"
    r"(?:www\.)?(?:github\.com|linkedin\.com)/[^\s|]+",
    re.IGNORECASE,
)
_GITHUB_PROFILE_RE = re.compile(r"github\.com/([^/\s|]+)/?$", re.IGNORECASE)
_LINK_LABEL_RE = re.compile(
    r"(source\s*code|technical\s*report|live\s*project|demo|portfolio|paper|website)",
    re.IGNORECASE,
)


def _normalize_url(url: str) -> str:
    cleaned = (url or "").strip().rstrip(".,;)")
    if not cleaned:
        return ""
    if cleaned.lower().startswith("mailto:"):
        return cleaned
    if not cleaned.lower().startswith(("http://", "https://")):
        return f"https://{cleaned.lstrip('/')}"
    return cleaned


def _normalize_project_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _project_tokens(name: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", (name or "").lower())}


def _match_score(heading: str, project_name: str) -> float:
    a = _normalize_project_key(heading)
    b = _normalize_project_key(project_name)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    ta, tb = _project_tokens(heading), _project_tokens(project_name)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _infer_link_label(url: str) -> str:
    lower = url.lower()
    if "github.com" in lower:
        return "Source Code"
    if any(x in lower for x in (".pdf", "report", "arxiv")):
        return "Technical Report"
    return "Live Project"


def _clean_label(raw: str) -> str:
    label = re.sub(r"^[–\-•]\s*", "", (raw or "").strip())
    if not label:
        return ""
    if label.lower() == "source code":
        return "Source Code"
    if label.lower() == "technical report":
        return "Technical Report"
    if label.lower() == "live project":
        return "Live Project"
    return label


def extract_urls_from_text(text: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for match in _URL_IN_TEXT_RE.finditer(text or ""):
        url = _normalize_url(match.group(0))
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def extract_pdf_hyperlinks(file_path: str) -> list[dict[str, Any]]:
    """Return hyperlink annotations sorted top-to-bottom per page."""
    path = Path(file_path)
    if not path.exists() or path.suffix.lower() != ".pdf":
        return []

    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        return []

    links: list[dict[str, Any]] = []
    try:
        reader = PdfReader(str(path))
        for page_idx, page in enumerate(reader.pages):
            annots = page.get("/Annots")
            if not annots:
                continue
            for annot in annots:
                obj = annot.get_object()
                if obj.get("/Subtype") != "/Link":
                    continue
                action = obj.get("/A") or {}
                uri = action.get("/URI")
                if not uri:
                    continue
                rect = obj.get("/Rect") or [0, 0, 0, 0]
                top = float(rect[3]) if len(rect) > 3 else 0.0
                links.append(
                    {
                        "url": _normalize_url(str(uri)),
                        "page": page_idx,
                        "top": top,
                    }
                )
    except Exception as exc:
        logger.warning("Failed to read PDF hyperlinks from %s: %s", file_path, exc)
        return []

    links.sort(key=lambda item: (item["page"], -item["top"]))
    return links


def _group_pdf_links_by_row(
    links: list[dict[str, Any]], y_tolerance: float = 18.0
) -> list[list[str]]:
    """Cluster PDF links that sit on the same visual row (one project block)."""
    project_links = [
        link
        for link in links
        if not (link["url"].lower().startswith("mailto:") or "linkedin.com" in link["url"].lower())
        and not _GITHUB_PROFILE_RE.search(link["url"])
    ]
    groups: list[list[str]] = []
    current: list[str] = []
    last_top: float | None = None
    last_page: int | None = None

    for link in project_links:
        page = link["page"]
        top = link["top"]
        if (
            current
            and last_page == page
            and last_top is not None
            and abs(top - last_top) > y_tolerance
        ):
            groups.append(current)
            current = []
        current.append(link["url"])
        last_top = top
        last_page = page

    if current:
        groups.append(current)
    return groups


def parse_cv_projects(cv_text: str) -> list[dict[str, Any]]:
    """Parse project titles and link labels from extracted CV text."""
    projects: list[dict[str, Any]] = []
    in_projects = False
    current: dict[str, Any] | None = None

    for raw_line in (cv_text or "").splitlines():
        line = raw_line.strip()
        lower = line.lower()

        if "technical projects" in lower and len(line) < 40:
            in_projects = True
            continue
        if in_projects and lower.startswith("technical skills"):
            break
        if not in_projects or not line:
            continue

        is_bullet = line.startswith("–") or line.startswith("-")
        has_link_label = bool(_LINK_LABEL_RE.search(line))

        if not is_bullet and "|" in line and not has_link_label:
            if current:
                projects.append(current)
            title = line.split("|", 1)[0].strip()
            current = {"name": title, "link_labels": []}
            continue

        if current and has_link_label:
            chunk = line.lstrip("–-• ").strip()
            labels = [_clean_label(part) for part in chunk.split("|")]
            current["link_labels"] = [label for label in labels if label]

    if current:
        projects.append(current)
    return projects


def build_project_link_map(file_path: str, cv_text: str) -> list[dict[str, Any]]:
    """Build ordered project link records from the original CV file + text."""
    projects = parse_cv_projects(cv_text)
    pdf_rows = _group_pdf_links_by_row(extract_pdf_hyperlinks(file_path))
    text_urls = extract_urls_from_text(cv_text)

    # Drop contact/header URLs from plain-text fallback list.
    non_contact_text_urls = [
        url
        for url in text_urls
        if "linkedin.com" not in url.lower()
        and not _GITHUB_PROFILE_RE.search(url)
        and not url.lower().startswith("mailto:")
    ]

    records: list[dict[str, Any]] = []
    for idx, project in enumerate(projects):
        urls = pdf_rows[idx] if idx < len(pdf_rows) else []
        if not urls and non_contact_text_urls:
            # DOCX / plain-text CVs: best-effort positional pairing.
            per_project = max(1, len(non_contact_text_urls) // max(1, len(projects)))
            start = idx * per_project
            urls = non_contact_text_urls[start : start + per_project]

        labels = project.get("link_labels") or []
        links: list[dict[str, str]] = []
        for j, url in enumerate(urls):
            label = labels[j] if j < len(labels) else _infer_link_label(url)
            links.append({"label": label, "url": url})

        if links:
            records.append({"name": project["name"], "links": links})

    return records


def extract_contact_links(file_path: str, cv_text: str) -> dict[str, str]:
    """Pull LinkedIn/GitHub profile URLs from the original CV."""
    contact: dict[str, str] = {}
    for url in extract_urls_from_text(cv_text) + [
        link["url"] for link in extract_pdf_hyperlinks(file_path)
    ]:
        lower = url.lower()
        if "linkedin.com" in lower and "linkedin" not in contact:
            contact["linkedin"] = url
        elif _GITHUB_PROFILE_RE.search(lower) and "github" not in contact:
            contact["github"] = url
    return contact


def load_stored_project_links(profile) -> list[dict[str, Any]]:
    raw = getattr(profile, "cv_links_json", "") or ""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def get_project_links_for_profile(profile) -> list[dict[str, Any]]:
    stored = load_stored_project_links(profile)
    if stored:
        return stored
    cv_path = getattr(profile, "cv_path", "") or ""
    cv_text = getattr(profile, "cv_text", "") or ""
    if not cv_path and not cv_text:
        return []
    return build_project_link_map(cv_path, cv_text)


def find_links_for_heading(heading: str, records: list[dict[str, Any]]) -> list[dict[str, str]] | None:
    if not heading or not records:
        return None
    best_score = 0.0
    best_links: list[dict[str, str]] | None = None
    for record in records:
        score = _match_score(heading, record.get("name", ""))
        if score > best_score:
            best_score = score
            best_links = record.get("links")
    return best_links if best_score >= 0.35 else None


def apply_original_links_to_resume(data: dict, records: list[dict[str, Any]]) -> dict:
    """Replace AI-hallucinated project URLs with links from the uploaded CV."""
    if not records:
        return data

    used: set[str] = set()
    for section in data.get("sections") or []:
        if not isinstance(section, dict) or section.get("type") != "projects":
            continue
        for item in section.get("items") or []:
            if not isinstance(item, dict):
                continue
            heading = item.get("heading") or ""
            matched = find_links_for_heading(heading, records)
            if matched:
                item["links"] = matched
                used.add(_normalize_project_key(heading))

    # If the model renamed projects, fill any unmatched items by leftover originals.
    unmatched_records = [
        record
        for record in records
        if _normalize_project_key(record.get("name", "")) not in used
    ]
    if not unmatched_records:
        return data

    pool_idx = 0
    for section in data.get("sections") or []:
        if section.get("type") != "projects":
            continue
        for item in section.get("items") or []:
            if item.get("links"):
                continue
            if pool_idx < len(unmatched_records):
                item["links"] = unmatched_records[pool_idx]["links"]
                pool_idx += 1

    return data


def serialize_project_links(records: list[dict[str, Any]]) -> str:
    return json.dumps(records, ensure_ascii=False)


def format_links_for_prompt(records: list[dict[str, Any]]) -> str:
    if not records:
        return ""
    lines = []
    for record in records:
        name = record.get("name", "")
        links = record.get("links") or []
        if not links:
            continue
        parts = [f"{link['label']}: {link['url']}" for link in links]
        lines.append(f"- {name}: " + " | ".join(parts))
    return "\n".join(lines)
