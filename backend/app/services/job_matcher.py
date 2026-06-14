"""Match and score jobs against user CV and filters."""

import re
from typing import Optional

from app.database import UserProfile
from app.services.scraper.base import (
    COUNTRY_ALIASES,
    EXCLUDED_COMPANIES,
    GLOBAL_LOCATION_SIGNALS,
    JUNIOR_KEYWORDS,
    RELOCATION_KEYWORDS,
    SENIORITY_KEYWORDS,
    US_LOCATION_SIGNALS,
    RawJob,
)


def _split_csv(value: str) -> list[str]:
    return [v.strip().lower() for v in (value or "").split(",") if v.strip()]


def _has_word(words: list[str], text: str) -> bool:
    return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)


# Seniority ordering used to enforce "not higher than selected" filters.
_LEVEL_RANK: dict[str, int] = {
    "intern": 0,
    "entry": 1,
    "mid": 2,
    "senior": 3,
    "executive": 4,
}

_LEVEL_KEYWORDS: dict[str, list[str]] = dict(SENIORITY_KEYWORDS)


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

    def classify_seniority(self, job: RawJob) -> str:
        """Classify a role into one of intern/entry/mid/senior/executive, or
        'unspecified' when no clear signal exists. The title is weighted first
        (more reliable), then the full text. 'unspecified' jobs are allowed
        through the seniority filter since boards rarely tag levels."""
        title = job.title.lower()
        for level, words in SENIORITY_KEYWORDS:
            if _has_word(words, title):
                return level
        text = " ".join([job.title, job.description, " ".join(job.tags)]).lower()
        for level, words in SENIORITY_KEYWORDS:
            if _has_word(words, text):
                return level
        return "unspecified"

    def _job_text(self, job: RawJob) -> str:
        return " ".join([job.title, job.description, " ".join(job.tags)]).lower()

    def _signals_levels(self, job: RawJob, level_names: list[str]) -> bool:
        text = self._job_text(job)
        title = job.title.lower()
        for name in level_names:
            words = _LEVEL_KEYWORDS.get(name, [])
            if _has_word(words, title) or _has_word(words, text):
                return True
        return False

    def matches_seniority(self, job: RawJob, levels: list[str]) -> bool:
        """True when the job fits the requested seniority band.

        When the user picks Internship / Entry only, mid/senior/executive roles
        are excluded. Untagged listings only pass if they show signals within the
        selected band and do not signal a higher level."""
        if not levels:
            return True

        classified = self.classify_seniority(job)
        allowed = {lvl for lvl in levels if lvl in _LEVEL_RANK}
        if not allowed:
            return True

        max_rank = max(_LEVEL_RANK[lvl] for lvl in allowed)

        if classified != "unspecified":
            return classified in allowed

        # Untagged role: reject clear signals above the user's ceiling.
        higher_levels = [lvl for lvl, rank in _LEVEL_RANK.items() if rank > max_rank]
        if self._signals_levels(job, higher_levels):
            return False

        # Early-career filters (intern/entry): require a matching early signal.
        if max_rank <= _LEVEL_RANK["entry"]:
            if job.source == "linkedin":
                # LinkedIn was already filtered by f_E (Experience Level) during scrape.
                # If we made it here without signaling a *higher* level, trust the LinkedIn tag.
                return True
            early_levels = [lvl for lvl in allowed if _LEVEL_RANK[lvl] <= _LEVEL_RANK["entry"]]
            return self._signals_levels(job, early_levels)

        # Mid-level and above: allow untagged unless we already ruled out higher.
        return True

    def matches_salary(self, job: RawJob, min_salary, max_salary) -> bool:
        """Best-effort salary gate. Jobs with no detectable salary always pass
        (most listings omit it). Only excludes when a detected figure clearly
        falls outside the requested band."""
        if not min_salary and not max_salary:
            return True
        smin = getattr(job, "salary_min", None)
        smax = getattr(job, "salary_max", None)
        if smin is None and smax is None:
            return True
        if min_salary and smax is not None and smax < min_salary:
            return False
        if max_salary and smin is not None and smin > max_salary:
            return False
        return True

    def matches_work_types(self, job: RawJob, work_types: list[str]) -> bool:
        """True when the job matches the selected work types.
        Allowed values: 'remote', 'hybrid', 'onsite'.
        If empty, all are allowed.
        """
        if not work_types:
            return True

        source = job.source.lower()
        if source == "linkedin":
            # LinkedIn was already filtered at the API level
            return True

        # Remote-only job boards
        if source in ("remoteok", "remotive", "weworkremotely"):
            return "remote" in work_types

        # Look for text clues in title, description, and location
        text = " ".join([job.title, job.description, job.location, " ".join(job.tags)]).lower()
        
        # Check remote signals
        if any(signal in text for signal in ("remote", "telecommute", "work from home", "wfh")):
            if "remote" in work_types:
                return True
        # Check hybrid signals
        if "hybrid" in text:
            if "hybrid" in work_types:
                return True
        # Default fallback: onsite (most traditional / relocation roles)
        return "onsite" in work_types

    def matches_target_role(self, job: RawJob, profile: UserProfile) -> bool:
        """True if the job matches one of the profile's target roles. When no
        target roles are set, all roles are allowed."""
        return self.matches_roles(job, _split_csv(profile.target_roles))

    def matches_roles(self, job: RawJob, roles: list[str]) -> bool:
        """Core role matcher (also used by per-role automation loops). Empty
        `roles` allows all."""
        roles = [r.strip().lower() for r in (roles or []) if r and r.strip()]
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
        return self.matches_locations(job, _split_csv(profile.target_countries))

    def matches_locations(self, job: RawJob, locations: list[str]) -> bool:
        """Core location matcher used for both profile target countries and an
        explicit per-search location filter. Empty `locations` allows all."""
        countries = [loc.strip().lower() for loc in (locations or []) if loc and loc.strip()]
        if not countries:
            return True

        text = " ".join([job.location, job.description, " ".join(job.tags)]).lower()
        
        # Exact/Alias match in text
        for country in countries:
            if country in text:
                return True
            for alias in COUNTRY_ALIASES.get(country, []):
                if alias in text:
                    return True

        # Check worldwide remote signals ONLY if the user didn't explicitly restrict to a non-remote physical country,
        # OR if the job explicitly says "anywhere" / "worldwide"
        worldwide_signals = ["worldwide", "anywhere", "global", "no location restriction", "remote (global)"]
        if any(signal in text for signal in worldwide_signals):
            return True
            
        # If they explicitly search for "remote", allow jobs with "remote" in them
        if "remote" in countries and "remote" in text:
            return True

        return False

    @staticmethod
    def _cv_tokens(cv_text: str) -> set[str]:
        if not cv_text:
            return set()
        stop = {
            "and", "the", "for", "with", "from", "that", "this", "have", "your",
            "will", "been", "were", "their", "about", "into", "using", "used",
        }
        tokens = re.findall(r"[a-z0-9+#.]{3,}", cv_text.lower())
        return {t for t in tokens if t not in stop and not t.isdigit()}

    def _cv_description_overlap(self, job: RawJob, profile: UserProfile) -> float:
        """0–40 points from CV vs job-description term overlap."""
        cv_tokens = self._cv_tokens(profile.cv_text or "")
        if not cv_tokens:
            return 0.0
        desc = " ".join([job.title, job.description, job.location]).lower()
        desc_tokens = set(re.findall(r"[a-z0-9+#.]{3,}", desc))
        if not desc_tokens:
            return 0.0
        overlap = len(cv_tokens & desc_tokens)
        ratio = overlap / max(len(cv_tokens), 1)
        return min(40.0, ratio * 80 + overlap * 0.5)

    def is_excluded(self, job: RawJob, requested_locations: Optional[list[str]] = None) -> tuple[bool, str]:
        """Hard exclusions applied before other filters: drop blacklisted companies.
        Only drops US-based roles if the user didn't explicitly request US locations."""
        company = (job.company or "").lower()
        for blocked in EXCLUDED_COMPANIES:
            if blocked in company:
                return True, f"excluded company ({job.company})"

        location_text = " ".join([job.location, " ".join(job.tags)]).lower()
        if self._is_us_location(location_text):
            # Check if user explicitly asked for US
            req = " ".join(requested_locations or []).lower()
            req_words = set(re.findall(r"\b[a-z]+\b", req))
            if "us" in req_words or "usa" in req_words or "united states" in req:
                pass # User explicitly wants US jobs
            else:
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

        # Primary ranking signal: CV vs full job description overlap.
        score += self._cv_description_overlap(job, profile)

        target_roles = [r.strip().lower() for r in (profile.target_roles or "").split(",") if r.strip()]
        for role in target_roles:
            if role in job.title.lower():
                score += 20
            elif role in text:
                score += 10

        target_countries = [c.strip().lower() for c in (profile.target_countries or "").split(",") if c.strip()]
        for country in target_countries:
            if country in text or country in job.location.lower():
                score += 10

        skills = [s.strip().lower() for s in (profile.skills or "").split(",") if s.strip()]
        for skill in skills:
            if skill in text:
                score += 4
            if skill in cv_text:
                score += 2

        if job.source == "relocateme":
            score += 10
        if job.source == "linkedin":
            score += 5

        relocation_kw = self.check_relocation(job)[1]
        if relocation_kw:
            score += 8

        exp = self.detect_experience_level(job)
        if exp == "graduate":
            score += 5
        elif exp == "intern":
            score += 3

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
