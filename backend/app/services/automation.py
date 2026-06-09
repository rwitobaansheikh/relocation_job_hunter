"""Autonomous per-loop pipeline: search -> tailor -> find contacts -> send.

Each AutomationLoop targets one job role with its own filters and caps. Runs are
bounded by:
  - the loop's daily send cap, clamped to the owner's plan (auto/loop/day)
  - per-company (per-domain) cap per run
  - suppression of companies the user has already emailed
  - the shared-API global rate limiter (inside the Gemini/Hunter clients)
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
    OutreachEmail,
    User,
    UserProfile,
)
from app.services.document_generator import DocumentGenerator
from app.services.email_service import EmailService
from app.services.job_search import JobSearchService, SearchFilters
from app.services.plans import effective_limits
from app.services.usage import get_usage, incr_usage

logger = logging.getLogger(__name__)

_SENT_STATUSES = ("sent",)


def _today_start() -> datetime:
    now = datetime.utcnow()
    return datetime(now.year, now.month, now.day)


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


def _contacted_companies(db: Session, profile_id: int) -> set[str]:
    rows = (
        db.query(Job.company)
        .join(JobApplication, JobApplication.job_id == Job.id)
        .join(OutreachEmail, OutreachEmail.application_id == JobApplication.id)
        .filter(
            JobApplication.user_profile_id == profile_id,
            OutreachEmail.status.in_(_SENT_STATUSES),
        )
        .distinct()
        .all()
    )
    return {(r[0] or "").strip().lower() for r in rows if r[0]}


class AutomationService:
    def __init__(self) -> None:
        self.generator = DocumentGenerator()
        self.email_service = EmailService()

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

        notes: list[str] = [f"loop '{loop.name or loop.role or loop.id}'"]
        try:
            if limits is None and profile is not None:
                user = db.query(User).filter(User.id == profile.user_id).first()
                limits = effective_limits(user) if user else None

            # 1) Search for fresh jobs scoped to this loop's role + filters.
            try:
                filters = SearchFilters(
                    roles=[loop.role] if loop.role else [],
                    locations=_csv(loop.locations),
                    seniority_levels=_csv(loop.seniority_levels),
                    posted_within_hours=loop.posted_within_hours or settings.job_age_hours,
                    min_salary=loop.min_salary,
                    max_salary=loop.max_salary,
                )
                stats = await JobSearchService().search_jobs(
                    db, loop.user_profile_id, settings.max_jobs_per_search, filters
                )
                run.jobs_found = stats.get("jobs_stored", 0)
                notes.append(f"search: {stats.get('jobs_stored', 0)} new")
            except Exception as exc:
                logger.warning("Automation search failed for loop %s: %s", loop.id, exc)
                notes.append(f"search error: {exc}")

            # 2) Tailor up to N discovered apps for this loop's role.
            discovered = (
                db.query(JobApplication)
                .join(Job, Job.id == JobApplication.job_id)
                .filter(
                    JobApplication.user_profile_id == loop.user_profile_id,
                    JobApplication.status == ApplicationStatus.DISCOVERED.value,
                )
                .all()
            )
            to_tailor = [
                a.id for a in discovered if _job_matches_role(a.job, loop.role)
            ][: (loop.max_tailor_per_run or settings.default_max_tailor_per_run)]
            tailored = await self.generator.tailor_batch(db, to_tailor)
            run.jobs_tailored = len(tailored)
            notes.append(f"tailored: {len(tailored)}")

            # 3) Send within the loop + plan caps.
            run.emails_sent = await self._send_within_caps(db, loop, limits, notes)
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
        return run

    async def _send_within_caps(
        self, db: Session, loop: AutomationLoop, limits, notes: list[str]
    ) -> int:
        plan_cap = limits.auto_per_loop_per_day if limits else settings.default_daily_send_cap
        loop_cap = loop.daily_send_cap if loop.daily_send_cap is not None else 5
        cap = min(loop_cap, plan_cap)
        scope = f"loop:{loop.id}"
        remaining = cap - get_usage(db, loop.user_profile_id, scope)
        if remaining <= 0:
            notes.append("send: loop daily cap reached")
            return 0

        per_domain_cap = loop.per_domain_cap or settings.default_per_domain_cap
        contacted = _contacted_companies(db, loop.user_profile_id)

        tailored_apps = (
            db.query(JobApplication)
            .join(Job, Job.id == JobApplication.job_id)
            .filter(
                JobApplication.user_profile_id == loop.user_profile_id,
                JobApplication.status == ApplicationStatus.TAILORED.value,
            )
            .order_by(JobApplication.ai_match_score.desc())
            .all()
        )

        sent_total = 0
        for app in tailored_apps:
            if remaining <= 0:
                break
            job = app.job
            if not job or not _job_matches_role(job, loop.role):
                continue
            company_key = (job.company or "").strip().lower()
            if company_key and company_key in contacted:
                continue

            allowance = min(per_domain_cap, settings.max_emails_per_company)
            try:
                results = await self.email_service.send_outreach(
                    db, app.id, dry_run=False, max_recipients=allowance
                )
            except Exception as exc:
                logger.warning("Automation send failed for app %s: %s", app.id, exc)
                notes.append(f"send error: {exc}")
                break  # misconfigured mailbox affects every app

            if any(r.status == "sent" for r in results):
                sent_total += 1
                remaining -= 1
                incr_usage(db, loop.user_profile_id, scope, 1)
                db.commit()
                if company_key:
                    contacted.add(company_key)

        notes.append(f"sent: {sent_total}")
        return sent_total


def _has_sending_identity(profile: UserProfile) -> bool:
    has_own = bool(profile.smtp_user and profile.smtp_password_enc)
    has_shared = bool(settings.smtp_user and settings.smtp_password)
    return has_own or has_shared


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
        if not profile or not _has_sending_identity(profile):
            continue
        user = db.query(User).filter(User.id == profile.user_id).first()
        limits = effective_limits(user) if user else None
        if not limits or not limits.can_automate:
            continue
        logger.info("Running automation loop %s (profile %s)", loop.id, profile.id)
        await service.run_for_loop(db, loop, limits)
        processed += 1
    return processed
