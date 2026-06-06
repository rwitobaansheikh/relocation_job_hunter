"""Match and score jobs against user CV and filters."""

import re

from app.database import UserProfile
from app.services.scraper.base import (
    COUNTRY_ALIASES,
    EXCLUDED_COMPANIES,
    GLOBAL_LOCATION_SIGNALS,
    JUNIOR_KEYWORDS,
    RELOCATION_KEYWORDS,
    US_LOCATION_SIGNALS,
    RawJob,
)


def _split_csv(value: str) -> list[str]:
    return [v.strip().lower() for v in (value or "").split(",") if v.strip()]


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
        """Return the role's early-career level. Explicit senior roles are
        rejected (''). Jobs that explicitly read as intern/graduate/junior get
        that label; everything else (no clear seniority signal) is treated as
        'unspecified' and allowed through, since boards rarely tag levels and
        LinkedIn already pre-filters to early-career via f_E."""
        title = job.title.lower()
        text = " ".join([job.title, job.description, " ".join(job.tags)]).lower()

        senior_signals = [
            "senior", "sr.", "lead", "principal", "staff", "head of", "manager",
            "director", "vp ", "3+ years", "4+ years", "5+ years", "6+ years",
            "7+ years", "8+ years", "10+ years",
        ]
        if any(s in title for s in senior_signals) or any(s in text for s in senior_signals):
            return ""

        for kw in JUNIOR_KEYWORDS:
            if kw in text:
                if "intern" in kw:
                    return "intern"
                if "grad" in kw:
                    return "graduate"
                return "junior"

        return "unspecified"

    def matches_target_role(self, job: RawJob, profile: UserProfile) -> bool:
        """True if the job matches one of the profile's target roles. When no
        target roles are set, all roles are allowed."""
        roles = _split_csv(profile.target_roles)
        if not roles:
            return True

        title = job.title.lower()
        text = " ".join([job.title, job.description, " ".join(job.tags)]).lower()
        for role in roles:
            if role in title or role in text:
                return True
            tokens = [t for t in role.split() if t]
            if tokens and all(tok in text for tok in tokens):
                return True
        return False

    def matches_target_country(self, job: RawJob, profile: UserProfile) -> bool:
        """True if the job names one of the profile's target countries (or a known
        alias), OR is an open remote/global role. US-based and excluded-company
        jobs are removed separately via `is_excluded`. When no target countries
        are set, all (non-excluded) locations are allowed."""
        text = " ".join([job.location, job.description, " ".join(job.tags)]).lower()

        countries = _split_csv(profile.target_countries)
        if not countries:
            return True

        for country in countries:
            if country in text:
                return True
            for alias in COUNTRY_ALIASES.get(country, []):
                if alias in text:
                    return True

        # Keep remote/global roles available even if they don't name a target
        # country (US ones are already filtered out by `is_excluded`).
        return any(signal in text for signal in GLOBAL_LOCATION_SIGNALS)

    def is_excluded(self, job: RawJob) -> tuple[bool, str]:
        """Hard exclusions applied before other filters: drop US-based roles and
        any blacklisted companies (e.g. Canonical)."""
        company = (job.company or "").lower()
        for blocked in EXCLUDED_COMPANIES:
            if blocked in company:
                return True, f"excluded company ({job.company})"

        location_text = " ".join([job.location, " ".join(job.tags)]).lower()
        if self._is_us_location(location_text):
            return True, "US location"
        return False, ""

    @staticmethod
    def _is_us_location(text: str) -> bool:
        for signal in US_LOCATION_SIGNALS:
            if re.search(r"\b" + re.escape(signal) + r"\b", text):
                return True
        # Standalone "us" as a location token (e.g. "Remote, US"), guarding
        # against substrings like "business" or country code confusion.
        return bool(re.search(r"(^|[\s,(/-])us([\s,)/.-]|$)", text))

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
        if job.source == "linkedin":
            score += 18

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
