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
from app.services.docx_renderer import (
    cv_layout_prompt_reference,
    document_filename,
    render_cover_letter_docx,
    render_resume_docx,
)
from app.services.llm import llm_available, llm_generate, resolve_gemini_api_key
from app.services.job_analyzer import JobAnalyzer

logger = logging.getLogger(__name__)

_SECTION_ORDER = [
    "summary",
    "skills",
    "soft_skills",
    "experience",
    "projects",
    "certifications",
    "education",
]
_ALLOWED_SECTION_TYPES = set(_SECTION_ORDER)


def _sort_resume_sections(data: dict) -> dict:
    sections = [s for s in (data.get("sections") or []) if isinstance(s, dict)]
    order_map = {t: i for i, t in enumerate(_SECTION_ORDER)}
    sections.sort(key=lambda s: order_map.get(s.get("type") or "", 99))
    data["sections"] = sections
    return data


_GEMINI_PACE_SECONDS = 2.5
_BATCH_PACE_SECONDS = 5.0
_AI_FAILURE_MSG = (
    "AI tailoring failed — the local LLM may be offline or overloaded. "
    "Ensure Ollama is running and the configured model is pulled, then retry."
)


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
            if isinstance(group, dict):
                if group.get("value"):
                    chunks.append(str(group["value"]))
                if group.get("label"):
                    chunks.append(str(group["label"]))
    words = [w for w in " ".join(chunks).split() if any(ch.isalnum() for ch in w)]
    return len(words)


def _resume_usable(data: dict | None) -> bool:
    return bool(data) and _resume_word_count(data) >= 40


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

        if not _resume_usable(cv_data):
            logger.warning(
                "Tailored CV for application %s unusable (AI empty or truncated).",
                application_id,
            )
            raise ValueError(_AI_FAILURE_MSG)

        cv_data = self._apply_profile_identity(cv_data, profile, cv_text)
        cv_data = _sort_resume_sections(cv_data)
        cv_docx = out_dir / document_filename(profile.full_name, job.title, "CV")
        if not render_resume_docx(cv_data, str(cv_docx)):
            raise ValueError("Failed to render the tailored CV to Word format. Please retry.")

        if not _looks_usable(tailored_cl):
            logger.warning(
                "Tailored cover letter for application %s unusable (AI empty or truncated).",
                application_id,
            )
            raise ValueError(_AI_FAILURE_MSG)

        cl_docx = out_dir / document_filename(profile.full_name, job.title, "Cover-Letter")
        contact = self._contact(profile)
        if not render_cover_letter_docx(profile.full_name, contact, tailored_cl, str(cl_docx)):
            raise ValueError("Failed to render the tailored cover letter to Word format. Please retry.")
        cl_path = str(cl_docx)

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

        application.tailored_cv_path = str(cv_docx)
        application.tailored_cover_letter_path = cl_path
        if analysis:
            try:
                application.ai_match_score = int(analysis.get("match_score") or 0)
            except (TypeError, ValueError):
                application.ai_match_score = 0
            analysis["cover_letter"] = tailored_cl
            analysis["cv_preview"] = cv_data
            application.analysis_json = json.dumps(analysis)
        else:
            application.analysis_json = json.dumps({"cover_letter": tailored_cl, "cv_preview": cv_data})
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

    def _write_document(self, markdown_text: str, out_dir, base_name: str, job_title: str = "") -> str:
        """Write the document as .docx (plain paragraphs)."""
        docx_path = out_dir / document_filename(base_name.replace(" ", "-"), job_title or "Role", "Document")
        contact = {"email": "", "phone": "", "linkedin": "", "location": ""}
        if render_cover_letter_docx("", contact, markdown_text, str(docx_path)):
            return str(docx_path)
        txt_path = out_dir / f"{base_name}.txt"
        txt_path.write_text(markdown_text, encoding="utf-8")
        return str(txt_path)

    def _fallback_document(
        self, original_text: str, original_path: str, out_dir, base_name: str, job_title: str = ""
    ) -> str:
        """Copy an uploaded document into the per-application output dir when needed."""
        source = Path(original_path) if original_path else None
        if source and source.exists() and source.suffix.lower() == ".docx":
            dest = out_dir / document_filename(base_name, job_title or "Role", "CV")
            shutil.copy2(source, dest)
            return str(dest)
        if original_text and original_text.strip():
            return self._write_document(original_text, out_dir, base_name, job_title)
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
        cleaned_sections = []
        for s in data.get("sections") or []:
            if not isinstance(s, dict) or s.get("type") not in _ALLOWED_SECTION_TYPES:
                continue
            st = s.get("type")
            if st == "certifications" and not (s.get("items") or []):
                continue
            if st == "soft_skills" and not (s.get("groups") or []):
                continue
            cleaned_sections.append(s)
        data["sections"] = cleaned_sections
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
  "tagline": "Role-aligned headline e.g. Software Engineer and Machine Learning Specialist",
  "contact": {"phone": "", "email": "", "linkedin": "", "github": "", "location": ""},
  "sections": [
    {"type": "summary", "title": "PROFESSIONAL SUMMARY", "text": "3-5 sentence tailored summary"},
    {"type": "skills", "title": "TECHNICAL SKILLS", "groups": [
      {"label": "Machine Learning & Deep Learning", "value": "PyTorch, TensorFlow, CNNs"},
      {"label": "MLOps, Cloud & DevOps", "value": "AWS, GCP, Docker, Terraform"}
    ]},
    {"type": "soft_skills", "title": "SOFT SKILLS", "groups": [
      {"label": "Leadership & Team Development", "value": "evidence-backed phrase from source CV"},
      {"label": "Communication", "value": "evidence-backed phrase tailored to the role"}
    ]},
    {"type": "experience", "title": "PROFESSIONAL EXPERIENCE", "items": [
      {"role": "Data Engineer", "company": "TCS (client: Equifax USA)", "location": "Mumbai, India", "date": "Apr 2022 – Aug 2023", "bullets": ["achievement with metrics"]}
    ]},
    {"type": "projects", "title": "PROJECTS", "items": [
      {"heading": "Project Name", "tech": "PyTorch, Python, Flask", "date": "2026", "bullets": ["impact bullet"], "links": [{"label": "Source code", "url": "https://..."}]}
    ]},
    {"type": "certifications", "title": "CERTIFICATIONS & CONTINUOUS LEARNING", "items": [
      {"heading": "Course or cert name, Provider", "detail": "status and year. One-line description."}
    ]},
    {"type": "education", "title": "EDUCATION", "items": [
      {"degree": "MSc Machine Learning and Autonomous Systems (Merit)", "school": "University of Bath", "location": "Bath, UK", "date": "Oct 2023 – Jan 2025", "courses": "deep learning, statistics, Bayesian ML"}
    ]}
  ]
}"""

        layout_spec = cv_layout_prompt_reference()

        prompt = f"""You are an expert CV writer producing CV360-approved ATS-friendly CVs.
Rewrite the source CV for the target role. Output strict JSON only — no markdown fences.

TARGET ROLE: {job.title}
JOB DESCRIPTION (extract keywords, soft skills, and technical requirements):
{(job.description or '')[:3000]}

Tailoring = re-emphasise, reorder, and reword REAL content from the source CV.
Never invent employers, dates, degrees, tools, certifications, or metrics.

Return ONLY a JSON object matching this schema:
{schema}

{layout_spec}

CONTENT RULES:
1. Maximum 2 A4 pages (~700-800 words). Drop least-relevant content instead of padding.
2. UK English spelling (optimise, organise, specialise).
3. tagline: concise role headline tailored to {job.title} (not generic "passionate professional").
4. TECHNICAL SKILLS: reorder categories and tools to mirror the job description. Job-required skills first.
5. SOFT SKILLS (required): 4-6 lines tailored to the role's interpersonal/leadership needs.
   Read the job description for cues (stakeholder management, cross-functional work, mentoring, etc.).
   Each line must reflect REAL experience from the source CV — paraphrase evidence, do not fabricate.
6. Experience: reverse chronological. 2-4 metric-driven bullets per role. Use role + company fields.
7. Projects: 2-3 most relevant; angle bullets toward the target role.
8. Certifications: include courses/certs from the source CV; omit the section if none exist.
9. Education: reverse chronological; add "Relevant courses" aligned to the target role.
10. Avoid AI clichés: leverage, robust, seamless, cutting-edge, dynamic, passionate, synergy.
11. Bullets must NOT start with a dash, bullet character, or number.
12. Project links: copy ONLY from ORIGINAL PROJECT LINKS — never invent URLs.

ORIGINAL PROJECT LINKS (copy exactly):
{links_prompt or "(none found — omit links arrays)"}

SOURCE CV:
{cv_text[:6000]}

CANDIDATE CONTACT:
- Name: {profile.full_name}
- Email: {profile.email} | Phone: {profile.phone} | LinkedIn: {profile.linkedin_url}
- Skills: {profile.skills}
- Open to relocation: {profile.target_countries}

IMPROVEMENT SUGGESTIONS (address truthfully): {gaps_text}
"""

        result = await llm_generate(
            prompt,
            system=(
                "You are an expert CV writer producing strict JSON for a CV360 ATS Word template. "
                "Layout: centred name, bold tagline, spaced contact line, ALL CAPS section headers, "
                "technical skills then soft skills (role-tailored), experience, projects, certifications, education."
            ),
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
