"""Autonomous per-loop pipeline: search -> tailor.

Each AutomationLoop targets one job role with its own filters. Runs are bounded by
the loop's tailor cap and the owner's plan (tailor/day). Jobs found during a run
are tagged with an automation_batch_date so users can review them as a daily queue.
Every pass is recorded as an AutomationRun for visibility/audit.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.database import (
    ApplicationStatus,
    AutomationLoop,
    AutomationRun,
    Job,
    JobApplication,
    User,
    UserProfile,
)
from app.services.automation_notifications import notify_run_complete
from app.services.document_generator import DocumentGenerator
from app.services.job_search import JobSearchService, SearchFilters
from app.services.plans import effective_limits
from app.services.usage import get_usage, incr_usage

logger = logging.getLogger(__name__)


def _csv(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _job_matches_role(job: Job, role: str) -> bool:
    if not role:
        return True
    text = f"{job.title or ''} {job.description or ''}".lower()
    role = role.lower()
    if role in text:
        return True
    tokens = [t for t in role.split() if t]
    return bool(tokens) and all(t in text for t in tokens)


class AutomationService:
    def __init__(self) -> None:
        self.generator = DocumentGenerator()

    async def run_for_loop(
        self, db: Session, loop: AutomationLoop, limits=None
    ) -> AutomationRun:
        profile = (
            db.query(UserProfile).filter(UserProfile.id == loop.user_profile_id).first()
        )
        run = AutomationRun(
            user_profile_id=loop.user_profile_id,
            automation_loop_id=loop.id,
            status="running",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        batch_date = datetime.utcnow().strftime("%Y-%m-%d")
        notes: list[str] = [f"loop '{loop.name or loop.role or loop.id}'"]
        try:
            if limits is None and profile is not None:
                user = db.query(User).filter(User.id == profile.user_id).first()
                limits = effective_limits(user) if user else None

            try:
                filters = SearchFilters(
                    roles=[loop.role] if loop.role else [],
                    location=_csv(loop.locations)[0] if _csv(loop.locations) else "",
                    seniority_levels=_csv(loop.seniority_levels),
                    posted_within_hours=loop.posted_within_hours or settings.job_age_hours,
                    min_salary=loop.min_salary,
                    max_salary=loop.max_salary,
                )
                stats = await JobSearchService().search_jobs(
                    db,
                    loop.user_profile_id,
                    settings.max_jobs_per_search,
                    filters,
                    automation_batch_date=batch_date,
                )
                run.jobs_found = stats.get("jobs_stored", 0)
                notes.append(f"search: {stats.get('jobs_stored', 0)} new ({batch_date})")
            except Exception as exc:
                logger.warning("Automation search failed for loop %s: %s", loop.id, exc)
                notes.append(f"search error: {exc}")

            discovered = (
                db.query(JobApplication)
                .join(Job, Job.id == JobApplication.job_id)
                .filter(
                    JobApplication.user_profile_id == loop.user_profile_id,
                    JobApplication.status == ApplicationStatus.DISCOVERED.value,
                    JobApplication.automation_batch_date == batch_date,
                )
                .all()
            )

            tailor_limit = limits.tailor_per_day if limits else 10
            used_tailor = get_usage(db, loop.user_profile_id, "tailor")
            remaining_tailor = max(0, tailor_limit - used_tailor)

            loop_tailor_cap = loop.max_tailor_per_run or settings.default_max_tailor_per_run
            tailor_batch_size = min(remaining_tailor, loop_tailor_cap)

            if tailor_batch_size > 0:
                to_tailor = [
                    a.id for a in discovered if _job_matches_role(a.job, loop.role)
                ][:tailor_batch_size]
                tailored = await self.generator.tailor_batch(db, to_tailor)
                for _ in tailored:
                    incr_usage(db, loop.user_profile_id, "tailor")
                run.jobs_tailored = len(tailored)
                notes.append(f"tailored: {len(tailored)}")
            else:
                run.jobs_tailored = 0
                notes.append("tailor: plan limit reached")

            run.emails_sent = 0
            run.status = "success"
        except Exception as exc:
            logger.exception("Automation run failed for loop %s", loop.id)
            run.status = "error"
            notes.append(f"fatal: {exc}")
        finally:
            run.finished_at = datetime.utcnow()
            run.detail = " | ".join(notes)[:2000]
            loop.last_run_at = run.finished_at
            db.commit()
            db.refresh(run)

        if run.status == "success":
            # Daily digest to the loop owner; failures are logged, never raised.
            await notify_run_complete(db, loop, run, batch_date)
        return run


async def run_due_loops(db: Session) -> int:
    """Run every enabled loop whose interval has elapsed and whose owner's plan
    still permits automation. Returns the number of loops processed."""
    if not settings.automation_globally_enabled:
        logger.info("Automation globally disabled; skipping scheduler tick.")
        return 0

    now = datetime.utcnow()
    loops = db.query(AutomationLoop).filter(AutomationLoop.enabled.is_(True)).all()
    service = AutomationService()
    processed = 0
    for loop in loops:
        interval = loop.interval_hours or settings.default_automation_interval_hours
        if loop.last_run_at and (now - loop.last_run_at).total_seconds() < interval * 3600:
            continue
        profile = (
            db.query(UserProfile).filter(UserProfile.id == loop.user_profile_id).first()
        )
        if not profile:
            continue
        user = db.query(User).filter(User.id == profile.user_id).first()
        limits = effective_limits(user) if user else None
        if not limits or not limits.can_automate:
            continue
        logger.info("Running automation loop %s (profile %s)", loop.id, profile.id)
        await service.run_for_loop(db, loop, limits)
        processed += 1
    return processed
