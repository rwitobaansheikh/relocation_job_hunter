"""Match and score jobs against user CV and filters."""

import re

from app.database import UserProfile
from app.services.scraper.base import JUNIOR_KEYWORDS, RELOCATION_KEYWORDS, RawJob


class JobMatcher:
    def check_relocation(self, job: RawJob) -> tuple[bool, str]:
        text = " ".join(
            [
                job.title,
                job.description,
                job.location,
                " ".join(job.tags),
            ]
        ).lower()

        if job.source == "relocateme":
            return True, "relocate.me listing"

        matched = [kw for kw in RELOCATION_KEYWORDS if kw in text]
        if matched:
            return True, ", ".join(matched)

        remote_relocation_signals = [
            "worldwide",
            "anywhere",
            "global",
            "international candidates",
            "open to international",
            "no location restriction",
        ]
        for signal in remote_relocation_signals:
            if signal in text:
                return True, signal

        return False, ""

    def detect_experience_level(self, job: RawJob) -> str:
        text = " ".join([job.title, job.description, " ".join(job.tags)]).lower()

        for kw in JUNIOR_KEYWORDS:
            if kw in text:
                if "intern" in kw:
                    return "intern"
                if "grad" in kw:
                    return "graduate"
                return "junior"

        senior_signals = ["senior", "lead", "principal", "staff", "5+ years", "7+ years", "10+ years"]
        if any(s in text for s in senior_signals):
            return ""

        if job.source in ("relocateme", "remoteok", "remotive"):
            return "junior"

        return ""

    def score_relevance(self, job: RawJob, profile: UserProfile) -> float:
        score = 0.0
        text = " ".join([job.title, job.description, " ".join(job.tags)]).lower()
        cv_text = (profile.cv_text or "").lower()

        target_roles = [r.strip().lower() for r in (profile.target_roles or "").split(",") if r.strip()]
        for role in target_roles:
            if role in job.title.lower():
                score += 30
            elif role in text:
                score += 15

        target_countries = [c.strip().lower() for c in (profile.target_countries or "").split(",") if c.strip()]
        for country in target_countries:
            if country in text or country in job.location.lower():
                score += 20

        skills = [s.strip().lower() for s in (profile.skills or "").split(",") if s.strip()]
        for skill in skills:
            if skill in text:
                score += 5
            if skill in cv_text:
                score += 2

        skill_matches = sum(1 for skill in skills if skill in text)
        if skills:
            score += (skill_matches / len(skills)) * 25

        if job.source == "relocateme":
            score += 15

        relocation_kw = self.check_relocation(job)[1]
        if relocation_kw:
            score += 10

        exp = self.detect_experience_level(job)
        if exp == "graduate":
            score += 8
        elif exp == "intern":
            score += 5

        return round(min(score, 100.0), 2)

    @staticmethod
    def extract_skills_from_cv(cv_text: str) -> list[str]:
        common_skills = [
            "python", "javascript", "typescript", "react", "node", "java", "go", "rust",
            "sql", "postgresql", "mongodb", "aws", "docker", "kubernetes", "git",
            "fastapi", "django", "flask", "vue", "angular", "c++", "c#", "ruby",
            "machine learning", "data science", "devops", "ci/cd", "linux", "html", "css",
        ]
        cv_lower = cv_text.lower()
        return [s for s in common_skills if s in cv_lower]
