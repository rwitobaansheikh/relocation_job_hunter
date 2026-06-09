"""Generate tailored CVs and cover letters using the configured LLM (Ollama/Gemini)."""

import asyncio
import json
import logging
import re
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import ApplicationStatus, JobApplication, UserProfile
from app.services.cv_link_extractor import (
    apply_original_links_to_resume,
    build_project_link_map,
    extract_contact_links,
    format_links_for_prompt,
    get_project_links_for_profile,
)
from app.services.llm import llm_available, llm_generate, resolve_gemini_api_key
from app.services.job_analyzer import JobAnalyzer
from app.services.pdf import markdown_to_pdf
from app.services.resume_renderer import render_cover_letter, render_resume

try:
    import markdown as _markdown
except Exception:  # pragma: no cover - optional dependency
    _markdown = None

logger = logging.getLogger(__name__)

_ALLOWED_SECTION_TYPES = {"summary", "experience", "education", "projects", "skills"}
_GEMINI_PACE_SECONDS = 2.5
_BATCH_PACE_SECONDS = 5.0
_AI_FAILURE_MSG = (
    "AI tailoring failed — the local LLM may be offline or overloaded. "
    "Ensure Ollama is running and the configured model is pulled, then retry."
)


def _safe_filename(name: str) -> str:
    cleaned = "".join(c for c in (name or "") if c.isalnum() or c in " -_").strip()
    return cleaned or "document"


def _strip_code_fences(text: str) -> str:
    """Remove a surrounding ```markdown ... ``` (or plain ```) fence that LLMs
    often wrap their output in. Left in place, the fence makes the whole document
    render as one monospace code block (a "wall of text") in the PDF."""
    if not text:
        return ""
    stripped = text.strip()
    fence = re.match(r"^```[a-zA-Z]*\s*\n(.*?)\n?```$", stripped, flags=re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return stripped


def _looks_usable(markdown_text: str) -> bool:
    """Heuristic: a real CV/cover letter has a meaningful amount of prose. Strip
    markdown punctuation and require enough actual words so we don't ship a near
    empty document (e.g. just a name + one line, as in a truncated AI response)."""
    if not markdown_text:
        return False
    plain = re.sub(r"[#*_>`\-\|\[\]()]", " ", markdown_text)
    words = [w for w in plain.split() if any(ch.isalnum() for ch in w)]
    return len(words) >= 40


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of an LLM response (tolerates code fences
    and surrounding prose)."""
    if not text:
        return None
    cleaned = _strip_code_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        result = json.loads(cleaned[start : end + 1])
        return result if isinstance(result, dict) else None
    except (ValueError, TypeError):
        return None


def _resume_word_count(data: dict) -> int:
    """Count meaningful words across a structured resume so we can reject a near
    empty AI result and fall back to the uploaded CV."""
    chunks: list[str] = []
    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        if section.get("text"):
            chunks.append(str(section["text"]))
        for item in section.get("items") or []:
            if not isinstance(item, dict):
                continue
            for key in ("heading", "subheading", "tech"):
                if item.get(key):
                    chunks.append(str(item[key]))
            chunks.extend(str(b) for b in (item.get("bullets") or []))
        for group in section.get("groups") or []:
            if isinstance(group, dict) and group.get("value"):
                chunks.append(str(group["value"]))
    words = [w for w in " ".join(chunks).split() if any(ch.isalnum() for ch in w)]
    return len(words)


def _resume_usable(data: dict | None) -> bool:
    return bool(data) and _resume_word_count(data) >= 40


def _markdown_to_html(text: str) -> str:
    cleaned = _strip_code_fences(text)
    if _markdown is not None:
        try:
            return _markdown.markdown(cleaned, extensions=["extra", "sane_lists", "nl2br"])
        except Exception:  # pragma: no cover - defensive
            pass
    # Minimal fallback: paragraphs split on blank lines.
    paragraphs = [p.strip().replace("\n", "<br>") for p in cleaned.split("\n\n") if p.strip()]
    return "".join(f"<p>{p}</p>" for p in paragraphs)


class DocumentGenerator:
    def __init__(self) -> None:
        self.analyzer = JobAnalyzer()

    async def tailor_for_application(self, db: Session, application_id: int) -> JobApplication:
        application = db.query(JobApplication).filter(JobApplication.id == application_id).first()
        if not application:
            raise ValueError(f"Application {application_id} not found")

        profile = application.user_profile
        job = application.job
        if not profile or not job:
            raise ValueError("Application missing profile or job")

        out_dir = Path(settings.generated_dir) / f"app_{application_id}"
        out_dir.mkdir(parents=True, exist_ok=True)

        cv_text = profile.cv_text or ""
        cover_base = profile.baseline_cover_letter_text or ""

        if not llm_available(profile):
            provider = (settings.llm_provider or "ollama").strip().lower()
            if provider == "gemini":
                raise ValueError(
                    "Gemini API key not configured. Set GEMINI_API_KEY in backend/.env "
                    "or add your own key in Settings."
                )
            raise ValueError(
                "Local LLM not configured. Install Ollama, run "
                f"'ollama pull {settings.ollama_model}', and ensure it is reachable at "
                f"{settings.ollama_base_url}."
            )
        api_key = resolve_gemini_api_key(profile)
        if not cv_text.strip():
            raise ValueError(
                "No CV text on your profile. Re-upload your CV so we can tailor it."
            )

        # Generate tailored documents first (paced to avoid overloading the LLM).
        cv_data = await self._generate_cv_data(profile, job, cv_text, gaps=None, api_key=api_key)
        await asyncio.sleep(_GEMINI_PACE_SECONDS)
        tailored_cl = _strip_code_fences(
            await self._generate_cover_letter(profile, job, cover_base, api_key=api_key)
        )

        name = _safe_filename(profile.full_name)
        contact = self._contact(profile)

        if not _resume_usable(cv_data):
            logger.warning(
                "Tailored CV for application %s unusable (AI empty or truncated).",
                application_id,
            )
            raise ValueError(_AI_FAILURE_MSG)

        cv_data = self._apply_profile_identity(cv_data, profile, cv_text)
        cv_pdf = out_dir / f"{name} - CV.pdf"
        if not render_resume(cv_data, str(cv_pdf)):
            raise ValueError("Failed to render the tailored CV to PDF. Please retry.")

        if not _looks_usable(tailored_cl):
            logger.warning(
                "Tailored cover letter for application %s unusable (AI empty or truncated).",
                application_id,
            )
            raise ValueError(_AI_FAILURE_MSG)

        cl_pdf = out_dir / f"{name} - Cover Letter.pdf"
        body_html = _markdown_to_html(tailored_cl)
        if render_cover_letter(profile.full_name, contact, body_html, str(cl_pdf)):
            cl_path = str(cl_pdf)
        else:
            cl_path = self._write_document(tailored_cl, out_dir, f"{name} - Cover Letter")
            if not cl_path:
                raise ValueError("Failed to render the tailored cover letter. Please retry.")

        # Optional match analysis (does not block tailoring success).
        analysis = None
        try:
            await asyncio.sleep(_GEMINI_PACE_SECONDS)
            analysis = await self.analyzer.analyze(
                job.company,
                job.description or "",
                cv_text,
                api_key=api_key,
                profile=profile,
            )
        except Exception as exc:
            logger.warning("Match analysis skipped for application %s: %s", application_id, exc)

        application.tailored_cv_path = str(cv_pdf)
        application.tailored_cover_letter_path = cl_path
        if analysis:
            try:
                application.ai_match_score = int(analysis.get("match_score") or 0)
            except (TypeError, ValueError):
                application.ai_match_score = 0
            application.analysis_json = json.dumps(analysis)
        application.status = ApplicationStatus.TAILORED.value
        db.commit()
        db.refresh(application)
        return application

    async def tailor_batch(self, db: Session, application_ids: list[int]) -> list[JobApplication]:
        results: list[JobApplication] = []
        errors: list[str] = []
        for idx, app_id in enumerate(application_ids):
            if idx > 0:
                await asyncio.sleep(_BATCH_PACE_SECONDS)
            try:
                app = await self.tailor_for_application(db, app_id)
                results.append(app)
            except Exception as exc:
                logger.error("Failed to tailor application %s: %s", app_id, exc)
                errors.append(str(exc))
        if not results and errors:
            raise ValueError(errors[0])
        return results

    def _write_document(self, markdown_text: str, out_dir, base_name: str) -> str:
        """Write the document as PDF, falling back to .txt if PDF deps are missing."""
        pdf_path = out_dir / f"{base_name}.pdf"
        if markdown_to_pdf(markdown_text, str(pdf_path)):
            return str(pdf_path)
        txt_path = out_dir / f"{base_name}.txt"
        txt_path.write_text(markdown_text, encoding="utf-8")
        return str(txt_path)

    def _fallback_document(
        self, original_text: str, original_path: str, out_dir, base_name: str
    ) -> str:
        """Copy/render an uploaded document into the per-application output dir.

        Never return the original upload path as a 'tailored' path — callers must
        only use this for explicit, non-AI fallbacks."""
        dest = out_dir / f"{base_name}.pdf"
        if original_path and Path(original_path).exists():
            shutil.copy2(original_path, dest)
            return str(dest)
        if original_text and original_text.strip():
            return self._write_document(original_text, out_dir, f"{base_name} (original)")
        return ""

    @staticmethod
    def _contact(profile: UserProfile) -> dict:
        return {
            "email": profile.email or "",
            "phone": profile.phone or "",
            "linkedin": profile.linkedin_url or "",
            "location": profile.location or "",
            "github": "",
        }

    def _apply_profile_identity(
        self, data: dict, profile: UserProfile, cv_text: str = ""
    ) -> dict:
        """Trust the profile for identity/contact details; restore original links."""
        data["name"] = profile.full_name or data.get("name") or ""
        ai_contact = data.get("contact") or {}
        contact = self._contact(profile)
        original_contact = extract_contact_links(profile.cv_path or "", cv_text)
        if not contact.get("github") and original_contact.get("github"):
            contact["github"] = original_contact["github"]
        elif not contact.get("github") and ai_contact.get("github"):
            contact["github"] = ai_contact.get("github")
        if not contact.get("linkedin") and original_contact.get("linkedin"):
            contact["linkedin"] = original_contact["linkedin"]
        elif not contact.get("linkedin") and ai_contact.get("linkedin"):
            contact["linkedin"] = ai_contact.get("linkedin")
        data["contact"] = contact

        data = apply_original_links_to_resume(data, get_project_links_for_profile(profile))

        # Keep only section types the template knows how to render.
        data["sections"] = [
            s
            for s in (data.get("sections") or [])
            if isinstance(s, dict) and s.get("type") in _ALLOWED_SECTION_TYPES
        ]
        return data

    async def _generate_cv_data(
        self, profile: UserProfile, job, cv_text: str, gaps=None, api_key: str | None = None
    ) -> dict | None:
        """Ask the LLM for a STRUCTURED resume (JSON) so we can render it through
        the designed template. Returns the parsed dict, or None on failure."""
        gaps_text = json.dumps(gaps) if gaps else "None provided"
        link_records = build_project_link_map(profile.cv_path or "", cv_text)
        links_prompt = format_links_for_prompt(link_records)

        schema = """{
  "name": "Full Name",
  "contact": {"phone": "", "email": "", "linkedin": "", "github": "", "location": ""},
  "sections": [
    {"type": "summary", "title": "Professional Summary", "text": "2-3 sentence tailored summary"},
    {"type": "skills", "title": "Technical Skills", "groups": [
      {"label": "Category", "value": "comma-separated skills"}
    ]},
    {"type": "experience", "title": "Work Experience", "items": [
      {"heading": "Company (Client)", "location": "City, Country", "subheading": "Job Title", "date": "Start -- End", "bullets": ["achievement with metrics"]}
    ]},
    {"type": "projects", "title": "Technical Projects", "items": [
      {"heading": "Project Name", "tech": "Tech, Stack", "date": "Year", "bullets": ["impact bullet"], "links": [{"label": "Source Code", "url": "https://..."}]}
    ]},
    {"type": "education", "title": "Education", "items": [
      {"heading": "Institution", "location": "City, Country", "subheading": "Degree (grade)", "date": "Year", "bullets": ["optional detail"]}
    ]}
  ]
}"""

        prompt = f"""You are an expert CV writer. Produce a tailored, truthful, ONE-PAGE CV as STRUCTURED JSON only.

Return ONLY a single JSON object matching this exact schema (no markdown, no code fences, no commentary):
{schema}

RULES:
- Output valid JSON only. Use straight quotes. No trailing commas.
- Allowed section types: "summary", "skills", "experience", "projects", "education".
- Order the "sections" array to best match the target job (put the most relevant sections first). Always include "summary" first.
- Be truthful: never fabricate experience, employers, or metrics not supported by the source CV.
- Tailor wording and emphasis to the job description; lead bullets with strong action verbs and quantified impact.
- Keep it concise enough to fit one page (typically 3-5 experience/project bullets each).
- Do NOT include placeholders or empty bracket tokens.
- For projects: include a "links" array. NEVER invent or guess URLs — copy ONLY from ORIGINAL PROJECT LINKS below. Use the exact label + url pairs provided.

ORIGINAL PROJECT LINKS (copy exactly; do not modify URLs):
{links_prompt or "(none found — omit links arrays)"}

SOURCE CV (extract real content from here):
{cv_text[:6000]}

CANDIDATE:
- Name: {profile.full_name}
- Email: {profile.email} | Phone: {profile.phone} | LinkedIn: {profile.linkedin_url} | Location: {profile.location}
- Skills: {profile.skills}
- Professional Summary: {profile.summary}
- Open to relocation to: {profile.target_countries}

TARGET JOB:
- Title: {job.title}
- Company: {job.company}
- Description: {(job.description or '')[:3000]}

IMPROVEMENT SUGGESTIONS TO ADDRESS (truthfully): {gaps_text}
"""

        result = await llm_generate(
            prompt,
            system="You are an expert CV writer that outputs strict JSON.",
            temperature=0.4,
            max_tokens=4096,
            api_key=api_key,
            json_mode=True,
        )
        return _extract_json(result)

    async def _generate_cover_letter(
        self, profile: UserProfile, job, baseline: str, api_key: str | None = None
    ) -> str:
        prompt = f"""Write a tailored cover letter for this job application. Use the baseline as a STYLE and FORMAT reference (match its tone, structure, and layout).
Express genuine interest in relocation and the specific role. Keep it professional and concise (200-320 words).

BASELINE COVER LETTER (mirror its format):
{baseline[:3000]}

APPLICANT: {profile.full_name}
TARGET JOB:
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description: {job.description[:2000]}

RELOCATION KEYWORDS IN JOB: {job.relocation_keywords}

FORMATTING RULES (critical):
- Output clean Markdown, NOT one block of text.
- Separate every paragraph with a blank line.
- Open with a greeting line (e.g. "Hi hiring team at {job.company},") followed by a blank line.
- 2-3 short body paragraphs, each separated by a blank line.
- Close with "Thanks for considering my application," then on a new line "Best regards," then on a new line "{profile.full_name}".
- Do NOT wrap the output in code fences or backticks.

Output the cover letter only as Markdown."""

        result = await llm_generate(
            prompt,
            system="You are an expert career coach helping with job applications.",
            temperature=0.7,
            max_tokens=2048,
            api_key=api_key,
        )
        # Return "" (not the untailored baseline) so the caller can detect failure.
        return result or ""
