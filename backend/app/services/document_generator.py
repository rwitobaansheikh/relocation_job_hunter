"""Generate tailored CVs and cover letters using Google Gemini."""

import json
import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import ApplicationStatus, JobApplication, UserProfile
from app.services.gemini import gemini_generate
from app.services.job_analyzer import JobAnalyzer
from app.services.pdf import markdown_to_pdf

logger = logging.getLogger(__name__)


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

        # Structured AI analysis: match score, gaps, and a tailored cover letter.
        analysis = await self.analyzer.analyze(job.company, job.description or "", cv_text)

        gaps = analysis.get("gaps_and_suggestions") if analysis else None
        tailored_cv = _strip_code_fences(await self._generate_cv(profile, job, cv_text, gaps))

        # Prefer the analysis cover letter; fall back to the standalone generator.
        ai_cover_letter = (analysis.get("cover_letter") or "").strip() if analysis else ""
        if not ai_cover_letter:
            ai_cover_letter = await self._generate_cover_letter(profile, job, cover_base)
        tailored_cl = _strip_code_fences(ai_cover_letter)

        name = _safe_filename(profile.full_name)

        # CV: never send a blank/broken document. If the AI output looks empty,
        # fall back to the originally uploaded CV exactly as provided.
        if _looks_usable(tailored_cv):
            cv_path = self._write_document(tailored_cv, out_dir, f"{name} - CV")
        else:
            logger.warning(
                "Tailored CV for application %s looks blank; using the uploaded CV.",
                application_id,
            )
            cv_path = self._fallback_document(cv_text, profile.cv_path, out_dir, f"{name} - CV")

        # Cover letter: same principle - fall back to the uploaded one if needed.
        if _looks_usable(tailored_cl):
            cl_path = self._write_document(tailored_cl, out_dir, f"{name} - Cover Letter")
        else:
            logger.warning(
                "Tailored cover letter for application %s looks blank; using the uploaded one.",
                application_id,
            )
            cl_path = self._fallback_document(
                cover_base, profile.baseline_cover_letter_path, out_dir, f"{name} - Cover Letter"
            )

        if not cv_path:
            raise ValueError(
                "Could not produce a CV: AI generation returned nothing and no CV "
                "is uploaded for this profile. Upload a CV or retry."
            )

        application.tailored_cv_path = cv_path
        application.tailored_cover_letter_path = cl_path or ""
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
        results = []
        for app_id in application_ids:
            try:
                app = await self.tailor_for_application(db, app_id)
                results.append(app)
            except Exception as exc:
                logger.error("Failed to tailor application %s: %s", app_id, exc)
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
        """Use the originally uploaded document when AI generation is unusable.

        Prefer the original uploaded file as-is (keeps its real formatting). If
        that file is gone but we still have the extracted text, render that to a
        PDF. Returns "" if there is nothing to fall back to."""
        if original_path and Path(original_path).exists():
            return str(original_path)
        if original_text and original_text.strip():
            return self._write_document(original_text, out_dir, f"{base_name} (original)")
        return ""

    async def _generate_cv(self, profile: UserProfile, job, cv_text: str, gaps=None) -> str:
        contact = {
            "email": profile.email,
            "phone": profile.phone,
            "linkedin": profile.linkedin_url,
            "location": profile.location,
        }
        gaps_text = json.dumps(gaps) if gaps else "None provided"

        prompt = f"""You are an expert CV writer. Generate a modified, targeted one-page CV using the provided variables while strictly maintaining the original structure and formatting.

**CRITICAL REQUIREMENTS:**
1. Output must be in clean markdown format for immediate PDF conversion
2. CV must fit exactly on one page
3. Maintain original section order: Personal Info -> Summary -> Skills -> Work Experience -> Projects -> Education
4. **MUST include the candidate name at the top CENTER ALIGNED: {profile.full_name}**

**INPUT VARIABLES TO INCORPORATE:**
- CV Template Structure: {cv_text[:6000]}
- Target Job Description: {(job.description or '')[:3000]}
- Improvement Suggestions: {gaps_text}
- Candidate Name: {profile.full_name}
- Contact Information: {json.dumps(contact)}
- Skills Data: {profile.skills}
- Professional Summary: {profile.summary}
- Target Countries (open to relocation): {profile.target_countries}

**MODIFICATION INSTRUCTIONS:**
- **Include Name:** Start the CV with "{profile.full_name}" as the main heading (markdown H1) CENTER ALIGNED
- **Contact Info Format:** Place contact information centered below the name, separated by pipes
- **Tailor Content:** Align skills and experience with the target job description requirements
- **Implement Suggestions:** Address all identified gaps and incorporate improvement recommendations (truthfully; never fabricate experience)
- **Enhance Impact:** Use strong action verbs and quantify achievements with metrics
- **Modernize Skills:** Update technical skills to reflect current industry standards
- **Optimize Space:** Be concise and prioritize most relevant information for one-page constraint

**OUTPUT FORMAT:** Return the modified CV as Markdown Content only."""

        result = await gemini_generate(
            prompt,
            system="You are an expert CV writer.",
            temperature=0.5,
            max_tokens=4096,
        )
        # Return "" (not the untailored original) so the caller can detect failure.
        return result or ""

    async def _generate_cover_letter(self, profile: UserProfile, job, baseline: str) -> str:
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

        result = await gemini_generate(
            prompt,
            system="You are an expert career coach helping with job applications.",
            temperature=0.7,
            max_tokens=2048,
        )
        # Return "" (not the untailored baseline) so the caller can detect failure.
        return result or ""
