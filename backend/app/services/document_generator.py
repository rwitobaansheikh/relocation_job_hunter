"""Generate tailored CVs and cover letters using OpenAI."""

import logging
from pathlib import Path

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.database import ApplicationStatus, JobApplication, UserProfile

logger = logging.getLogger(__name__)


class DocumentGenerator:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

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

        tailored_cv = await self._generate_cv(profile, job, cv_text)
        tailored_cl = await self._generate_cover_letter(profile, job, cover_base)

        cv_path = out_dir / "tailored_cv.txt"
        cl_path = out_dir / "tailored_cover_letter.txt"
        cv_path.write_text(tailored_cv, encoding="utf-8")
        cl_path.write_text(tailored_cl, encoding="utf-8")

        application.tailored_cv_path = str(cv_path)
        application.tailored_cover_letter_path = str(cl_path)
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

    async def _generate_cv(self, profile: UserProfile, job, cv_text: str) -> str:
        prompt = f"""Tailor this CV for the job application below. Keep it truthful — only reframe and emphasize 
existing experience. Highlight skills relevant to the role and mention openness to relocation.

USER CV:
{cv_text[:6000]}

TARGET JOB:
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description: {job.description[:3000]}

USER SKILLS: {profile.skills}
TARGET COUNTRIES: {profile.target_countries}

Output a complete tailored CV in plain text format."""

        return await self._call_llm(prompt, fallback=cv_text)

    async def _generate_cover_letter(self, profile: UserProfile, job, baseline: str) -> str:
        prompt = f"""Write a tailored cover letter for this job application. Use the baseline as style reference.
Express genuine interest in relocation and the specific role. Keep it professional and concise (300-400 words).

BASELINE COVER LETTER:
{baseline[:3000]}

APPLICANT: {profile.full_name}
TARGET JOB:
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description: {job.description[:2000]}

RELOCATION KEYWORDS IN JOB: {job.relocation_keywords}

Output the cover letter only."""

        return await self._call_llm(prompt, fallback=baseline)

    async def _call_llm(self, prompt: str, fallback: str) -> str:
        if not self.client:
            logger.warning("OpenAI API key not configured; returning fallback text")
            return fallback

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert career coach helping with job applications."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        return response.choices[0].message.content or fallback
