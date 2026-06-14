"""Orchestrates all job scrapers and filters results."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.database import Job, JobApplication, UserProfile
from app.services.job_matcher import JobMatcher
from app.services.scraper.base import (
    LEVEL_TO_FE,
    RawJob,
    parse_salary,
    salary_to_fe_bucket,
)
from app.services.scraper.linkedin_query import (
    resolve_work_type_codes,
    split_locations,
)
from app.services.scraper.linkedin import LinkedInScraper, compute_fetch_limit
from app.services.scraper.relocateme import RelocateMeScraper
from app.services.scraper.remotive import RemotiveScraper
from app.services.scraper.remoteok import RemoteOKScraper
from app.services.scraper.weworkremotely import WeWorkRemotelyScraper

logger = logging.getLogger(__name__)


@dataclass
class SearchFilters:
    """Optional per-search filters. All fields fall back to sensible defaults
    (profile preferences / settings) when unset."""

    seniority_levels: list[str] = field(default_factory=list)
    posted_within_hours: Optional[int] = None
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    location: str = ""
    # Overrides the profile's target_roles for this search when provided
    # (used by per-role automation loops).
    roles: list[str] = field(default_factory=list)
    # LinkedIn f_WT work-type filters: remote, hybrid, onsite.
    work_types: list[str] = field(default_factory=list)

    def experience_codes(self) -> Optional[str]:
        codes: list[str] = []
        for level in self.seniority_levels:
            codes.extend(LEVEL_TO_FE.get(level, []))
        if not codes:
            return None
        return ",".join(sorted(set(codes), key=int))

    def linkedin_locations(self) -> list[str]:
        """Geographic locations for LinkedIn (work-type tokens stripped)."""
        geo, _ = split_locations([self.location] if self.location else [])
        return geo

    def linkedin_work_type_codes(self) -> list[str]:
        return resolve_work_type_codes(self.work_types, [self.location] if self.location else [])


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

    async def search_jobs(
        self,
        db: Session,
        user_profile_id: int,
        max_jobs: int = 100,
        filters: Optional[SearchFilters] = None,
    ) -> dict:
        """Original synchronous-like search (used by automation loops).
        Iterates the stream and accumulates stats."""
        final_stats = {
            "jobs_found": 0,
            "jobs_stored": 0,
            "jobs_filtered": 0,
        }
        async for event in self.search_jobs_stream(db, user_profile_id, max_jobs, filters):
            if event["type"] == "done":
                final_stats = event["stats"]
                break
            elif event["type"] == "job":
                final_stats = event["stats"]
                if final_stats["jobs_stored"] >= max_jobs:
                    break
        return final_stats

    async def search_jobs_stream(
        self,
        db: Session,
        user_profile_id: int,
        max_jobs: int = 100,
        filters: Optional[SearchFilters] = None,
    ):
        profile = db.query(UserProfile).filter(UserProfile.id == user_profile_id).first()
        if not profile:
            raise ValueError(f"User profile {user_profile_id} not found")

        filters = filters or SearchFilters()
        max_jobs = min(max_jobs, settings.max_jobs_per_search)
        age_hours = filters.posted_within_hours or settings.job_age_hours
        cutoff = datetime.utcnow() - timedelta(hours=age_hours)

        if filters.roles:
            roles = [r.strip() for r in filters.roles if r.strip()]
        else:
            roles = [r.strip() for r in (profile.target_roles or "").split(",") if r.strip()]
            
        if filters.location:
            locations = [filters.location.strip()]
        else:
            locations = [c.strip() for c in (profile.target_countries or "").split(",") if c.strip()]

        linkedin_geo, _ = split_locations(locations)
        if not linkedin_geo:
            linkedin_geo = [""]

        existing_external_ids = self._existing_external_ids(db, user_profile_id)

        yield {"type": "status", "message": f"Starting search for {linkedin_geo[0]}..."}

        stats = {
            "jobs_found": 0,
            "jobs_stored": 0,
            "jobs_filtered": 0,
        }

        linkedin_scraper = next((s for s in self.scrapers if isinstance(s, LinkedInScraper)), None)
        if not linkedin_scraper:
            yield {"type": "done", "stats": stats}
            return

        async for job in linkedin_scraper.fetch_jobs_stream(
            roles=roles,
            location=linkedin_geo[0],
            age_hours=age_hours,
            experience_codes=filters.experience_codes(),
            salary_bucket=salary_to_fe_bucket(filters.min_salary),
            work_type_codes=filters.linkedin_work_type_codes(),
            exclude_external_ids=existing_external_ids,
        ):
            smin, smax, currency, salary_label = parse_salary(" ".join([job.title, job.description]))
            job.salary_min, job.salary_max = smin, smax
            job.salary_currency, job.salary_text = currency, salary_label

            excluded, _reason = self.matcher.is_excluded(job, [filters.location] if filters.location else None)
            if excluded:
                stats["jobs_filtered"] += 1
                continue

            if job.posted_at and job.posted_at < cutoff:
                stats["jobs_filtered"] += 1
                continue

            if not self.matcher.matches_locations(job, [filters.location] if filters.location else locations):
                stats["jobs_filtered"] += 1
                continue

            seniority_level = self.matcher.classify_seniority(job)
            if not self.matcher.matches_seniority(job, filters.seniority_levels):
                stats["jobs_filtered"] += 1
                continue

            if not self.matcher.matches_work_types(job, filters.work_types):
                stats["jobs_filtered"] += 1
                continue

            offers_relocation, relocation_kw = self.matcher.check_relocation(job)
            score = self.matcher.score_relevance(job, profile)
            
            stats["jobs_found"] += 1

            existing = db.query(Job).filter(Job.external_id == job.external_id).first()
            if existing:
                existing.relevance_score = score
                existing.seniority_level = seniority_level
                existing.salary_min = job.salary_min
                existing.salary_max = job.salary_max
                existing.salary_currency = job.salary_currency
                existing.salary_text = job.salary_text
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
                    experience_level=seniority_level,
                    seniority_level=seniority_level,
                    offers_relocation=offers_relocation,
                    relocation_keywords=relocation_kw,
                    salary_min=job.salary_min,
                    salary_max=job.salary_max,
                    salary_currency=job.salary_currency,
                    salary_text=job.salary_text,
                    posted_at=job.posted_at,
                    relevance_score=score,
                )
                db.add(job_record)
                db.flush()

            app_exists = db.query(JobApplication).filter(JobApplication.user_profile_id == user_profile_id, JobApplication.job_id == job_record.id).first()
            if not app_exists:
                db.add(JobApplication(user_profile_id=user_profile_id, job_id=job_record.id, status="discovered"))
                stats["jobs_stored"] += 1

            db.commit()

            yield {
                "type": "job",
                "job": {
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "url": job.url
                },
                "stats": stats
            }

        yield {"type": "done", "stats": stats}

    @staticmethod
    def _existing_external_ids(db: Session, user_profile_id: int) -> set[str]:
        rows = (
            db.query(Job.external_id)
            .join(JobApplication, JobApplication.job_id == Job.id)
            .filter(JobApplication.user_profile_id == user_profile_id)
            .all()
        )
        return {row[0] for row in rows if row[0]}

    async def _fetch_all(
        self,
        roles: list[str] | None = None,
        locations: list[str] | None = None,
        age_hours: int = 48,
        max_jobs: int = 100,
        exclude_external_ids: Optional[set[str]] = None,
        experience_codes: Optional[str] = None,
        salary_bucket: Optional[str] = None,
        work_type_codes: Optional[list[str]] = None,
    ) -> list[RawJob]:
        linkedin_limit = compute_fetch_limit(requested=max_jobs, locations=locations)
        exclude = exclude_external_ids or set()
        tasks = []
        for scraper in self.scrapers:
            if isinstance(scraper, LinkedInScraper):
                tasks.append(
                    scraper.fetch_jobs(
                        limit=linkedin_limit,
                        roles=roles,
                        locations=locations,
                        age_hours=age_hours,
                        exclude_external_ids=exclude,
                        experience_codes=experience_codes,
                        salary_bucket=salary_bucket,
                        work_type_codes=work_type_codes,
                    )
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
                if job.external_id in exclude:
                    continue
                if job.external_id not in seen_ids:
                    seen_ids.add(job.external_id)
                    all_jobs.append(job)
        return all_jobs
