"""Orchestrates all job scrapers and filters results."""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.database import Job, JobApplication, UserProfile
from app.services.job_matcher import JobMatcher
from app.services.scraper.base import RawJob
from app.services.scraper.linkedin import LinkedInScraper
from app.services.scraper.relocateme import RelocateMeScraper
from app.services.scraper.remotive import RemotiveScraper
from app.services.scraper.remoteok import RemoteOKScraper
from app.services.scraper.weworkremotely import WeWorkRemotelyScraper

logger = logging.getLogger(__name__)


class JobSearchService:
    def __init__(self) -> None:
        self.scrapers = [
            LinkedInScraper(),
            RemoteOKScraper(),
            RemotiveScraper(),
            WeWorkRemotelyScraper(),
            RelocateMeScraper(),
        ]
        self.matcher = JobMatcher()

    async def search_jobs(self, db: Session, user_profile_id: int, max_jobs: int = 100) -> dict:
        profile = db.query(UserProfile).filter(UserProfile.id == user_profile_id).first()
        if not profile:
            raise ValueError(f"User profile {user_profile_id} not found")

        max_jobs = min(max_jobs, settings.max_jobs_per_search)
        cutoff = datetime.utcnow() - timedelta(hours=settings.job_age_hours)

        roles = [r.strip() for r in (profile.target_roles or "").split(",") if r.strip()]
        locations = [c.strip() for c in (profile.target_countries or "").split(",") if c.strip()]

        raw_jobs = await self._fetch_all(roles, locations, settings.job_age_hours)
        stats = {
            "jobs_found": len(raw_jobs),
            "jobs_filtered_excluded": 0,
            "jobs_filtered_age": 0,
            "jobs_filtered_experience": 0,
            "jobs_filtered_role": 0,
            "jobs_filtered_country": 0,
            "jobs_stored": 0,
        }

        filtered: list[tuple[RawJob, float, str, str, bool]] = []
        for job in raw_jobs:
            # Hard exclusions: US-based roles and blacklisted companies (Canonical).
            excluded, _reason = self.matcher.is_excluded(job)
            if excluded:
                stats["jobs_filtered_excluded"] += 1
                continue

            # Constraint 1: posted within the last 48h. Unknown dates are
            # rejected since the constraint can't be verified for them.
            if not job.posted_at or job.posted_at < cutoff:
                stats["jobs_filtered_age"] += 1
                continue

            # Constraint 2: only junior / graduate / internship levels.
            experience_level = self.matcher.detect_experience_level(job)
            if not experience_level:
                stats["jobs_filtered_experience"] += 1
                continue

            # Relocation/visa info is still recorded (for scoring + display) but
            # is no longer a hard filter.
            offers_relocation, relocation_kw = self.matcher.check_relocation(job)

            # Constraint 4: must match one of the profile's target roles.
            if not self.matcher.matches_target_role(job, profile):
                stats["jobs_filtered_role"] += 1
                continue

            # Constraint 3: must be in one of the profile's target countries.
            if not self.matcher.matches_target_country(job, profile):
                stats["jobs_filtered_country"] += 1
                continue

            score = self.matcher.score_relevance(job, profile)
            filtered.append((job, score, experience_level, relocation_kw, offers_relocation))

        filtered.sort(key=lambda x: x[1], reverse=True)
        top_jobs = filtered[:max_jobs]

        for job, score, experience_level, relocation_kw, offers_relocation in top_jobs:
            existing = db.query(Job).filter(Job.external_id == job.external_id).first()
            if existing:
                existing.relevance_score = score
                job_record = existing
            else:
                job_record = Job(
                    external_id=job.external_id,
                    source=job.source,
                    title=job.title,
                    company=job.company,
                    company_domain=job.company_domain,
                    location=job.location,
                    description=job.description,
                    url=job.url,
                    experience_level=experience_level,
                    offers_relocation=offers_relocation,
                    relocation_keywords=relocation_kw,
                    posted_at=job.posted_at,
                    relevance_score=score,
                )
                db.add(job_record)
                db.flush()

            app_exists = (
                db.query(JobApplication)
                .filter(
                    JobApplication.user_profile_id == user_profile_id,
                    JobApplication.job_id == job_record.id,
                )
                .first()
            )
            if not app_exists:
                db.add(
                    JobApplication(
                        user_profile_id=user_profile_id,
                        job_id=job_record.id,
                        status="discovered",
                    )
                )
                stats["jobs_stored"] += 1

        db.commit()
        return stats

    async def _fetch_all(
        self,
        roles: list[str] | None = None,
        locations: list[str] | None = None,
        age_hours: int = 48,
    ) -> list[RawJob]:
        tasks = []
        for scraper in self.scrapers:
            if isinstance(scraper, LinkedInScraper):
                # LinkedIn is the primary source: it supports server-side
                # keyword/location/recency/level filtering, so pass the full
                # context and pull a larger share of results from it.
                tasks.append(
                    scraper.fetch_jobs(limit=120, roles=roles, locations=locations, age_hours=age_hours)
                )
            else:
                tasks.append(scraper.fetch_jobs(limit=150, roles=roles))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_jobs: list[RawJob] = []
        seen_ids: set[str] = set()
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Scraper failed: %s", result)
                continue
            for job in result:
                if job.external_id not in seen_ids:
                    seen_ids.add(job.external_id)
                    all_jobs.append(job)
        return all_jobs
